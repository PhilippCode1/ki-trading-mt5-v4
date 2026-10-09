"""Parität: der Takt (Backtest-Runner) gegen eine direkte, unabhängige Rechnung derselben Regeln.

- Signal-Parität: Signale, die der Takt ins Journal schreibt (SIGNAL, Namensraum STRATEGIE, angenommen oder abgelehnt), gegen die
  Signale, die die Strategie direkt über die Kerzenreihe liefert – mit derselben Fensterregel wie Bot.handel (Abruf ab
  jetzt − (rueckblick + 5) · tf · 3, nur abgeschlossene Kerzen, nur neue und frische Kerzen: Schluss = Schritt). Soll: 100 %.
- Trade-Parität: jeder geschlossene Trade des Takts gegen kit.backtest.ausstieg.simulieren mit Einstiegskurs, SL, TP und Lots
  des Takts: Ausstiegszeit, -kurs, -grund und Ergebnis auf den Cent. Zwangsausstiege des Takts (Band, K3) bildet die direkte Rechnung
  nicht nach; sie werden getrennt ausgewiesen.
- Später (F-07): Signaltreue Demo-Live gegen den täglichen Schatten-Backtest mit derselben Funktion vergleich().
"""
from __future__ import annotations

import bisect
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace

from kit.backtest.ausstieg import Markt, simulieren
from kit.backtest.runner import TradeDetail
from kit.backtest.terminal import TF_S
from kit.domain.types import Bar
from kit.strategy.base import Strategie

ZWANG = frozenset({"BAND_BODEN", "BAND_DECKEL", "K3", "SONST"})


def signal_fenster(zeitrahmen: str, rueckblick: int, kerzen: Sequence[Bar], schritte: Iterable[int]) -> Iterator[tuple[int, int, list[Bar]]]:
    """Fensterregel von Bot.handel als einzige Quelle für direkte Rechnungen (Signal-Parität, Datensatz F-05): je frischer Kerze i
    (Schluss = Schritt) das Paar (i, Schritt, Fenster) mit Abruf ab Schritt − (rueckblick + 5) · tf · 3, nur Kerzen bis i, die letzten
    rueckblick. Kerzen, deren Schluss kein Schritt ist, würde der Takt erst später sehen (nicht frisch) – kein Fenster."""
    tf = TF_S[zeitrahmen]
    schritt_menge = set(schritte)
    zeiten = [b.time for b in kerzen]
    for i, b in enumerate(kerzen):
        jetzt = b.time + tf
        if jetzt not in schritt_menge:
            continue
        start = int(jetzt - (rueckblick + 5) * tf * 3)
        yield i, jetzt, list(kerzen[bisect.bisect_left(zeiten, start):i + 1][-rueckblick:])


def direkte_signale(strategie: Strategie, symbol: str, kerzen: Sequence[Bar], schritte: Iterable[int], *,
                    spread_points=None) -> list[tuple[str, int, str]]:
    """Signale (Symbol, Kerze, Richtung) wie Bot.handel sie sähe. kerzen = Strategie-Zeitrahmen des Symbols (aufsteigend);
    schritte = Schrittzeiten des Runners (H1-Schlüsse); spread_points = Spread-Abbildung des Kostenprofils (wie im Terminal)."""
    if spread_points is not None:
        kerzen = [replace(b, spread_points=spread_points(b.spread_points)) for b in kerzen]
    aus: list[tuple[str, int, str]] = []
    for _, _, fenster in signal_fenster(strategie.zeitrahmen, strategie.rueckblick, kerzen, schritte):
        sig = strategie.signal(symbol, fenster)
        if sig is not None:
            aus.append((symbol, sig.kerze, str(sig.side)))
    return aus


def vergleich(takt: Iterable[tuple], direkt: Iterable[tuple]) -> dict:
    """Mengenvergleich zweier Signal- bzw. Ereignislisten (Reihenfolge egal, Mehrfache zählen)."""
    a, b = list(takt), list(direkt)
    rest_b = list(b)
    nur_a = []
    for x in a:
        if x in rest_b:
            rest_b.remove(x)
        else:
            nur_a.append(x)
    gleich = len(a) - len(nur_a)
    n = max(len(a), len(b))
    return {"takt": len(a), "direkt": len(b), "gleich": gleich, "nur_takt": nur_a[:20], "nur_direkt": rest_b[:20],
            "quote": 1.0 if n == 0 else gleich / n}


def signal_paritaet(journal_signale: Iterable[dict], strategie: Strategie, kerzen_tf: dict[str, Sequence[Bar]],
                    schritte: Sequence[int], *, spread_points=None) -> dict:
    takt = [(s["symbol"], int(s["kerze"]), str(s["side"])) for s in journal_signale]
    direkt = [x for sym in strategie.symbole if sym in kerzen_tf
              for x in direkte_signale(strategie, sym, kerzen_tf[sym], schritte, spread_points=spread_points)]
    return vergleich(takt, direkt)


def trade_paritaet(details: Iterable[TradeDetail], markt: Markt, max_halte_s: float | None) -> dict:
    """Jeder Takt-Trade gegen die direkte Ausstiegsrechnung. Abweichungen ohne Zwangsausstieg sind Fehler."""
    n = gleich = zwang = 0
    abweichungen: list[dict] = []
    for d in details:
        n += 1
        if d.grund in ZWANG:
            zwang += 1
            continue
        a = simulieren(markt, d.symbol, d.side, d.preis_auf, d.sl, d.tp, d.lots, d.t_auf, max_halte_s)
        if (a.t, a.preis, a.grund, a.ergebnis) == (d.t_zu, d.preis_zu, d.grund, d.ergebnis):
            gleich += 1
        else:
            abweichungen.append({"position_id": d.position_id, "symbol": d.symbol, "takt": [d.t_zu, str(d.preis_zu), d.grund, str(d.ergebnis)],
                                 "direkt": [a.t, str(a.preis), a.grund, str(a.ergebnis)]})
    geprueft = n - zwang
    return {"trades": n, "zwangsausstiege": zwang, "geprueft": geprueft, "gleich": gleich, "abweichungen": abweichungen[:20],
            "quote": 1.0 if geprueft == 0 else gleich / geprueft}

