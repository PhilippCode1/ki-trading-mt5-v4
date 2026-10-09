"""Backtest (F-04): Kostenmodell mit Handrechnung auf den Cent, Runner (Bilanz, Parität, Vorgriffswächter, Schattenereignisse),
Zufallsreferenz netto ≈ −Kosten und die Mutationen „Kosten aus“ und „Lot aufrunden“. Nur synthetische Kerzen."""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import replace
from decimal import Decimal

import pytest

from kit.backtest import kosten, paritaet, runner
from kit.backtest.ausstieg import Markt, simulieren, zufallspaar
from kit.backtest.kosten import Kostenprofil
from kit.backtest.terminal import BacktestTerminal, VorgriffFehler
from kit.broker.sim import Uhr
from kit.domain.types import Action, Bar, OrderRequest, Side
from kit.gates import tore
from kit.gates.trade_test import band_pruefen
from kit.orders import ids
from kit.risk import band as bandmod
from kit.strategy.rev import Fehlausbruch, MittelwertRueckkehr
from kit_tests import backtest_hilfen as bh

D = Decimal
MI_10 = 1420621200            # Mi 07.01.2015 09:00 UTC (Kerzenbeginn) = 12:00 Serverzeit
DO_10 = 1420707600            # Do 08.01.2015 09:00 UTC
MI_NACHT = 1420664400         # Mi 21:00 UTC = Do 00:00 Serverzeit (Rollover der Mittwochsnacht, Dreifachswap)


def _profil(provision: str = "3.25", **swap) -> Kostenprofil:
    return Kostenprofil("test", D(provision), {s: (D(a), D(b)) for s, (a, b) in swap.items()})


# ---------------------------------------------------------------------------------------------------- Kostenfunktionen
def test_swap_faktor_und_servertage():
    assert [kosten.swap_faktor(w) for w in range(7)] == [1, 1, 3, 1, 1, 0, 0]
    assert kosten.servertag_wechsel(MI_10, DO_10, 10800) == [MI_NACHT]
    assert kosten.servertag_wechsel(MI_NACHT, MI_NACHT + 86400, 10800) == [MI_NACHT + 86400]     # Grenze links offen, rechts zu
    assert kosten.wochentag_der_nacht(MI_NACHT, 10800) == 2                                     # Nacht Mi → Do
    assert kosten.wochentag_der_nacht(MI_NACHT + 2 * 86400, 10800) == 4                         # Nacht Fr → Sa: 1×


def test_umrechnung_tickwert_und_seitenkosten_von_hand():
    mitten = {"EURUSD": D("1.10006"), "USDJPY": D("110.010")}
    # USD: 1/1,10006 = 0,909041325… → 8 Stellen 0,90904133; JPY über EURJPY = 1,10006 · 110,010 = 121,0176006 → 100/121,0176006
    assert kosten.tickwert(D("0.00001"), D(100000), kosten.eur_je_einheit("USD", mitten)) == D("0.90904133")
    assert kosten.tickwert(D("0.001"), D(100000), kosten.eur_je_einheit("JPY", mitten)) == D("0.82632608")
    assert kosten.eur_je_einheit("EUR", mitten) == 1 and kosten.eur_je_einheit("GBP", mitten) is None
    # Seite EURUSD 0,53 Lot, Spread 12 Points: 0,53 · (0,00012/2 · 90904,133 + 3,25) = 4,6132514294
    assert kosten.seitenkosten(D("0.00012"), D("0.00001"), D("0.90904133"), D("0.53"), D("3.25")) == D("4.6132514294")
    # Seite USDJPY 0,40 Lot, Spread 20 Points: 0,40 · (0,020/2 · 826,32608 + 3,25) = 4,60530432
    assert kosten.seitenkosten(D("0.020"), D("0.001"), D("0.82632608"), D("0.40"), D("3.25")) == D("4.6053043200")
    p = _profil("3.25", EURUSD=("-7.5", "1.2")).mal("1.5")
    assert p.provision() == D("4.875") and p.spread_points(12) == 18 and p.spread_points(1) == 2
    assert p.swap("EURUSD", Side.BUY) == D("-11.25") and p.swap("EURUSD", Side.SELL) == D("1.2")       # Gutschrift bleibt


