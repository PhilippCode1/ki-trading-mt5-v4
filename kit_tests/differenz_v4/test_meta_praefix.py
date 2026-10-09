"""Präfix-Invarianz und Lecktest des Datensatz-Bauers der Runde 2 (Prereg F-05 §3) nach dem Muster von referenz/oracles/t09_causal.py:
Für ≥ 200 feindliche Suffixe hinter dem Präfixende sind alle Datensatzzeilen mit Entscheidung bis zum Präfixende (Signal, SL/TP,
Einstieg, Merkmale) bytegleich zum Datensatz nur auf dem Präfix; Labels nur dort, wo der Ausstieg schon im Präfix lag (das Label darf
und soll die Zukunft nach der Entscheidung sehen). Lecktest: ein Fensterschnitt bis i+6 (Merkmale aus Kerzen nach t) macht den Test rot.
Geprüft wird der Produktionspfad: meta.datensatz mit paritaet.signal_fenster (derselbe Schnitt wie die Signal-Parität im Takt) – für
S-REV-01 auf H1 und für S-REV-02 auf H4 (Merkmale 11/12, H4-Kerzen mit dem Spread der H1-Kerze desselben Schlusses)."""
from __future__ import annotations

import math
from decimal import Decimal

import pytest

from kit.backtest import paritaet
from kit.backtest.ausstieg import Markt
from kit.backtest.kosten import Kostenprofil
from kit.domain.types import Bar, Side
from kit.research import meta
from kit.strategy import meta_filter as mf
from kit.strategy.base import Signal
from kit_tests import backtest_hilfen as bh
from oracles import t09_causal

P_H4 = 4 * (mf.FENSTER + 40)  # H1-Kerzen für ≥ 560 H4-Kerzen (Merkmalsfenster 520 H4 + Signale am Ende)
SUFFIX_MAX_H4 = 32           # 8 H4-Kerzen hinter der Grenze

D = Decimal
P = mf.FENSTER + 120         # Präfixkerzen (H1, Handelsstunden): Merkmalsfenster + Signale am Ende
SUFFIX_MAX = 12              # genug Kerzen hinter der Grenze für einen Vorgriff bis i+6
SIGNAL_AB = P - 40           # Signale nur an den letzten 40 Präfixkerzen (und im Suffix) – hält den Test schnell


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
        aus.append(Bar("EURUSD", t, o, max(o, c) + D("0.00020"), min(o, c) - D("0.00020"), c, 10 + len(aus) % 7))
        vorher = c
    return aus


class Spaet:
    """Basis ohne Idee: Signal an jeder Kerze ab einem Zeitpunkt, Richtung abwechselnd, SL/TP fest um den Einstieg."""

    name, rueckblick, symbole, max_halte_s = "TEST-SPAET", 250, ("EURUSD",), 6 * 3600.0
    L = 20                                                       # Spannenlänge für die Merkmale 11/12 (Art REV02)

    def __init__(self, ab: int, zeitrahmen: str = "H1") -> None:
        self.ab, self.zeitrahmen = ab, zeitrahmen

    def parameter(self) -> dict:
        return {"ab": self.ab}

    def signal(self, symbol, kerzen):
        k = kerzen[-1]
        if k.time < self.ab:
            return None
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        e = k.close + k.spread_points * D("0.00001") if side is Side.BUY else k.close
        return Signal(symbol, side, e - side.sign * D("0.00150"), e + side.sign * D("0.00100"), k.time, "spaet")


def _zeilen(kerzen: list[Bar], ab: int, tf: str = "H1") -> list[dict]:
    profil = Kostenprofil("praefix", D(0))
    h1 = {"EURUSD": kerzen}
    h4 = {"EURUSD": bh.verdichten(kerzen, 14400)} if tf == "H4" else None
    art = "REV02" if tf == "H4" else "REV01"
    zeilen, _ = meta.datensatz(Spaet(ab, tf), art, meta.takt_kerzen(h1, h4, tf, profil), Markt(h1, profil))
    return zeilen


def _ausschnitt(zeilen: list[dict], ende: int, mit_label: set | None = None) -> list[tuple]:
    aus = []
    for z in zeilen:
        if z["t_ent"] > ende:
            continue
        kern = (z["symbol"], z["t_kerze"], z["t_ent"], z["side"], z["sl"], z["tp"], z["preis_auf"], tuple(z["x"]), z["takt_moeglich"])
        if mit_label is not None and z["t_kerze"] in mit_label:
            kern += (z["label"], z["t_exit"], z["grund"], z["ergebnis"])
        aus.append(kern)
    return aus


def _verstoesse(n_max: int | None = None, tf: str = "H1") -> tuple[list[str], int]:
    n, suffix_max = (P, SUFFIX_MAX) if tf == "H1" else (P_H4, SUFFIX_MAX_H4)
    werte = t09_causal.base_series(7, n)
    zeiten = _stunden(bh.MONTAG, n + suffix_max)
    praefix = _kerzen(zeiten[:n], werte, None)
    assert len(praefix) == n
    ab = praefix[SIGNAL_AB].time if tf == "H1" else praefix[n - 4 * 30].time       # H4: Signale an den letzten ~30 H4-Kerzen
    ende = praefix[-1].time + 3600
    basis_zeilen = _zeilen(praefix, ab, tf)
    entschieden = {z["t_kerze"] for z in basis_zeilen if z["t_exit"] is not None}          # Ausstieg schon im Präfix
    basis = _ausschnitt(basis_zeilen, ende, entschieden)
    namen = mf.MERKMALE_REV02 if tf == "H4" else mf.MERKMALE
    assert len(basis) >= 25 and len(entschieden) >= 10 and all(len(b[7]) == len(namen) for b in basis)
    suffixe = t09_causal.suffixes(werte)
    assert len(suffixe) >= t09_causal.MIN_SUFFIXES
    verstoesse = []
    for name, folge in suffixe[:n_max]:
        rest = _kerzen(zeiten[n:], list(folge[:suffix_max]), praefix[-1].close)
        if _ausschnitt(_zeilen(praefix + rest, ab, tf), ende, entschieden) != basis:
            verstoesse.append(name)
    return verstoesse, len(suffixe[:n_max])


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_datensatz_praefix_invariant_t09_suffixe(tf):
    verstoesse, n = _verstoesse(tf=tf)
    assert n >= 200 and verstoesse == []


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_lecktest_fensterschnitt_bis_i_plus_6_wird_erkannt(monkeypatch, tf):
    original = paritaet.signal_fenster

    def mit_vorgriff(zeitrahmen, rueckblick, kerzen, schritte):
        for i, jetzt, _ in original(zeitrahmen, rueckblick, kerzen, schritte):
            # Mutation „Rendite der nächsten 6 Kerzen“: das Fenster endet 6 Kerzen nach der Signalkerze (Merkmale sehen die Zukunft)
            yield i, jetzt, list(kerzen[max(0, i + 7 - rueckblick):i + 7])
    monkeypatch.setattr(paritaet, "signal_fenster", mit_vorgriff)
    verstoesse, n = _verstoesse(n_max=40, tf=tf)
    # Suffixe ohne darstellbare Kerzen (NaN/None/±inf/riesig) verraten nichts; jeder Sprung und Trend muss auffallen
    assert len(verstoesse) >= 20 and {"jump-up-50-5", "jump-down-50-5", "trend-up-60"} <= set(verstoesse)
