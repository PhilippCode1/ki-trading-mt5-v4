"""Trade-Test (Tor 85): Konfig-Pin, Walk-Forward, Kennzahlen mit Handwerten, Band-Nachrechnung gegen den Takt, Bewertung, Auswahl."""
from __future__ import annotations

import ast
import copy
import dataclasses
import random
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kit.domain.types import Namensraum, Position, Side, SymbolSpec
from kit.gates import ROOT, tore
from kit.gates import trade_test as tt
from kit.orders import ids
from kit.research.stats import wilson
from kit.risk import band as bandmod

D = Decimal
T = tore()
K = tt.konfig()
BAND = bandmod.Band.aus_toren(T)
J2013, J2014, J2021, J2021H2 = 1356998400, 1388534400, 1609459200, 1625097600      # 01.01.2013/2014/2021, 01.07.2021 UTC
TAG = 86400


def _konf(bootstrap: int = 500) -> dict:
    k = copy.deepcopy(K)
    k["bootstrap"]["wiederholungen"] = bootstrap        # Tests ohne Bootstrap-Schwerpunkt schneller
    return k


# ---------------------------------------------------------------- Konfiguration
def test_konfig_gepinnt_und_aenderung_erkannt(tmp_path):
    assert K["version"] == 1 and K["walk_forward"]["entwicklung_ende"] == "2021-06-30" and K["konto"]["versatz_s"] == 10800
    assert K["kennzahlen"] == {"gewinnfaktor_basis": "EUR", "verlust_zu_gewinn_basis": "EUR"} and K["zusatz"]["nur_berichten"] is True
    kopie = tmp_path / "trade_test.toml"
    kopie.write_bytes(tt.TRADE_TEST_PFAD.read_bytes().replace(b"saat = 4041", b"saat = 4040"))
    with pytest.raises(tt.TradeTestVeraendert):
        tt.konfig(kopie)


def test_konfig_passt_zu_den_toren_und_doppelt_keine_schwellen():
    assert D(K["bootstrap"]["untergrenze_perzentil"]) == 100 - D(T["tor_85"]["erwartung_untergrenze_prozent"])
    assert K["zufall"]["wiederholungen"] >= T["tor_85"]["zufall_wiederholungen"]
    assert D(K["zufall"]["perzentil"]) == D(T["tor_85"]["zufall_perzentil"])
    assert not {"tor_85", "stop50", "band", "limits"} & set(K)
    falsch = _konf()
    falsch["bootstrap"]["untergrenze_perzentil"] = "10"
    with pytest.raises(ValueError):
        tt.bewerten([], [], [], [], [], T, falsch, monate=1)


def test_unabhaengig_vom_takt():
    baum = ast.parse((ROOT / "kit" / "gates" / "trade_test.py").read_text(encoding="utf-8"))
    module = {n.module for n in ast.walk(baum) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(baum)
                                                                                     if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and m.startswith(("kit.risk", "kit.run", "kit.backtest")) for m in module)


# ---------------------------------------------------------------- Zeitfenster
def test_walk_forward_fenster_exakt():
    wf = K["walk_forward"]
    f = tt.walk_forward(wf["entwicklung_start"], wf["entwicklung_ende"], wf["anpassung_jahre"], wf["test_jahre"])
    jahre = [J2013 + sum((366 if j % 4 == 0 else 365) * TAG for j in range(2013, 2013 + i)) for i in range(9)]
    assert f == [(jahre[i], jahre[i + 1]) for i in range(8)] + [(J2021, J2021H2)]
    assert f[0] == (J2013, J2014) and len(f) == 9
    assert tt.walk_forward("2010-01-01", "2021-06-30", 3, 2)[-1] == (J2021, J2021H2)
    assert [v for v, _ in tt.walk_forward("2010-01-01", "2021-06-30", 3, 2)] == [J2013, jahre[2], jahre[4], jahre[6], J2021]
    assert tt.walk_forward("2010-01-01", "2012-12-31", 3, 1) == []
    assert tt.walk_forward("2012-02-29", "2016-12-31", 1, 1)[0][0] == 1362009600                    # 28.02.2013