def test_handrechnung_eurusd_und_usdjpy_auf_den_cent():
    """Kauf EURUSD 0,53 Lot und Verkauf USDJPY 0,40 Lot über die Mittwochsnacht (Dreifachswap), Kommission 3,25 je Lot und Seite.

    Mi 10:00 (Schluss): EURUSD Bid 1,10000 / Ask 1,10012 (Mitte 1,10006), USDJPY 110,000 / 110,020 (Mitte 110,010).
    Swap Mi-Nacht ×3 zum Kurs des Rollovers: EURUSD −7,50 Pkt · 0,00001 · 100.000 = −7,50 USD/Lot → /1,10006 · 0,53 · 3 = −10,84;
    USDJPY −21,40 Pkt · 0,001 · 100.000 = −2.140 JPY/Lot → /121,0176006 · 0,40 · 3 = −21,22.
    Do 10:00: EURUSD Bid 1,10250 (Mitte 1,10255 → Tickwert 0,90698835), USDJPY Ask 109,520 (Mitte 109,510, EURJPY 120,74025050 →
    Tickwert 0,82822422). Gewinn EURUSD 238 Ticks · 0,90698835 · 0,53 = 114,4075… → 114,41; USDJPY 480 · 0,82822422 · 0,40 =
    159,0190… → 159,02. Kommission je Seite: Cent(3,25 · 0,53) = 1,72 bzw. Cent(3,25 · 0,40) = 1,30.
    Trade EURUSD: 114,41 − 2 · 1,72 − 10,84 = 100,13 EUR; Trade USDJPY: 159,02 − 2 · 1,30 − 21,22 = 135,20 EUR."""
    uhr = Uhr(MI_10 + 3600)
    profil = _profil("3.25", EURUSD=("-7.50", "1.20"), USDJPY=("9.80", "-21.40"))
    t = BacktestTerminal(["EURUSD", "USDJPY"], kostenprofil=profil, balance=D(10000), uhr=uhr)
    t.kerze_spielen(Bar("EURUSD", MI_10, D("1.09990"), D("1.10010"), D("1.09980"), D("1.10000"), 12))
    t.kerze_spielen(Bar("USDJPY", MI_10, D("109.990"), D("110.010"), D("109.980"), D("110.000"), 20))
    t.umrechnung_aktualisieren()
    assert t.specs["EURUSD"].tick_value == D("0.90904133") and t.specs["USDJPY"].tick_value == D("0.82632608")
    m1, m2 = ids.magic(ids.Namensraum.STRATEGIE, "hand-1"), ids.magic(ids.Namensraum.STRATEGIE, "hand-2")
    kauf = t.send(OrderRequest(Action.ENTRY_DEAL, "EURUSD", Side.BUY, D("0.53"), m1, sl=D("1.09500"), tp=D("1.11000")))
    verkauf = t.send(OrderRequest(Action.ENTRY_DEAL, "USDJPY", Side.SELL, D("0.40"), m2, sl=D("111.000"), tp=D("108.000")))
    assert kauf.price == D("1.10012") and verkauf.price == D("110.000")
    uhr.t = MI_NACHT
    t.swap_buchen(kosten.swap_faktor(kosten.wochentag_der_nacht(MI_NACHT, 10800)))
    uhr.t = DO_10 + 3600
    t.kerze_spielen(Bar("EURUSD", DO_10, D("1.10200"), D("1.10260"), D("1.10190"), D("1.10250"), 10))
    t.kerze_spielen(Bar("USDJPY", DO_10, D("109.600"), D("109.650"), D("109.480"), D("109.500"), 20))
    t.umrechnung_aktualisieren()
    assert t.specs["EURUSD"].tick_value == D("0.90698835") and t.specs["USDJPY"].tick_value == D("0.82822422")
    t.send(OrderRequest(Action.REDUCE_DEAL, "EURUSD", Side.SELL, D("0.53"), m1, ticket=kauf.order))
    t.send(OrderRequest(Action.REDUCE_DEAL, "USDJPY", Side.BUY, D("0.40"), m2, ticket=verkauf.order))
    je_pos = {}
    for d in t.deals(0, 2**62):
        je_pos.setdefault(d.position_id, []).append(d)
    eu, uj = je_pos[kauf.order], je_pos[verkauf.order]
    assert [(d.profit, d.commission, d.swap) for d in eu] == [(D(0), D("-1.72"), D(0)), (D("114.41"), D("-1.72"), D("-10.84"))]
    assert [(d.profit, d.commission, d.swap) for d in uj] == [(D(0), D("-1.30"), D(0)), (D("159.02"), D("-1.30"), D("-21.22"))]
    assert sum(d.geld for d in eu) == D("100.13") and sum(d.geld for d in uj) == D("135.20")
    assert t.balance == D("10235.33")


