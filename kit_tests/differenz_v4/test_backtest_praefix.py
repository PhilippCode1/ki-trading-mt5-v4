"""Präfix-Invarianz des Backtest-Runners nach dem Muster von referenz/oracles/t09_causal.py (≥ 200 feindliche Suffixe):
Alles, was der Takt bis zum Schluss der letzten Präfixkerze sieht oder tut (Signale samt Ablehnungen, geschlossene Trades, Equity),
ist bytegleich zum Lauf nur auf dem Präfix. Mutation „Look-ahead“ (Kurs der nächsten Kerze vor dem Takt) wird erkannt."""
from __future__ import annotations

import math
from decimal import Decimal

from kit.backtest import runner
from kit.backtest.kosten import Kostenprofil
from kit.domain.types import Bar, Side
from kit.strategy.base import Signal
from kit.strategy.rev import MittelwertRueckkehr
from kit_tests import backtest_hilfen as bh
from oracles import t09_causal

D = Decimal
P = 110                      # Präfixkerzen (H1, nur Handelsstunden)
SUFFIX_MAX = 3               # Kerzen je Suffix: Vorgriff wirkt sofort an der Grenze; mehr kostet nur Laufzeit


def _stunden(start: int, n: int) -> list[int]:
    aus, t = [], start
    while len(aus) < n:
        if bh.offen(t):
            aus.append(t)
        t += 3600
    return aus


def _kerzen(zeiten: list[int], werte: list, vorher: Decimal | None) -> list[Bar]:
    """Preise 1,1 · w/100; nicht darstellbare Werte (None, NaN, ±inf, außerhalb 0,01…100) = fehlende Kerze (Lücke)."""
    aus = []
    for t, w in zip(zeiten, werte, strict=False):
        if w is None or not math.isfinite(w):
            continue
        preis = 1.1 * w / 100
        if not 0.01 <= preis <= 100:
            continue
        c = D(repr(preis)).quantize(D("0.00001"))
        o = vorher if vorher is not None else c
        aus.append(Bar("EURUSD", t, o, max(o, c) + D("0.00020"), min(o, c) - D("0.00020"), c, 10))
        vorher = c
    return aus


class Kombiniert:
    """S-REV-01 (kurzer Rückblick) plus ein fester Kauf an der letzten Präfixkerze, damit an der Grenze sicher gehandelt wird."""

    def __init__(self, basis: MittelwertRueckkehr, kauf_bei: int) -> None:
        self.basis, self._kauf_bei = basis, kauf_bei
        self.name, self.zeitrahmen, self.rueckblick = "TEST-PRAEFIX", "H1", basis.rueckblick
        self.symbole, self.max_halte_s = ("EURUSD",), basis.max_halte_s

    def parameter(self) -> dict:
        return {"basis": self.basis.parameter(), "kauf_bei": self._kauf_bei}

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        k = kerzen[-1]
        if k.time == self._kauf_bei and len(kerzen) >= self.rueckblick:
            e = k.close + k.spread_points * D("0.00001")
            return Signal(symbol, Side.BUY, e - D("0.00300"), e + D("0.00300"), k.time, "grenze")
        return self.basis.signal(symbol, kerzen)


def _ausschnitt(erg, ende: int) -> tuple:
    return ([(s["symbol"], s["kerze"], s["side"], s["ergebnis"], s["grund"]) for s in erg.signale if s["t"] <= ende],
            [(t.symbol, t.t_auf, t.t_zu, t.ergebnis, t.grund) for t in erg.trades if t.t_zu <= ende],
            [(t, e) for t, e in erg.kurve if t <= ende])


def _verstoesse(tmp_path, n_max: int | None = None) -> tuple[list[str], int]:
    werte = t09_causal.base_series(4, P)
    zeiten = _stunden(bh.MONTAG, P + SUFFIX_MAX)
    praefix = _kerzen(zeiten[:P], werte, None)
    ende = praefix[-1].time + 3600
    strat = Kombiniert(MittelwertRueckkehr(k=2.0, z_tp=0.5, r=2, symbole=("EURUSD",), rueckblick=60), praefix[-1].time)
    profil = Kostenprofil("praefix", D("3.25"))
    basis = _ausschnitt(runner.laufen(strat, {"EURUSD": praefix}, tmp_path / "basis", runner.Einstellungen(profil)), ende)
    assert any(s[3] == "ERLEDIGT" and s[1] == praefix[-1].time for s in basis[0])       # an der Grenze wird gehandelt
    suffixe = t09_causal.suffixes(werte)
    assert len(suffixe) >= t09_causal.MIN_SUFFIXES
    verstoesse = []
    for i, (name, folge) in enumerate(suffixe[:n_max]):
        rest = _kerzen(zeiten[P:], list(folge[:SUFFIX_MAX]), praefix[-1].close)
        erg = runner.laufen(strat, {"EURUSD": praefix + rest}, tmp_path / f"s{i}", runner.Einstellungen(profil))
        if _ausschnitt(erg, ende) != basis:
            verstoesse.append(name)
    return verstoesse, len(suffixe[:n_max])


def test_runner_praefix_invariant_t09_suffixe(tmp_path):
    verstoesse, n = _verstoesse(tmp_path)
    assert n >= 200 and verstoesse == []


