"""S-BL-01 Referenz BL-TFD1 (D1, docs/bot/prereg/F04_ENTWURF.md §4): Donchian-Kanalkreuzung mit ATR-Anfangsstopp und Nachführung.

Herkunft: Semantik aus referenz/reference/research/baseline.py (Regeln R1–R8, RA-1/RA-2), hier eigenständig neu geschrieben
(kit importiert die Referenz nie); Orakel referenz/oracles/tfd1_oracle.py (Differenztest kit_tests/differenz_v4). float-Rechnung
in derselben Reihenfolge wie die Referenz, damit Trades bitgleich sind. Kein Server-TP → läuft nie über den Takt und zählt nie
für das 85-%-Tor (nur Vergleich und Plausibilitätsanker).

Regeln je Kerze t (Reihenfolge): (0) fälliger Einstieg zur Eröffnung t ± halber Spread (verkürzte Sitzung bzw. offene Position →
ENTRY_NOT_EXECUTABLE, ungültige Kerze → ENTRY_DATA_GAP_REPLAY, keine Nachholung), Anfangsstopp = Fill ∓ stop_k·ATR(Signalkerze);
(1) Stopp-Prüfung nur auf gültigen Kerzen (Long auf Bid, Short auf Ask; Eröffnungslücke → Fill zur Eröffnung; Einstiegskerze
'full_bar' mit Tief/Hoch bzw. 'close_only' mit Schluss, dort ohne Lückenregel); (2) Nachführung auf min(Low)/max(High) der
trail_n Kerzen bis t, nur enger, nur bei lückenlosem Fenster; (3) Signal: Schluss kreuzt den Kanal der entry_n Kerzen vor t
(Long C_t > U_t und C_{t−1} ≤ U_{t−1}, Short spiegelbildlich), nur aus gültigen Kerzen t und t−1 mit lückenlosen Fenstern und ATR;
Ausführung in t+1, nur ohne offene Position. ATR: Wilder über gültige Kerzen (TR mit dem Schluss der letzten gültigen Kerze),
Start = Mittel der ersten atr_n TR; ungültige Kerzen ändern den Zustand nicht."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Kerze:
    high: float
    low: float
    close: float
    open: float
    valid: bool = True
    short_session: bool = False


@dataclass(frozen=True)
class Params:
    entry_n: int = 55
    trail_n: int = 20
    atr_n: int = 20
    stop_k: float = 2.0
    entry_bar_mode: str = "full_bar"

    def __post_init__(self) -> None:
        if min(self.entry_n, self.trail_n, self.atr_n) < 1 or self.stop_k <= 0:
            raise ValueError("Parameter")
        if self.entry_bar_mode not in ("full_bar", "close_only"):
            raise ValueError("entry_bar_mode")


@dataclass
class Trade:
    direction: int
    signal_bar: int
    entry_bar: int
    entry_price: float
    initial_stop: float
    stop_distance: float
    stop: float
    exit_bar: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None


@dataclass
class Lauf:
    trades: list[Trade] = field(default_factory=list)          # geschlossene Trades
    open_trade: Trade | None = None
    blocked: dict = field(default_factory=dict)                 # Sperrgrund → Anzahl
    stops: list[float | None] = field(default_factory=list)    # Stopp nach dem Schluss je Kerze
    signals: list[int] = field(default_factory=list)            # +1 / −1 / 0 je Kerze


def atr_reihe(kerzen: Sequence[Kerze], n: int) -> list[float | None]:
    """Wilder-ATR je Kerze (None bei ungültiger Kerze und vor dem Start)."""
    out: list[float | None] = []
    erste: list[float] = []
    atr: float | None = None
    schluss: float | None = None
    for k in kerzen:
        if not k.valid:
            out.append(None)
            continue
        tr = k.high - k.low if schluss is None else max(k.high - k.low, abs(k.high - schluss), abs(k.low - schluss))
        schluss = k.close
        if atr is None:
            erste.append(tr)
            if len(erste) == n:
                atr = sum(erste) / n
        else:
            atr = ((n - 1) * atr + tr) / n
        out.append(atr)
    return out


def kanal(kerzen: Sequence[Kerze], ende: int, n: int, oben: bool) -> float | None:
    """max(High) bzw. min(Low) der Kerzen ende−n … ende−1; None bei zu kurzem oder lückenhaftem Fenster."""
    if ende < n or ende > len(kerzen):
        return None
    fenster = kerzen[ende - n:ende]
    for k in fenster:
        if not k.valid:
            return None
    return max(k.high for k in fenster) if oben else min(k.low for k in fenster)


def _signal(kerzen: Sequence[Kerze], atr: Sequence[float | None], t: int, n: int) -> tuple[int, str | None]:
    if not kerzen[t].valid:
        return 0, "BAR_INVALID"
    if t < 1 or not kerzen[t - 1].valid:
        return 0, "PREV_BAR_INVALID"
    grenzen = (kanal(kerzen, t, n, True), kanal(kerzen, t, n, False), kanal(kerzen, t - 1, n, True), kanal(kerzen, t - 1, n, False))
    if any(g is None for g in grenzen):
        return 0, "GAP_OR_WARMUP_IN_ENTRY_WINDOW"
    if atr[t] is None:
        return 0, "ATR_UNAVAILABLE"
    oben_t, unten_t, oben_v, unten_v = grenzen
    c, cv = kerzen[t].close, kerzen[t - 1].close
    lang = c > oben_t and cv <= oben_v
    kurz = c < unten_t and cv >= unten_v
    if lang == kurz:
        return 0, None
    return (1 if lang else -1), None


def _stopp_fill(k: Kerze, richtung: int, stopp: float, hs: float, einstiegskerze: bool, modus: str) -> float | None:
    """Ausstiegskurs, wenn die Kerze den Stopp erreicht (Long auf Bid = Mitte − hs, Short auf Ask = Mitte + hs), sonst None."""
    nur_schluss = einstiegskerze and modus == "close_only"
    if richtung > 0:
        eroeffnung = k.open - hs
        if not einstiegskerze and eroeffnung <= stopp:
            return eroeffnung
        probe = k.close - hs if nur_schluss else k.low - hs
        return stopp if probe <= stopp else None
    eroeffnung = k.open + hs
    if not einstiegskerze and eroeffnung >= stopp:
        return eroeffnung
    probe = k.close + hs if nur_schluss else k.high + hs
    return stopp if probe >= stopp else None


def _zaehlen(blocked: dict, grund: str) -> None:
    blocked[grund] = blocked.get(grund, 0) + 1


def run(kerzen: Sequence[Kerze], half_spread: float, p: Params | None = None) -> Lauf:
    """BL-TFD1 über die ganze Reihe (Mid-Preise; half_spread = halber Spread in Preiseinheiten)."""
    p = p or Params()
    atr = atr_reihe(kerzen, p.atr_n)
    lauf = Lauf()
    pos: Trade | None = None
    faellig: tuple[int, int] | None = None                      # (Richtung, Signalkerze), Ausführung in der Folgekerze
    for t, k in enumerate(kerzen):
        neu = False
        if faellig is not None:                                  # (0) fälliger Einstieg
            richtung, sig = faellig
            faellig = None
            if pos is None and k.valid and not k.short_session:
                abstand = p.stop_k * atr[sig]
                px = k.open + half_spread if richtung > 0 else k.open - half_spread
                stopp = px - abstand if richtung > 0 else px + abstand
                pos = Trade(richtung, sig, t, px, stopp, abstand, stopp)
                neu = True
            elif pos is not None or k.short_session:
                _zaehlen(lauf.blocked, "ENTRY_NOT_EXECUTABLE")
            else:
                _zaehlen(lauf.blocked, "ENTRY_DATA_GAP_REPLAY")
        if pos is not None and k.valid:                          # (1) Stopp-Prüfung
            fill = _stopp_fill(k, pos.direction, pos.stop, half_spread, neu, p.entry_bar_mode)
            if fill is not None:
                pos.exit_bar, pos.exit_price = t, fill
                pos.exit_reason = "INITIAL_STOP" if pos.stop == pos.initial_stop else "TRAIL_STOP"
                lauf.trades.append(pos)
                pos = None
        if pos is not None:                                      # (2) Nachführung (Fenster bis einschließlich t)
            stufe = kanal(kerzen, t + 1, p.trail_n, pos.direction < 0)
            if stufe is not None:
                pos.stop = max(pos.stop, stufe) if pos.direction > 0 else min(pos.stop, stufe)
        lauf.stops.append(pos.stop if pos is not None else None)
        richtung, grund = _signal(kerzen, atr, t, p.entry_n)     # (3) Einstiegssignal
        lauf.signals.append(richtung)
        if grund:
            _zaehlen(lauf.blocked, grund)
        if pos is None and richtung != 0:
            faellig = (richtung, t)
    lauf.open_trade = pos
    return lauf