def _trade(t_auf: int, ergebnis: str, *, t_zu: int | None = None, risiko: str = "30", grund: str = "TP", einstieg=None) -> tt.TestTrade:
    return tt.TestTrade("EURUSD", "BUY", t_auf, t_auf + 3600 if t_zu is None else t_zu, D(ergebnis), D(risiko), grund, einstieg)


def test_oos_grenzen_und_trade_eigenschaften():
    trades = [_trade(J2013 - 1, "1"), _trade(J2013, "1"), _trade(J2014 - 1, "1"), _trade(J2014, "1")]
    assert tt.oos(trades, [(J2013, J2014)]) == trades[1:3]
    assert _trade(0, "15").r == 0.5 and _trade(0, "0").gewinn is False and _trade(0, "0.01").gewinn is True
    assert tt.TestTrade.__test__ is False


# ---------------------------------------------------------------- Kennzahlen
def test_quote_gewinnfaktor_verlust_zu_gewinn():
    werte = [D(10), D(20), D(-5), D(0), D(-15)]
    assert tt.quote([_trade(0, str(w)) for w in werte]) == D("0.4") and tt.quote([]) == 0
    assert tt.gewinnfaktor(werte) == D("1.5")                                           # 30 / 20
    assert tt.verlust_zu_gewinn(werte) == D(10) / D(15)                                   # Ø|5, 15| / Ø(10, 20); 0 verdünnt nicht
    assert tt.verlust_zu_gewinn([D(10), D(0), D(-30)]) == 3                               # Review F-04: nicht 1,5
    assert tt.verlust_zu_gewinn([D(0), D(5)]) == 0                                        # nur Null-Ergebnis: kein Verlustbetrag
    assert tt.gewinnfaktor([D(1), D(2)]) is None and tt.gewinnfaktor([]) is None
    assert tt.verlust_zu_gewinn([D(1)]) == 0 and tt.verlust_zu_gewinn([D(-1)]) == tt.UNENDLICH and tt.verlust_zu_gewinn([]) is None
    assert tt.gewinnfaktor([0.5, -0.25]) == 2


def test_max_drawdown_vom_laufenden_hoch():
    kurve = [(i, D(e)) for i, e in enumerate((100, 120, 90, 130, 104))]
    assert tt.max_drawdown_prozent(kurve) == D(25)                                      # (120 − 90) / 120
    assert tt.max_drawdown_prozent([(0, D(100)), (1, D(110))]) == 0 and tt.max_drawdown_prozent([]) is None


def test_stop50_ereignisse_konstruierte_folge():
    folge = [_trade(i, e) for i, e in enumerate(("-1", "0", "1", "1", "1", "-1", "-1", "1"))]
    assert tt.stop50_ereignisse(folge, 4, 3, "0.5") == [2, 6]                           # 1/3; 2/4 hält; 3/4; 2/4 erneut
    verluste = [_trade(i, "-1") for i in range(30)]
    s = T["stop50"]
    assert tt.stop50_ereignisse(verluste, s["fenster"], s["ab_trades"], s["quote_max"]) == [19]
    gemischt = [_trade(i, "1" if i % 2 else "-1") for i in range(60)]                    # genau 50 % → ≤ 50 % ab Trade 20
    assert tt.stop50_ereignisse(gemischt, s["fenster"], s["ab_trades"], s["quote_max"]) == [19]
    assert tt.stop50_ereignisse([_trade(i, "1") for i in range(60)], 50, 20, "0.50") == []


def test_wilson_aus_stats():
    lo, hi = wilson(170, 200)
    assert abs(lo - 0.7939442071583334) < 1e-12 and abs(hi - 0.89286406437758) < 1e-12


