"""Präfix-Invarianz und Lecktest des Datensatz-Bauers der Runde 3 (Prereg F05B §3, Muster referenz/oracles/t09_causal.py): Für ≥ 200
feindliche Suffixe sind alle Zeilen mit Entscheidung bis zum Präfixende (Punkt, gespiegelte SL/TP, Merkmale, Geometrie) bytegleich zum
Datensatz nur auf dem Präfix; beide Labels nur dort, wo beide Ausstiege schon im Präfix lagen. Lecktest: Fensterschnitt bis i+6 wird
erkannt. Geprüft wird kit.research.richtung.datensatz (H1 und H4) mit demselben Fensterschnitt wie die Signal-Parität im Takt."""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit.backtest import paritaet, runner
from kit.backtest.ausstieg import Markt
from kit.backtest.kosten import Kostenprofil
from kit.domain.types import Side
from kit.research import meta
from kit.research import richtung as ri
from kit.strategy import meta_filter as mf
from kit.strategy import richtung as rf
from kit.strategy.base import Signal
from kit_tests import backtest_hilfen as bh
from kit_tests.differenz_v4.test_meta_praefix import P_H4, SIGNAL_AB, SUFFIX_MAX, SUFFIX_MAX_H4, P, _kerzen, _stunden
from oracles import t09_causal

D = Decimal
KONF = runner.bot_konfiguration()


class Spaet:
    """Basis ohne Idee: Signal an jeder Kerze ab einem Zeitpunkt, Richtung abwechselnd, Ziel 100 / Stop 150 Ticks."""

    name, rueckblick, symbole, max_halte_s = "TEST-SPAET-R", 250, ("EURUSD",), 6 * 3600.0
    L = 20

    def __init__(self, ab: int, zeitrahmen: str = "H1") -> None:
        self.ab, self.zeitrahmen = ab, zeitrahmen

    def parameter(self) -> dict:
        return {"ab": self.ab}

    def signal(self, symbol, kerzen):
        k = kerzen[-1]
        if k.time < self.ab:
            return None
        side = Side.BUY if (k.time // 3600) % 2 else Side.SELL
        e = rf.einstieg(k, side)
        return Signal(symbol, side, e - side.sign * D("0.00150"), e + side.sign * D("0.00100"), k.time, "spaet")


def _zeilen(kerzen, ab: int, tf: str) -> list[dict]:
    profil = Kostenprofil("praefix", D(0))
    h1 = {"EURUSD": kerzen}
    h4 = {"EURUSD": bh.verdichten(kerzen, 14400)} if tf == "H4" else None
    art = "REV02" if tf == "H4" else "REV01"
    return ri.datensatz(Spaet(ab, tf), art, meta.takt_kerzen(h1, h4, tf, profil), Markt(h1, profil), KONF)[0]


def _ausschnitt(zeilen, ende: int, mit_label: set) -> list[tuple]:
    aus = []
    for z in zeilen:
        if z["t_ent"] > ende:
            continue
        kern = (z["symbol"], z["t_kerze"], z["t_ent"], z["basis_side"], z["sl_k"], z["tp_k"], z["sl_v"], z["tp_v"], tuple(z["x"]),
                z["geometrie"])
        if z["t_kerze"] in mit_label:
            kern += (z["label_k"], z["label_v"], z["t_exit_k"], z["t_exit_v"])
        aus.append(kern)
    return aus


def _verstoesse(n_max: int | None = None, tf: str = "H1") -> tuple[list[str], int]:
    n, suffix_max = (P, SUFFIX_MAX) if tf == "H1" else (P_H4, SUFFIX_MAX_H4)
    werte = t09_causal.base_series(9, n)
    zeiten = _stunden(bh.MONTAG, n + suffix_max)
    praefix = _kerzen(zeiten[:n], werte, None)
    ab = praefix[SIGNAL_AB].time if tf == "H1" else praefix[n - 4 * 30].time
    ende = praefix[-1].time + 3600
    basis_zeilen = _zeilen(praefix, ab, tf)
    entschieden = {z["t_kerze"] for z in basis_zeilen if z["t_exit"] is not None}
    basis = _ausschnitt(basis_zeilen, ende, entschieden)
    namen = mf.MERKMALE_REV02 if tf == "H4" else mf.MERKMALE
    assert len(basis) >= 10 and len(entschieden) >= 5 and all(len(b[8]) == len(namen) for b in basis)
    suffixe = t09_causal.suffixes(werte)
    assert len(suffixe) >= t09_causal.MIN_SUFFIXES
    verstoesse = []
    for name, folge in suffixe[:n_max]:
        rest = _kerzen(zeiten[n:], list(folge[:suffix_max]), praefix[-1].close)
        if _ausschnitt(_zeilen(praefix + rest, ab, tf), ende, entschieden) != basis:
            verstoesse.append(name)
    return verstoesse, len(suffixe[:n_max])


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_richtungsdatensatz_praefix_invariant_t09_suffixe(tf):
    verstoesse, n = _verstoesse(tf=tf)
    assert n >= 200 and verstoesse == []


@pytest.mark.parametrize("tf", ["H1", "H4"])
def test_lecktest_fensterschnitt_bis_i_plus_6_wird_erkannt(monkeypatch, tf):
    original = paritaet.signal_fenster

    def mit_vorgriff(zeitrahmen, rueckblick, kerzen, schritte):
        for i, jetzt, _ in original(zeitrahmen, rueckblick, kerzen, schritte):
            yield i, jetzt, list(kerzen[max(0, i + 7 - rueckblick):i + 7])
    monkeypatch.setattr(paritaet, "signal_fenster", mit_vorgriff)
    verstoesse, _ = _verstoesse(n_max=40, tf=tf)
    assert len(verstoesse) >= 20 and {"jump-up-50-5", "jump-down-50-5", "trend-up-60"} <= set(verstoesse)
