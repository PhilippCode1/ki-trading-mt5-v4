"""Risiko: Nominal/Gegenprobe, Hebelband (Einstieg, Probe, Prüfpunkte), Tagesbudget, LOSS_LOCK, 50-%-Stopp, Tradebuch, Wächter."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from kit.config import Konfiguration
from kit.domain.types import AccountSnapshot, Bar, HandelsModus, KontoModus, Namensraum, Position, Quote, Side
from kit.gates import tore
from kit.orders import ids
from kit.risk import band as bandmod
from kit.risk import guards, limits, sizing
from kit.run.trockenlauf import specs

D = Decimal
UTC = dt.UTC
SPECS = {s.name: s for s in specs()[0]}
EU, GU, UJ = SPECS["EURUSD"], SPECS["GBPUSD"], SPECS["USDJPY"]
BAND = bandmod.Band.aus_toren(tore())
PROV = D("3.25")


def test_tore_eingefroren_und_versiegelte_werte():
    t = tore()
    assert (t["band"]["boden"], t["band"]["deckel"], t["band"]["korridor_unten"], t["band"]["korridor_oben"]) == ("5", "15", "5.25", "14.25")
    assert t["limits"]["loss_lock_prozent"] == "25" and t["limits"]["tagesbudget_prozent"] == "3"
    assert t["stop50"] == {"fenster": 50, "ab_trades": 20, "quote_max": "0.50"}
    assert t["tor_85"]["quote_min"] == "0.85" and t["tor_95"]["quote_min"] == "0.95" and t["tor_t"]["quote_min"] == "0.95"


def test_tore_aenderung_wird_erkannt(tmp_path):
    from kit.gates import TORE_PFAD, ToreVeraendert
    kopie = tmp_path / "tore.toml"
    kopie.write_bytes(TORE_PFAD.read_bytes().replace(b'quote_min = "0.85"', b'quote_min = "0.50"'))
    try:
        tore(kopie)
    except ToreVeraendert:
        return
    raise AssertionError("veränderte Tore nicht erkannt")


def test_nominal_und_ergebnis():
    assert sizing.nominal(EU, D("1.163"), D("1"), "EUR") == D(100000)              # Basis = Kontowährung
    assert abs(sizing.nominal(GU, D("1.34"), D("1"), "EUR") - D("115220")) < D(50)
    assert sizing.ergebnis(EU, Side.BUY, D("1.16300"), D("1.16400"), D("1")) == D("100") * EU.tick_value
    assert sizing.ergebnis(EU, Side.SELL, D("1.16300"), D("1.16400"), D("1")) < 0


def test_gegenprobe_tickwert():
    assert sizing.gegenprobe(EU, sizing.umrechnung_aus_kurs("EUR", "USD", "EURUSD", D("1.163"), D("1.16312"))) is None
    assert sizing.gegenprobe(UJ, sizing.umrechnung_aus_kurs("EUR", "JPY", "EURJPY", D("172.1"), D("172.12"))) is None
    assert sizing.gegenprobe(EU, sizing.umrechnung_aus_kurs("EUR", "USD", "EURUSD", D("1.40"), D("1.40"))) == "TICKWERT_UNPLAUSIBEL"
    assert sizing.gegenprobe(EU, None) == "UMRECHNUNG_FEHLT"


def _groesse(side=Side.BUY, sl_p="0.45", tp_p="0.35", equity="10000", offene=(), budget="300", spec=EU, preis="1.16312"):
    p = D(preis)
    sl = p * (1 - side.sign * D(sl_p) / 100)
    tp = p * (1 + side.sign * D(tp_p) / 100)
    return bandmod.einstieg_strategie(BAND, spec, "EUR", side, p, sl, tp, equity=D(equity), offene=list(offene), budget=D(budget),
                                      provision=PROV)


def test_einstieg_im_korridor_inkl_tp_und_sl():
    for side in (Side.BUY, Side.SELL):
        for spec, preis in ((EU, "1.16312"), (GU, "1.34016"), (UJ, "148.014")):
            g = _groesse(side=side, spec=spec, preis=preis)
            assert g.lots is not None, g
            assert BAND.unten <= g.hebel <= BAND.oben and g.hebel_tp >= BAND.unten and g.hebel_sl <= BAND.oben
            assert g.verlust_sl <= D(300)
            kleiner = bandmod.einstieg_strategie(BAND, spec, "EUR", side, D(preis), D(preis), D(preis), equity=D(10000), offene=[],
                                                 budget=D(300), provision=PROV)
            assert kleiner.lots is None


def test_einstieg_minimal_noetiges_volumen():
    g = _groesse()
    weniger = g.lots - EU.volume_step
    nominal = sizing.nominal(EU, D("1.16312"), weniger, "EUR")
    tp = D("1.16312") * (1 + D("0.35") / 100)
    equity_tp = D(10000) + sizing.ergebnis(EU, Side.BUY, D("1.16312"), tp, weniger) - sizing.kosten(weniger, PROV)
    assert nominal / D(10000) < BAND.unten or nominal / equity_tp < BAND.unten          # ein Schritt weniger verletzt die Untergrenze


def test_einstieg_budget_und_sl_obergrenze_und_maximum():
    assert _groesse(budget="100").grund == "TAGESBUDGET"
    assert _groesse(sl_p="2.5", tp_p="1").grund in ("BAND_OBERGRENZE", "TAGESBUDGET")
    p = Position(1, "EURUSD", Side.BUY, D("0.54"), D("1.163"), D("1.15"), D("1.17"), ids.magic(Namensraum.STRATEGIE, "x"))
    offen = bandmod.Bewertet(p, EU, D(54000), D(100), True)
    assert _groesse(offene=[offen]).grund == "MAX_STRATEGIEPOSITIONEN"
    assert _groesse(equity="0").grund == "EQUITY_NICHT_POSITIV"


def test_probe_nur_obergrenze():
    g = bandmod.einstieg_probe(BAND, EU, "EUR", Side.BUY, D("1.16312"), D("1.16012"), equity=D(10000), offene=[], budget=D(300),
                               provision=PROV)
    assert g.lots == EU.volume_min and g.hebel < BAND.unten                                 # V4: keine Untergrenze
    p = Position(1, "EURUSD", Side.BUY, D("1.43"), D("1.163"), D("1.16"), D("1.17"), ids.magic(Namensraum.STRATEGIE, "y"))
    voll = bandmod.Bewertet(p, EU, D(143000), D(50), True)
    g2 = bandmod.einstieg_probe(BAND, EU, "EUR", Side.BUY, D("1.16312"), D("1.16012"), equity=D(10000), offene=[voll], budget=D(300),
                                provision=PROV)
    assert g2.grund == "BAND_OBERGRENZE"


def _bew(lots: str, strategie: bool = True, ticket: int = 1, spec=EU) -> bandmod.Bewertet:
    ns = Namensraum.STRATEGIE if strategie else Namensraum.PROBE
    p = Position(ticket, spec.name, Side.BUY, D(lots), D("1.163"), D("1.15"), D("1.18"), ids.magic(ns, str(ticket)))
    return bandmod.Bewertet(p, spec, sizing.nominal(spec, D("1.163"), D(lots), "EUR"), D(10), strategie)


def test_pruefpunkt_boden_deckel_und_ruhe():
    assert bandmod.pruefpunkt(BAND, [_bew("0.54")], D(10000)) == []                          # 5,4 im Band
    boden = bandmod.pruefpunkt(BAND, [_bew("0.54")], D(12000))                               # 4,5 < 5 → glattstellen
    assert [(z.grund, z.lots) for z in boden] == [("BAND_BODEN", D("0.54"))]
    deckel = bandmod.pruefpunkt(BAND, [_bew("1.60"), _bew("0.01", False, 2)], D(10000))      # 16,1 > 15 → auf ≤ 14,25
    assert deckel[0].grund == "BAND_DECKEL" and deckel[0].ticket == 1
    rest = D("1.60") - deckel[0].lots
    assert (rest * 100000 + 1000) / D(10000) <= BAND.oben
    nur_probe = bandmod.pruefpunkt(BAND, [_bew("0.01", False, 3)], D(50))                    # Probe allein über dem Deckel
    assert nur_probe and nur_probe[0].ticket == 3


@given(st.integers(min_value=1000, max_value=200000), st.sampled_from(["0.10", "0.20", "0.35", "0.50"]), st.sampled_from([Side.BUY, Side.SELL]))
def test_einstieg_eigenschaften(equity, tp_p, side):
    g = _groesse(side=side, equity=str(equity), tp_p=tp_p, sl_p=str(D(tp_p) * D("1.2")), budget=str(D(equity) * D("0.03")))
    if g.lots is not None:
        assert BAND.unten <= g.hebel <= BAND.oben and g.hebel_tp >= BAND.unten and g.hebel_sl <= BAND.oben
        assert g.verlust_sl <= D(equity) * D("0.03") and g.lots % EU.volume_step == 0


def test_budget_tagesstopp_lossl_lock():
    assert limits.budget(D(10000), D(10000), D(3)) == D(300)
    assert limits.budget(D(10000), D(9800), D(3)) == D(100)
    assert limits.budget(D(10000), D(10500), D(3)) == D(300)                                  # Gewinn erhöht das Budget nicht
    assert not limits.tagesstopp(D(10000), D("9700.01"), D(3)) and limits.tagesstopp(D(10000), D(9700), D(3))
    assert not limits.loss_lock(D(10000), D("7500.01"), D(25)) and limits.loss_lock(D(10000), D(7500), D(25))


def _deal(seq, pid, entry, geld, magic, lots="0.5", zeit=0, art="HANDEL"):
    return {"art": "DEAL", "seq": seq, "daten": {"position_id": pid, "entry": entry, "geld": geld, "magic": magic, "volumen": lots,
                                                 "symbol": "EURUSD", "zeit": zeit or seq, "reason": "TP", "deal_art": art}}


def test_tradebuch_zaehlregeln():
    m = ids.magic(Namensraum.STRATEGIE, "a")
    buch = limits.Tradebuch()
    for s in (_deal(1, 7, "IN", "-1.63", m), _deal(2, 7, "OUT", "1.63", m),           # Kosten fressen den Gewinn: 0 = Verlust
              _deal(3, 8, "IN", "-1.63", m), _deal(4, 8, "OUT", "50", m, lots="0.25"), _deal(5, 8, "OUT", "-10", m, lots="0.25"),
              _deal(6, 9, "IN", "-0.03", ids.magic(Namensraum.PROBE, "p"), lots="0.01"), _deal(7, 9, "OUT", "4", 0, lots="0.01"),
              _deal(8, 10, "IN", "0", 12345), _deal(9, 0, "NONE", "1000", 0, art="KAPITAL")):
        buch.deal(s)
    trades = buch.geschlossene()
    assert [(t.position_id, t.gewinn) for t in trades] == [(7, False), (8, True)]
    assert [t.position_id for t in buch.geschlossene(Namensraum.PROBE)] == [9]
    assert buch.geschlossene(ab_seq=2) == [trades[1]]


def test_stop50_fenster():
    def trades(gewinne: list[bool]) -> list[limits.Trade]:
        return [limits.Trade(i, "EURUSD", Namensraum.STRATEGIE, i, i, D(1), D(1), D(5) if g else D(-5), i + 1) for i, g in enumerate(gewinne)]
    assert not limits.stop50(trades([False] * 19), 50, 20, D("0.5"))[0]                    # erst ab 20 Trades
    assert limits.stop50(trades([True] * 10 + [False] * 10), 50, 20, D("0.5"))[0]          # genau 50 % → Stopp
    assert not limits.stop50(trades([True] * 11 + [False] * 10), 50, 20, D("0.5"))[0]
    lang = trades([False] * 40 + [True] * 26 + [False] * 24)                                 # letzte 50: 26/50 → kein Stopp
    assert not limits.stop50(lang, 50, 20, D("0.5"))[0]


KONF = Konfiguration("", ("EURUSD",), ("EURUSD",))


def _konto(modus=HandelsModus.DEMO, margin="0", erlaubt=True):
    return AccountSnapshot(modus, KontoModus.HEDGING, "EUR", D(10000), D(10000), D(0), D(10000), D(margin), 30, erlaubt)


def _t(text: str) -> float:
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp()


def test_waechter_fenster_berlin():
    assert guards.im_fenster(_t("2026-10-07 06:00"), KONF)            # Mi 08:00 Berlin (Sommerzeit)
    assert not guards.im_fenster(_t("2026-10-07 05:59"), KONF)
    assert not guards.im_fenster(_t("2026-10-07 20:00"), KONF)        # 22:00 Berlin
    assert guards.im_fenster(_t("2026-10-09 17:59"), KONF)            # Fr 19:59
    assert not guards.im_fenster(_t("2026-10-09 18:00"), KONF)        # Fr ab 20:00 keine Einstiege
    assert not guards.im_fenster(_t("2026-10-10 10:00"), KONF)        # Samstag
    assert guards.im_fenster(_t("2026-11-04 07:00"), KONF)            # Winterzeit: 08:00 Berlin = 07:00 UTC
    assert not guards.im_fenster(_t("2026-11-04 06:30"), KONF)


def test_waechter_reihenfolge_und_gruende():
    t = _t("2026-10-07 10:00")
    q = Quote("EURUSD", D("1.16300"), D("1.16312"), int(t * 1000))
    kerzen = [Bar("EURUSD", int(t) - 120 + i, D("1.163"), D("1.164"), D("1.162"), D("1.163"), 12) for i in range(3)]
    assert guards.einstieg(t, _konto(), EU, q, kerzen, KONF, D(300)) is None
    assert guards.einstieg(t, _konto(HandelsModus.REAL), EU, q, kerzen, KONF, D(300)) == "NICHT_DEMO"
    assert guards.einstieg(t, _konto(erlaubt=False), EU, q, kerzen, KONF, D(300)) == "HANDEL_NICHT_ERLAUBT"
    assert guards.einstieg(t + 6, _konto(), EU, q, kerzen, KONF, D(300)) == "KURS_ALT"
    weit = Quote("EURUSD", D("1.18"), D("1.18012"), int(t * 1000))
    assert guards.einstieg(t, _konto(), EU, weit, kerzen, KONF, D(300)) == "KURS_AUSSER_KORRIDOR"
    breit = Quote("EURUSD", D("1.16300"), D("1.16350"), int(t * 1000))
    assert guards.einstieg(t, _konto(), EU, breit, kerzen, KONF, D(300)) == "SPREAD_HOCH"
    assert guards.einstieg(t, _konto(margin="250"), EU, q, kerzen, KONF, D(300)) == "MARGIN_NIEDRIG"
    assert guards.einstieg(_t("2026-10-10 10:00"), _konto(), EU, q, kerzen, KONF, D(300)) == "AUSSERHALB_FENSTER"