def test_naechster_rang_und_bootstrap_deterministisch():
    werte = [float(i) for i in range(1, 11)]
    assert [tt._naechster_rang(werte, p) for p in ("0", "5", "50", "95", "100")] == [1.0, 1.0, 5.0, 10.0, 10.0]
    zufall = random.Random(5)
    r = [zufall.uniform(-1.0, 1.0) for _ in range(30)]
    a = tt.bootstrap_untergrenze(r, 2000, 4041, "5")
    assert a == tt.bootstrap_untergrenze(r, 2000, 4041, "5") and a != tt.bootstrap_untergrenze(r, 2000, 1, "5")
    assert a < sum(r) / len(r) < tt.bootstrap_untergrenze(r, 2000, 4041, "95")
    assert tt.bootstrap_untergrenze([0.0, 1.0], 1, 7, "5") == sum(random.Random(7).choices([0.0, 1.0], k=2)) / 2
    assert tt.bootstrap_untergrenze([0.25] * 5, 100, 1, "5") == 0.25 and tt.bootstrap_untergrenze([], 10, 1, "5") is None


def test_zufallsbasis():
    halb = tt.zufallsbasis([(True, False)] * 200, 1000, 4042, "95")
    assert halb["n"] == 200 and abs(halb["mittel"] - 0.5) < 0.01 and 0.5 < halb["p95"] < 0.6
    assert halb == tt.zufallsbasis([(True, False)] * 200, 1000, 4042, "95")
    assert tt.zufallsbasis([(True, True)] * 10, 50, 1, "95") == {"p95": 1.0, "mittel": 1.0, "n": 10}
    assert tt.zufallsbasis([(False, False)] * 10, 50, 1, "95")["p95"] == 0.0
    assert tt.zufallsbasis([], 50, 1, "95") == {"p95": None, "mittel": None, "n": 0}


def test_tagesverluste_servertag():
    t0 = 1609718400                                                                     # Mo 04.01.2021 00:00 UTC = 03:00 Server
    kurve = [(t0, D(10000)), (t0 + 3600, D(9800)), (t0 + 20 * 3600, D(9600)),           # Servertag 04.01.: 4 %
             (t0 + 21 * 3600, D(9600)), (t0 + 22 * 3600, D(9500)),                       # 21:00 UTC = 00:00 Server: neuer Anker
             (t0 + 45 * 3600, D(10000)), (t0 + 46 * 3600, D(9700))]                      # Servertag 06.01.: genau 3 % (nicht über)
    tv = tt.tagesverluste(kurve, 10800)
    assert tv == {"max_prozent": D(4), "tage_ueber_3": 1}
    assert tt.tagesverluste(kurve, 0)["max_prozent"] == D(5)                             # UTC-Tage: Anker 10000, Tief 9500
    assert tt.tagesverluste([], 10800) == {"max_prozent": 0, "tage_ueber_3": 0}


def test_monatsrenditen_und_teilperioden():
    maerz15, april = 1615766400, 1617235200
    kurve = [(J2021, D(100)), (J2021 + 30 * TAG + 82800, D(110)), (maerz15, D(99)), (april, D(500))]
    assert tt.monatsrenditen(kurve, J2021, april) == [pytest.approx(0.1), 0.0, pytest.approx(-0.1)]
    assert tt.monatsrenditen([], J2021, april) == []
    trades = [_trade(0, "10", t_zu=50), _trade(0, "-5", t_zu=150), _trade(0, "3", t_zu=160), _trade(0, "1", t_zu=399),
              _trade(0, "2", t_zu=450)]
    assert tt.teilperioden(trades, 4, 0, 400) == [D(10), D(-2), D(0), D(3)]             # danach → letzter Abschnitt


# ---------------------------------------------------------------- Hebelband und Tagesbudget
def _einstieg(**ueber) -> tt.Einstieg:
    basis = {"symbol": "EURUSD", "side": "BUY", "t": 0, "lots": D("0.53"), "preis": D("1.10000"), "sl": D("1.09800"),
             "tp": D("1.10100"), "equity": D(10000), "budget": D(300), "provision": D(0), "waehrung": "EUR",
             "tick_size": D("0.00001"), "tick_value": D(1), "contract_size": D(100000), "currency_base": "EUR",
             "volume_min": D("0.01"), "volume_step": D("0.01"), "volume_max": D(100)}
    basis.update(ueber)
    return tt.Einstieg(**basis)