# ---------------------------------------------------------------------------------------------------- Runner
@pytest.fixture(scope="module")
def lauf_rev01(tmp_path_factory):
    h1 = bh.markt(wochen=6, saat=3, sigma=0.0025)
    profil = _profil("3.25", **{s: ("-5", "1") for s in bh.STARTKURSE})
    strat = MittelwertRueckkehr(k=2.0, z_tp=0.5, r=2)
    erg = runner.laufen(strat, h1, tmp_path_factory.mktemp("rev01"), runner.Einstellungen(profil))
    return h1, profil, strat, erg


def test_runner_bilanz_paritaet_band(lauf_rev01):
    h1, profil, strat, erg = lauf_rev01
    assert erg.technik_ok, (erg.sperren, erg.vorfaelle[:3])
    assert len(erg.trades) >= 20 and erg.offen_am_ende == 0
    # Geldbilanz: Equity am Ende = Start + Summe aller Trade-Ergebnisse (Zählregel: alle Deals inkl. Kommission und Swap)
    assert erg.kurve[-1][1] == D(10000) + sum((t.ergebnis for t in erg.trades), D(0))
    assert all(t.risiko > 0 and t.einstieg is not None for t in erg.trades)
    assert Counter(b for t in erg.trades for b in band_pruefen(t.einstieg, tore()["band"])) == Counter()
    m = Markt(h1, profil)
    tp = paritaet.trade_paritaet(erg.details, m, strat.max_halte_s)
    assert tp["quote"] == 1.0 and tp["geprueft"] == len(erg.trades), tp["abweichungen"][:3]
    sp = paritaet.signal_paritaet(erg.signale, strat, h1, m.schritte)
    assert sp["quote"] == 1.0 and sp["takt"] == len(erg.signale) > 0, sp
    gruende = Counter(s["grund"] for s in erg.signale if s["ergebnis"] == "ABGELEHNT")
    assert "AUSSERHALB_FENSTER" in gruende                       # Handelsfenster wirkt wie im Betrieb
    assert erg.einstieg_nachteil_ticks == [0] * len(erg.trades)    # H1: der Fill ist genau der erwartete Einstieg e der Strategie
    for d in erg.details:                                         # Rastertreue und Stop/Ziel = r = 2 exakt
        assert abs(d.preis_auf - d.sl) == 2 * abs(d.tp - d.preis_auf)


def test_runner_h4_strategie_paritaet(tmp_path):
    h1 = bh.markt(wochen=10, saat=5, sigma=0.0025)
    h4 = {s: bh.verdichten(k, 14400) for s, k in h1.items()}
    profil = _profil("0")
    strat = Fehlausbruch(L=20, z_tp=0.5)
    erg = runner.laufen(strat, h1, tmp_path, runner.Einstellungen(profil), tf_kerzen=h4)
    assert erg.technik_ok and erg.trades
    assert erg.kurve[-1][1] == D(10000) + sum((t.ergebnis for t in erg.trades), D(0)) + _schwebend(erg)
    m = Markt(h1, profil)
    assert paritaet.trade_paritaet(erg.details, m, strat.max_halte_s)["quote"] == 1.0
    assert paritaet.signal_paritaet(erg.signale, strat, h4, m.schritte)["quote"] == 1.0
    assert len(erg.einstieg_nachteil_ticks) == len(erg.trades)     # H4: Spread der H4-Kerze gegen Ask der letzten H1-Kerze (berichtet)
    for t in erg.trades:                                          # H4-Signal nur zu H4-Schlüssen (Serverzeit 00/04/…)
        assert (t.t_auf + 10800) % 14400 == 0


def _schwebend(erg) -> Decimal:
    return D(0) if not erg.offen_am_ende else erg.kurve[-1][1] - D(10000) - sum((t.ergebnis for t in erg.trades), D(0))