def test_mutation_lookahead_wird_erkannt(tmp_path, monkeypatch):
    original = runner._kerzen_abspielen

    def spaehen(term, h1, zeiger, t):
        original(term, h1, zeiger, t)
        for sym, kerzen in h1.items():                    # Mutation: Kurs der NÄCHSTEN Kerze vor dem Takt (am Wächter vorbei)
            if zeiger[sym] < len(kerzen):
                nb = kerzen[zeiger[sym]]
                term.setze_kurs(sym, nb.close, nb.close + term.specs[sym].point * nb.spread_points)
    monkeypatch.setattr(runner, "_kerzen_abspielen", spaehen)
    verstoesse, _ = _verstoesse(tmp_path, n_max=30)
    # Suffixe ohne nächste Kerze (NaN/None) oder mit gleichem Kurs (konstant) können nichts verraten; jeder Sprung muss auffallen.
    assert len(verstoesse) >= 10 and {"jump-up-50-1", "jump-down-50-1", "trend-up-1"} <= set(verstoesse)


# ---------------------------------------------------------------- Review F-04: mehrere Symbole, JPY-Umrechnung, H4, Swap, Kosten × 1,5
def _grenzen(h1: dict, details=()) -> list[int]:
    """Schrittzeiten als Präfixenden: Servertageswechsel (21:00 UTC), letzter Schluss vor dem Wochenende, 22:00 Berlin, weitere und
    drei Schritte, an denen im Volllauf eine JPY-Position offen ist (dort wirken Umrechnung und Tickwerte auf die Equity)."""
    schritte = sorted({b.time + 3600 for k in h1.values() for b in k})
    jpy = [g for d in details if d.symbol.endswith("JPY") for g in schritte if d.t_auf < g < d.t_zu][:: 7][:3]
    mitternacht = [t for t in schritte if (t + 3 * 3600) % 86400 == 0][3:5]
    freitag = [a for a, b in zip(schritte, schritte[1:], strict=False) if b - a > 24 * 3600][1:2]
    abends = [t for t in schritte if (t // 3600) % 24 == 20][6:7]
    return sorted(set(mitternacht + freitag + abends + jpy + [schritte[len(schritte) // 2], schritte[-30]]))


def _kurz(erg, ende: int) -> tuple:
    return (*_ausschnitt(erg, ende), [(s["art"], s["t"]) for s in erg.schatten if s["t"] <= ende],
            [(t.symbol, t.t_auf, t.risiko, t.einstieg) for t in erg.trades if t.t_zu <= ende])


def _mehrfach_verstoesse(tmp_path) -> tuple[list[int], int]:
    from kit.strategy.rev import Fehlausbruch
    symbole = ("EURUSD", "USDJPY", "CHFJPY")
    h1 = bh.markt(symbole, wochen=8, saat=13, sigma=0.0025)
    h4 = {s: bh.verdichten(k, 14400) for s, k in h1.items()}
    profil = Kostenprofil("praefix", D("3.25"), {"EURUSD": (D("-6.5"), D("2.1")), "USDJPY": (D("8"), D("-17")),
                                                "CHFJPY": (D("-10"), D("4"))}).mal("1.5")
    strat = Fehlausbruch(L=20, z_tp=0.5, symbole=symbole, rueckblick=60)
    voll = runner.laufen(strat, h1, tmp_path / "voll", runner.Einstellungen(profil), tf_kerzen=h4)
    assert voll.trades and any(d.swap != 0 for d in voll.details)                  # Swap und Trades kommen vor
    grenzen = _grenzen(h1, voll.details)
    assert len(grenzen) >= 8
    verstoesse = []
    for i, g in enumerate(grenzen):
        p1 = {s: [b for b in k if b.time + 3600 <= g] for s, k in h1.items()}
        p4 = {s: [b for b in k if b.time + 14400 <= g] for s, k in h4.items()}
        erg = runner.laufen(strat, p1, tmp_path / f"p{i}", runner.Einstellungen(profil), tf_kerzen=p4)
        if _kurz(erg, g) != _kurz(voll, g):
            verstoesse.append(g)
    return verstoesse, len(grenzen)


def test_runner_praefix_mehrere_symbole_h4_swap(tmp_path):
    verstoesse, n = _mehrfach_verstoesse(tmp_path)
    assert n >= 5 and verstoesse == []


def test_mutation_lookahead_nur_usdjpy_wird_erkannt(tmp_path, monkeypatch):
    original = runner._kerzen_abspielen

    def spaehen(term, h1, zeiger, t):
        original(term, h1, zeiger, t)
        kerzen = h1.get("USDJPY", [])
        if zeiger.get("USDJPY", 0) < len(kerzen):           # Mutation: nur der Umrechnungskurs USDJPY kommt aus der nächsten Kerze
            nb = kerzen[zeiger["USDJPY"]]
            term.setze_kurs("USDJPY", nb.close, nb.close + term.specs["USDJPY"].point * nb.spread_points)
    monkeypatch.setattr(runner, "_kerzen_abspielen", spaehen)
    verstoesse, n = _mehrfach_verstoesse(tmp_path)
    assert len(verstoesse) >= 3                    # mindestens dort, wo eine JPY-Position offen ist, verrät der Vorgriff sich