def test_band_pruefen_handwerte():
    b = T["band"]
    spec = SymbolSpec(name="EURUSD", digits=5, point=D("0.00001"), tick_size=D("0.00001"), tick_value=D(1), contract_size=D(100000),
                      volume_min=D("0.01"), volume_max=D(100), volume_step=D("0.01"))
    g = bandmod.einstieg_strategie(BAND, spec, "EUR", Side.BUY, D("1.10000"), D("1.09800"), D("1.10100"), equity=D(10000), offene=[],
                                   budget=D(300), provision=D(0))
    assert g.lots == D("0.53")                                                           # h0 5,3; htp 53000/10053 = 5,27; 0,52 → 5,2
    assert tt.band_pruefen(_einstieg(), b) == []
    assert tt.band_pruefen(_einstieg(lots=D("0.54")), b) == ["LOT_NICHT_MINIMAL"]
    assert tt.band_pruefen(_einstieg(lots=D("0.535")), b) == ["LOT_RASTER"]
    assert tt.band_pruefen(_einstieg(lots=D("0.53"), volume_min=D("0.6")), b) == ["LOT_RASTER"]
    assert tt.band_pruefen(_einstieg(side="SELL"), b) == ["SCHUTZ"]
    assert tt.band_pruefen(_einstieg(budget=D(100)), b) == ["TAGESBUDGET"]                # Verlust bis SL 106
    assert tt.band_pruefen(_einstieg(offene_risiko=D(250)), b) == ["TAGESBUDGET"]
    assert tt.band_pruefen(_einstieg(offene_nominal=D(100000)), b) == ["BAND_GESAMT"]     # 153000 / 10000
    assert tt.band_pruefen(_einstieg(tp=D("1.12000")), b) == ["BAND_TP"]                  # 53000 / 11060 = 4,79
    assert tt.band_pruefen(_einstieg(lots=D("1.50")), b) == ["BAND_EINSTIEG", "BAND_SL", "BAND_GESAMT", "LOT_NICHT_MINIMAL"]
    # Größenregel des Takts ohne Einstiegskosten: 0,53 Lot bei Equity 10096 → 53000 / 10096 = 5,2496 < 5,25, also ist 0,54 minimal
    # (mit Einstiegskosten wäre 53000 / (10096 − 1,7225) = 5,2505 – die Prüfung h0 ≥ 5,25 nach Kosten bestünde schon mit 0,53).
    kante = _einstieg(equity=D(10096), provision=D("3.25"), lots=D("0.54"), tp=D("1.10005"), sl=D("1.09990"))
    assert tt.band_pruefen(kante, b) == []
    with pytest.raises(ValueError):
        tt.band_pruefen(_einstieg(side="KAUF"), b)
    zu_weit = _einstieg(sl=D("1.09500"), tp=D("1.10100"))                                   # Stop 500 > 3 × Ziel 100 (D4)
    assert "STOP_ZU_ZIEL" in tt.band_pruefen(zu_weit, b) and "STOP_ZU_ZIEL" not in tt.band_pruefen(_einstieg(), b)


@st.composite
def _faelle(draw):
    """Zufälliger Einstieg auf einem EURUSD-ähnlichen (Basis EUR) oder USDJPY-ähnlichen Vertrag (Basis USD) mit konsistentem Tickwert.

    Auch Mini-Ziele: die Minimalität folgt der Größenregel des Takts (Untergrenze beim Einstieg ohne Einstiegskosten)."""
    jpy = draw(st.booleans())
    tick = D("0.001") if jpy else D("0.00001")
    if jpy:
        kurs = draw(st.integers(80_000, 160_000)) * tick
        tv = (tick * 100000 / (draw(st.integers(100_000, 170_000)) * D("0.001"))).quantize(D("0.00001"))   # über EURJPY
    else:
        kurs = draw(st.integers(100_000, 160_000)) * tick
        tv = (tick * 100000 / kurs).quantize(D("0.00001"))
    spec = SymbolSpec(name="USDJPY" if jpy else "EURUSD", digits=3 if jpy else 5, point=tick, tick_size=tick, tick_value=tv,
                      contract_size=D(100000), volume_min=D("0.01"), volume_max=D(100), volume_step=D("0.01"),
                      currency_profit="JPY" if jpy else "USD", currency_base="USD" if jpy else "EUR")
    side = draw(st.sampled_from([Side.BUY, Side.SELL]))
    tp_ticks = draw(st.integers(10, 400))
    sl_ticks = draw(st.integers(1, 3 * tp_ticks))
    provision = draw(st.sampled_from([D(0), D("3.25"), D("4.875")]))
    equity = D(draw(st.integers(1_000, 300_000))) + D(draw(st.integers(0, 99))) / 100
    budget = equity * draw(st.sampled_from([D("0.5"), D(1), D(3)])) / 100
    offene: list[bandmod.Bewertet] = []
    if draw(st.booleans()):                                                             # offene Probe (V4) belastet Gesamt und Budget
        pos = Position(9, spec.name, Side.BUY, D("0.01"), kurs, kurs - tick, D(0), ids.magic(Namensraum.PROBE, "p"))
        offene.append(bandmod.Bewertet(pos, spec, D(draw(st.integers(0, 30_000))), D(draw(st.integers(0, 40))), False))
    return spec, side, kurs, kurs - side.sign * sl_ticks * tick, kurs + side.sign * tp_ticks * tick, equity, budget, provision, offene