def test_vorgriff_waechter():
    uhr = Uhr(MI_10 + 1800)
    t = BacktestTerminal(["EURUSD"], kostenprofil=_profil("0"), balance=D(10000), uhr=uhr)
    bar = Bar("EURUSD", MI_10, D("1.1"), D("1.1"), D("1.1"), D("1.1"), 5)
    with pytest.raises(VorgriffFehler):
        t.kerze_spielen(bar)                                      # Schluss liegt nach der Uhr
    with pytest.raises(VorgriffFehler):
        t.zeitrahmen_kerze(replace(bar, time=MI_10 - 7200), "H4")  # H4 endet erst 2 h nach jetzt
    uhr.t = MI_10 + 3600
    t.kerze_spielen(bar)
    assert t.bars("EURUSD", "H1", 0, MI_10 + 3600) == [bar]


def test_schattenereignisse_rechnen_weiter(tmp_path):
    """Ein Dauerkauf im Abwärtstrend: STOP50 und LOSS_LOCK werden als Schatten gebucht, der Takt sperrt nicht und handelt weiter."""
    eur = bh.h1_reihe("EURUSD", stunden=24 * 7 * 8, saat=11, sigma=0.0004, drift=-0.0002)
    plan = {("EURUSD", b.time): (Side.BUY, 200, 5000) for b in eur if 7 <= (b.time // 3600) % 24 <= 15}
    strat = bh.FesteSignale(plan)
    erg = runner.laufen(strat, {"EURUSD": eur}, tmp_path, runner.Einstellungen(_profil("0")))
    arten = [s["art"] for s in erg.schatten]
    assert "STOP50" in arten and "LOSS_LOCK" in arten, erg.schatten
    assert erg.sperren == [] and erg.technik_ok
    erstes = min(s["t"] for s in erg.schatten)
    assert any(t.t_auf > erstes for t in erg.trades)              # nach dem ersten Ereignis wird weiter gehandelt
    assert erg.tagesstopps >= 0 and any(s["grund"] == "TAGESBUDGET" for s in erg.signale)


# ---------------------------------------------------------------------------------------------------- Zufallsreferenz, Mutationen
def _zufallsreferenz(erg, h1, profil) -> tuple[float, float, float, int]:
    """(Ø Netto je Lot, erwartete Kosten je Lot, Standardfehler, n): Kosten = ein Spread (Kauf beim Einstieg, Verkauf beim
    Ausstieg, Ø Kerzenspread laut Daten) + Kommission beider Seiten; Swap ist im Test 0."""
    netto = [float(d.ergebnis / d.lots) for d in erg.details]
    tv = [float(d.tick_value_auf) for d in erg.details]
    spread = sum(b.spread_points for b in h1["EURUSD"]) / len(h1["EURUSD"])
    kosten_je_lot = spread * sum(tv) / len(tv) + 2 * float(profil.provision())
    n = len(netto)
    mittel = sum(netto) / n
    se = math.sqrt(sum((x - mittel) ** 2 for x in netto) / (n - 1) / n)
    return mittel, kosten_je_lot, se, n


def _zufallsreferenz_ok(mittel: float, kosten_je_lot: float, se: float) -> bool:
    return abs(mittel + kosten_je_lot) <= 4 * se and mittel < 0


@pytest.fixture(scope="module")
def zufallsmarkt():
    return {"EURUSD": bh.h1_reihe("EURUSD", stunden=24 * 7 * 24, saat=21, sigma=0.0003, spread=20)}


def test_zufallsreferenz_netto_gleich_minus_kosten(tmp_path, zufallsmarkt):
    profil = _profil("3.25")
    erg = runner.laufen(bh.Zufallsrichtung(sl_ticks=100, tp_ticks=100), zufallsmarkt, tmp_path, runner.Einstellungen(profil))
    mittel, k, se, n = _zufallsreferenz(erg, zufallsmarkt, profil)
    assert n >= 500 and k > 8 * se                                 # Test trennscharf: Kosten deutlich über dem Rauschen
    assert _zufallsreferenz_ok(mittel, k, se), (mittel, k, se, n)


def test_mutation_kosten_aus_wird_erkannt(tmp_path, zufallsmarkt, monkeypatch):
    original = BacktestTerminal.kerze_spielen
    monkeypatch.setattr(BacktestTerminal, "kerze_spielen", lambda self, bar: original(self, replace(bar, spread_points=0)))
    profil = _profil("0")                                         # Mutation: Spread und Kommission fallen weg
    erg = runner.laufen(bh.Zufallsrichtung(sl_ticks=100, tp_ticks=100), zufallsmarkt, tmp_path, runner.Einstellungen(profil))
    mittel, _, se, _ = _zufallsreferenz(erg, zufallsmarkt, profil)
    erwartet = _zufallsreferenz(erg, zufallsmarkt, _profil("3.25"))[1]   # Kosten laut Daten und Profil
    assert not _zufallsreferenz_ok(mittel, erwartet, se)


def test_schnelle_zufallsreferenz_viele_einstiege(zufallsmarkt):
    """Ausstiegsrechnung (Zufallsbasis) auf 3.000 zufälligen Einstiegen (mit Zurücklegen): Ø Netto je Lot ≈ −Kosten; ohne Kosten ≈ 0."""
    rng = random.Random(5)
    for prov, mit_kosten in (("3.25", True), ("0", False)):
        profil = _profil(prov)
        m = Markt(zufallsmarkt if mit_kosten else {"EURUSD": [replace(b, spread_points=0) for b in zufallsmarkt["EURUSD"]]}, profil)
        netto = []
        for t in rng.choices(m.schritte[:-30], k=3000):
            bid, ask = m.kurs("EURUSD", t)
            side = Side.BUY if rng.random() < 0.5 else Side.SELL
            e = ask if side is Side.BUY else bid
            a = simulieren(m, "EURUSD", side, e, e - side.sign * D("0.00100"), e + side.sign * D("0.00100"), D(1), t, 3 * 3600)
            netto.append(float(a.ergebnis))
        mittel = sum(netto) / len(netto)
        se = math.sqrt(sum((x - mittel) ** 2 for x in netto) / (len(netto) - 1) / len(netto))
        kosten_je_lot = 20 * 0.9 + 2 * float(prov) if mit_kosten else 0.0     # ~20 Points · Tickwert ≈ 0,9 + Kommission
        assert abs(mittel + kosten_je_lot) <= 4 * se + 1.0, (prov, mittel, kosten_je_lot, se)
    kauf, verkauf = zufallspaar(m, "EURUSD", m.schritte[100], D("0.00100"), D("0.00100"), D(1), 3 * 3600)
    assert isinstance(kauf, bool) and isinstance(verkauf, bool)


def test_mutation_lot_aufrunden_wird_erkannt(tmp_path, monkeypatch):
    original = bandmod._raster

    def aufrunden(lots, spec, *, auf):
        r = original(lots, spec, auf=auf)
        return r + spec.volume_step if auf else r                # Mutation: Mindestgröße einen Schritt zu groß
    monkeypatch.setattr(bandmod, "_raster", aufrunden)
    h1 = bh.markt(("EURUSD", "GBPUSD"), wochen=5, saat=3, sigma=0.0025)
    erg = runner.laufen(MittelwertRueckkehr(symbole=("EURUSD", "GBPUSD")), h1, tmp_path, runner.Einstellungen(_profil("0")))
    befunde = Counter(b for t in erg.trades for b in band_pruefen(t.einstieg, tore()["band"]))
    assert erg.trades and befunde["LOT_NICHT_MINIMAL"] == len(erg.trades)


def test_speicherjournal_gleich_dateijournal(tmp_path):
    """Das Speicherjournal des Backtests liefert dieselben Sätze (inkl. Hashkette) und dieselben Ergebnisse wie das Dateijournal."""
    from kit.state.journal import lesen
    h1 = bh.markt(("EURUSD", "USDJPY"), wochen=5, saat=3, sigma=0.0025)
    profil = _profil("3.25", EURUSD=("-5", "1"), USDJPY=("2", "-6"))
    strat = MittelwertRueckkehr(symbole=("EURUSD", "USDJPY"))
    datei = runner.laufen(strat, h1, tmp_path / "datei", runner.Einstellungen(profil), speicher_journal=False)
    speicher = runner.laufen(strat, h1, tmp_path / "speicher", runner.Einstellungen(profil))
    assert datei.trades and (datei.trades, datei.signale, datei.kurve) == (speicher.trades, speicher.signale, speicher.kurve)
    assert not any((tmp_path / "speicher" / "journal").glob("*.jsonl"))
    saetze = lesen(tmp_path / "datei" / "journal")
    assert [s["art"] for s in saetze].count("DEAL") == 2 * len(datei.trades)