def _takt_und_einstieg(fall) -> tuple[bandmod.Groesse, tt.Einstieg | None]:
    spec, side, kurs, sl, tp, equity, budget, provision, offene = fall
    g = bandmod.einstieg_strategie(BAND, spec, "EUR", side, kurs, sl, tp, equity=equity, offene=offene, budget=budget,
                                   provision=provision)
    if g.lots is None:
        return g, None
    e = tt.Einstieg(spec.name, side.value, 0, g.lots, kurs, sl, tp, equity, budget, provision, "EUR", spec.tick_size, spec.tick_value,
                    spec.contract_size, spec.currency_base, spec.volume_min, spec.volume_step, spec.volume_max,
                    sum((b.nominal for b in offene), D(0)), sum((b.restrisiko for b in offene), D(0)))
    return g, e


@given(_faelle())
def test_band_pruefen_konsistent_mit_takt(fall):
    _, e = _takt_und_einstieg(fall)
    if e is not None:
        assert tt.band_pruefen(e, T["band"]) == []


@given(_faelle())
def test_band_pruefen_erkennt_aufgerundetes_lot(fall):
    _, e = _takt_und_einstieg(fall)
    if e is not None:
        befunde = tt.band_pruefen(dataclasses.replace(e, lots=e.lots + e.volume_step), T["band"])
        assert "LOT_NICHT_MINIMAL" in befunde or any(b.startswith("BAND_") or b == "TAGESBUDGET" for b in befunde)


def test_band_faelle_nicht_leer():
    treffer = 0
    rng = random.Random(3)
    for _ in range(200):
        tick, kurs = D("0.00001"), rng.randint(100_000, 160_000) * D("0.00001")
        tv = (tick * 100000 / kurs).quantize(D("0.00001"))
        spec = SymbolSpec(name="EURUSD", digits=5, point=tick, tick_size=tick, tick_value=tv, contract_size=D(100000),
                          volume_min=D("0.01"), volume_max=D(100), volume_step=D("0.01"))
        tp_ticks = rng.randint(50, 300)
        fall = (spec, Side.SELL, kurs, kurs + tp_ticks * 2 * tick, kurs - tp_ticks * tick, D(rng.randint(2_000, 100_000)),
                D(rng.randint(2_000, 100_000)) * D("0.03"), D("3.25"), [])
        _, e = _takt_und_einstieg(fall)
        if e is not None:
            treffer += 1
            assert tt.band_pruefen(e, T["band"]) == []
    assert treffer > 50


# ---------------------------------------------------------------- Bewertung
def _lauf(n: int = 240, verlust_jeder: int = 12, *, start: int = J2013, ergebnis_verlust: str = "-20", erste_verluste: int = 0):
    trades, kurve, eq = [], [(start, D(10000))], D(10000)
    for i in range(n):
        t_auf = start + i * 3 * TAG
        verlust = i < erste_verluste or i % verlust_jeder == verlust_jeder - 1
        erg = D(ergebnis_verlust) if verlust else D(10)
        trades.append(tt.TestTrade("EURUSD", "BUY", t_auf, t_auf + 7200, erg, D(30), "SL" if verlust else "TP", _einstieg(t=t_auf)))
        eq += erg
        kurve.append((t_auf + 7200, eq))
    return trades, kurve


SIGNALE = ([{"symbol": "EURUSD", "kerze": i, "side": "BUY", "ergebnis": "ERLEDIGT", "grund": ""} for i in range(240)]
           + [{"symbol": "EURUSD", "kerze": 0, "side": "BUY", "ergebnis": "ABGELEHNT", "grund": "TAGESBUDGET"}] * 15
           + [{"symbol": "EURUSD", "kerze": 0, "side": "SELL", "ergebnis": "ABGELEHNT", "grund": "STOP_ZU_ZIEL"}] * 5
           + [{"symbol": "EURUSD", "kerze": 0, "side": "SELL", "ergebnis": "OFFEN", "grund": ""}])


def test_bewerten_bestanden():
    trades, kurve = _lauf()
    b = tt.bewerten(trades, kurve, SIGNALE, [], [(True, False)] * 240, T, K, monate=24)
    k, z = b["kriterien"], b["kennzahlen"]
    assert b["bestanden"] is True and all(x["ok"] is True for x in k.values())
    assert list(k) == ["trades", "quote", "erwartung_r", "gewinnfaktor", "verlust_zu_gewinn", "zufallsbasis", "drawdown", "stop50",
                       "band_budget"]
    assert "Holdout" in k["trades"]["text"] and k["trades"]["wert"] == 240
    assert (z["n"], z["gewinner"], z["trades_pro_monat"]) == (240, 220, 10.0)
    assert z["wilson_95"] == list(wilson(220, 240)) and z["pf_eur"] == 5.5 and z["verlust_zu_gewinn_eur"] == 2.0
    assert z["e_r"] == pytest.approx((220 / 3 - 20 * 2 / 3) / 240) and 0 < z["e_r_untergrenze"] < z["e_r"]
    assert z["pf_r"] == pytest.approx(5.5) and z["verlust_zu_gewinn_r"] == pytest.approx(2.0)
    assert z["ausstiege"] == {"SL": 20, "TP": 220} and z["stop50_ereignisse"] == [] and z["schatten"] == {}
    assert z["signale"] == {"gesamt": 261, "erledigt": 240, "abgelehnt": {"STOP_ZU_ZIEL": 5, "TAGESBUDGET": 15}, "sonst": 1,
                            "quote_signal_trade": 240 / 261}
    assert z["hebel"] == {"min": 5.3, "mittel": pytest.approx(5.3), "max": 5.3} and z["band_befunde"] == {}
    assert abs(z["zufall"]["mittel"] - 0.5) < 0.01 and z["max_dd_prozent"] < 1


def test_bewerten_nicht_bestanden_je_kriterium():
    konf = _konf()

    def urteil(trades, kurve, schatten=(), paare=None, **kw):
        b = tt.bewerten(trades, kurve, [], list(schatten), [(True, False)] * len(trades) if paare is None else paare, T, konf,
                        monate=24, **kw)
        return b, {name: x["ok"] for name, x in b["kriterien"].items()}

    trades, kurve = _lauf()
    b, ok = urteil(trades, kurve)
    assert b["bestanden"] is True
    b, ok = urteil(*_lauf(200, 5))                                                      # 160/200 = 80 %
    assert ok["quote"] is False and ok["gewinnfaktor"] is True and b["bestanden"] is False
    assert urteil(*_lauf(199, 100))[1]["trades"] is False
    b, ok = urteil(*_lauf(erste_verluste=20))
    assert ok["stop50"] is False and b["kennzahlen"]["stop50_ereignisse"] == [19]
    b, ok = urteil(trades, kurve, [{"art": "LOSS_LOCK", "t": J2013 + 100}, {"art": "STOP50", "t": J2013 - 10**6}])
    assert ok["stop50"] is False and b["kennzahlen"]["schatten"] == {"LOSS_LOCK": 1}
    assert urteil(trades, kurve, [{"art": "STOP50", "t": J2013 - 10**6}, {"art": "TAGESSTOPP", "t": J2013 + 100}])[0]["bestanden"]
    assert urteil(trades, kurve, [{"art": "STOP50", "t": J2013 + 5}], zeitraum=(J2013 + 10, J2021))[0]["bestanden"]
    mit_befund = [*trades[:-1], dataclasses.replace(trades[-1], einstieg=_einstieg(lots=D("0.54")))]
    b, ok = urteil(mit_befund, kurve)
    assert ok["band_budget"] is False and b["kennzahlen"]["band_befunde"] == {"LOT_NICHT_MINIMAL": 1}
    b, ok = urteil([*trades[:-1], dataclasses.replace(trades[-1], einstieg=None)], kurve)
    assert ok["band_budget"] is None and b["bestanden"] is False
    tief = [*kurve[:100], (kurve[99][0] + 1, D(7400)), *kurve[100:]]                    # 26 % unter dem Hoch
    b, ok = urteil(trades, tief)
    assert ok["drawdown"] is False and b["kennzahlen"]["max_dd_prozent"] > 25
    assert urteil(trades, [])[1]["drawdown"] is None
    assert urteil(trades, kurve, paare=[(True, False)] * 10)[1]["zufallsbasis"] is None
    assert urteil(trades, kurve, paare=[(True, True)] * 240)[1]["zufallsbasis"] is False   # Zufall trifft immer
    b, ok = urteil(*_lauf(240, 2, ergebnis_verlust="-35"))                              # Ø Verlust 3,5 × Ø Gewinn, E[R] < 0
    assert ok["verlust_zu_gewinn"] is False and ok["gewinnfaktor"] is False and ok["erwartung_r"] is False
    alle = [dataclasses.replace(t, ergebnis=D(10)) for t in trades]
    b, ok = urteil(alle, kurve)
    assert b["kriterien"]["gewinnfaktor"]["wert"] == float("inf") and ok["gewinnfaktor"] is True and ok["verlust_zu_gewinn"] is True


def test_bewerten_leer_nicht_bewertbar():
    b = tt.bewerten([], [], [], [], [], T, K, monate=0)
    assert b["bestanden"] is False and all(x["ok"] is None for x in b["kriterien"].values())
    z = b["kennzahlen"]
    assert z["n"] == 0 and z["quote"] is None and z["wilson_95"] is None and z["trades_pro_monat"] is None
    assert z["signale"]["quote_signal_trade"] is None and z["hebel"]["min"] is None


def test_auswahl_mit_gleichstand():
    def bew(bestanden: bool, lo: float, tpm: float) -> dict:
        return {"bestanden": bestanden, "kennzahlen": {"wilson_95": [lo, 0.99], "trades_pro_monat": tpm}}

    assert tt.auswahl({"A": bew(True, 0.80, 5), "B": bew(True, 0.80, 8), "C": bew(False, 0.95, 20)}) == "B"
    assert tt.auswahl({"A": bew(True, 0.81, 1), "B": bew(True, 0.80, 8)}) == "A"
    assert tt.auswahl({"A": bew(True, 0.80, 8), "B": bew(True, 0.80, 8)}) == "A"           # voller Gleichstand: Reihenfolge
    assert tt.auswahl({"C": bew(False, 0.95, 20)}) is None and tt.auswahl({}) is None


def test_zusatz_nur_berichten():
    z = tt.zusatz(K, teilperioden_werte=[D(1), D(-1), D(2), D(3)], gewinnfaktor_kosten=D("1.0"), dsr=0.96)
    assert z["nur_berichten"] is True
    assert z["teilperioden"]["positiv"] == 3 and z["teilperioden"]["ok"] is True and z["teilperioden"]["schwelle"] == "3/4"
    assert z["gewinnfaktor_kosten"]["ok"] is False and z["dsr"]["ok"] is True                # Kosten × 1,5: > 1,0 verlangt
    leer = tt.zusatz(K)
    assert leer["dsr"]["ok"] is None and leer["teilperioden"]["ok"] is None and leer["gewinnfaktor_kosten"]["ok"] is None
