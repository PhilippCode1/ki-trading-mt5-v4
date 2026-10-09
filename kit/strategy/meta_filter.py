"""KI-Meta-Filter (Runde 2, docs/bot/prereg/F05_ENTWURF.md; Plan F-1 §4): Hülle um eine Basisstrategie, die je Signal die
Wahrscheinlichkeit „Ziel vor Stop“ schätzt und nur Signale über der Schwelle weitergibt. Kein Sprachmodell im Handelspfad.

Nur Standardbibliothek: Merkmale in float, Modelle als eingefrorene JSON-Parameter (logistische Regression, HistGradientBoosting),
gerechnet mit math. Die Wahrscheinlichkeit stimmt mit scikit-learn auf ≤ 1e-9 überein (Paritätstest in kit_tests und beim Training).

Merkmale (Prereg §1) aus genau den übergebenen Kerzen des Strategie-Zeitrahmens (letzte = Signalkerze t), so wie der Takt sie sieht:
Fenster = die letzten FENSTER Kerzen; ATR = Wilder(14) über das ganze Fenster (wie kit.strategy.rev.wilder_atr), ATR_t = letzter Wert.
  (1) (C_t − SMA48)/σ48          (2) σ48/ATR_t        (3) ATR_t/C_t       (4) Anteil der letzten 250 ATR-Werte ≤ ATR_t
  (5) Spread_t/ATR_t             (6) (C_t − C_{t−24})/ATR_t               (7) (SMA48_t − SMA48_{t−12})/ATR_t
  (8) (C_t − min Tief_20)/(max Hoch_20 − min Tief_20) über die letzten 20 Kerzen inkl. t (Spanne 0 → 0,5)
  (9) sin/cos(2π·h/24), h = Stunde des Kerzenbeginns in Berlin   (10) Wochentag Mo–Fr 1-aus-5 (Berliner Datum; Sa/So → alle 0)
  nur S-REV-02: (11) Ausbruchstiefe (Extrem − Spannengrenze)/ATR_t, Spanne = L Kerzen vor t wie in rev.Fehlausbruch
                (12) (Hoch_t − Tief_t)/ATR_t
σ = Populations-Standardabweichung der Schlüsse (wie rev._band); σ = 0 → Merkmal (1) = 0. Zu kurzes Fenster oder ATR_t ≤ 0 /
nicht endlich → keine Merkmale → kein Signal.

Zeitplan: je Testfenster [test_von, test_bis) ein Modell mit Schwelle. Entscheidungszeit t_ent = Beginn der Signalkerze + Zeitrahmen
(der Schritt, an dem der Takt einsteigt). Kein Signal außerhalb aller Fenster, vor embargo_bis (Embargo nach der Anpassung) und
ohne Schwelle; sonst Signal genau dann, wenn p > Schwelle („über der Schwelle“). Die Basis bleibt unverändert (gleiche SL/TP).
Jedes Modell trägt seine Trainingsgrenzen (training: fit_bis, max_t_ent, max_t_exit, val_max_t_exit); die Hülle verweigert fail-closed
ein Modell, dessen Trainings- oder Validierungsdaten in sein Testfenster reichen, sowie überlappende oder offene Fenster vor dem letzten.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from kit.domain import zeit
from kit.domain.types import Bar, Side
from kit.strategy.base import Signal, strategie_hash
from kit.strategy.rev import punkt, wilder_atr

FENSTER = 520                 # Kerzen: ATR-Anlauf 14 + 250 ATR-Werte für (4) + Puffer gegen den Wilder-Startwert
ATR_N = 14
SMA_N = 48
PERZENTIL_N = 250
RENDITE_N = 24
STEIGUNG_N = 12
SPANNE_N = 20
TF_S = {"H1": 3600, "H4": 14400}
MERKMALE = ("abstand_sma48_sigma", "sigma48_atr", "atr_schluss", "atr_perzentil250", "spread_atr", "rendite24_atr",
            "steigung_sma48_12_atr", "lage_spanne20", "stunde_sin", "stunde_cos", "wt_mo", "wt_di", "wt_mi", "wt_do", "wt_fr")
MERKMALE_REV02 = (*MERKMALE, "ausbruchstiefe_atr", "kerzenspanne_atr")
ARTEN = ("REV01", "REV02")


def merkmal_namen(art: str) -> tuple[str, ...]:
    if art not in ARTEN:
        raise ValueError(f"unbekannte Art {art}")
    return MERKMALE_REV02 if art == "REV02" else MERKMALE


def _mittel_sigma(werte: Sequence[float]) -> tuple[float, float]:
    n = len(werte)
    mittel = sum(werte) / n
    return mittel, math.sqrt(sum([(x - mittel) * (x - mittel) for x in werte]) / n)


def merkmale(kerzen: Sequence[Bar], side: Side, art: str, *, spanne_l: int | None = None) -> list[float] | None:
    """Merkmalsvektor (Reihenfolge merkmal_namen(art)) aus den letzten FENSTER Kerzen bis zur Signalkerze t; None = nicht berechenbar."""
    if art not in ARTEN or (art == "REV02" and not spanne_l):
        raise ValueError("Art REV01/REV02 (REV02 mit spanne_l)")
    if len(kerzen) < FENSTER:
        return None
    k = list(kerzen[-FENSTER:])
    atr = wilder_atr(k, ATR_N)
    a = atr[-1]
    if a is None or not math.isfinite(a) or a <= 0:
        return None
    c = [float(b.close) for b in k]
    ct = c[-1]
    sma_t, sigma = _mittel_sigma(c[-SMA_N:])
    sma_vor = sum(c[-SMA_N - STEIGUNG_N:-STEIGUNG_N]) / SMA_N
    letzte = [x for x in atr[-PERZENTIL_N:] if x is not None]
    if len(letzte) < PERZENTIL_N:
        return None
    t = k[-1]
    hoch = max(float(b.high) for b in k[-SPANNE_N:])
    tief = min(float(b.low) for b in k[-SPANNE_N:])
    berlin = zeit.nach_berlin(zeit.aus_epoch(t.time))
    winkel = 2 * math.pi * berlin.hour / 24
    wt = berlin.weekday()
    x = [
        (ct - sma_t) / sigma if sigma > 0 else 0.0,
        sigma / a,
        a / ct,
        sum(1 for v in letzte if v <= a) / PERZENTIL_N,
        float(t.spread_points * punkt(t.symbol)) / a,
        (ct - c[-RENDITE_N - 1]) / a,
        (sma_t - sma_vor) / a,
        (ct - tief) / (hoch - tief) if hoch > tief else 0.5,
        math.sin(winkel),
        math.cos(winkel),
        *[1.0 if wt == i else 0.0 for i in range(5)],
    ]
    if art == "REV02":
        spanne = k[-spanne_l - 1:-1]
        if side is Side.SELL:
            tiefe = float(t.high) - max(float(b.high) for b in spanne)
        else:
            tiefe = min(float(b.low) for b in spanne) - float(t.low)
        x += [tiefe / a, (float(t.high) - float(t.low)) / a]
    return x if all(math.isfinite(v) for v in x) else None


# ---------------------------------------------------------------------------------------------------- Modelle (JSON)
def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _blatt(knoten: Sequence[Sequence], x: Sequence[float]) -> float:
    """Ein Baum von HistGradientBoosting; Knoten [Wert, Merkmal, Schwelle, fehlend_links, links, rechts, Blatt] wie sklearn
    (_predictor: x ≤ num_threshold → links; NaN → missing_go_to_left)."""
    i = 0
    while True:
        wert, merkmal, schwelle, fehlend_links, links, rechts, blatt = knoten[i]
        if blatt:
            return wert
        v = x[merkmal]
        if math.isnan(v):
            i = links if fehlend_links else rechts
        else:
            i = links if v <= schwelle else rechts


def wahrscheinlichkeit(modell: Mapping, x: Sequence[float]) -> float:
    """P(Gewinn) aus einem eingefrorenen Modell: LOGREG (Standardisierung + lineare Funktion) oder HGB (Basis + Blattwerte)."""
    art = modell.get("art")
    if len(x) != len(modell["merkmale"]):
        raise ValueError("Merkmalsanzahl passt nicht zum Modell")
    if art == "LOGREG":
        z = 0.0
        for xi, m, s, c in zip(x, modell["mittel"], modell["skala"], modell["koeffizienten"], strict=True):
            z += c * ((xi - m) / s)
        return _sigmoid(z + modell["achsenabschnitt"])
    if art == "HGB":
        roh = modell["basis"]
        for baum in modell["baeume"]:
            roh += _blatt(baum, x)
        return _sigmoid(roh)
    raise ValueError(f"unbekannte Modellart {art}")


# ---------------------------------------------------------------------------------------------------- Hülle
@dataclass(frozen=True)
class Fenster:
    """Ein Testfenster des Zeitplans: Modell und Schwelle gelten für Entscheidungen mit test_von ≤ t_ent < test_bis (test_bis None =
    offen, Holdout/Betrieb), aber erst ab embargo_bis; schwelle None = in diesem Fenster kein Handel."""

    test_von: int
    test_bis: int | None
    embargo_bis: int
    schwelle: float | None
    modell: Mapping | None


def fenster_pruefen(f: Fenster, art: str, naechstes: Fenster | None = None) -> None:
    """Fail-closed: Embargo im Fenster, Fenster ohne Überlappung (offen nur das letzte), Modell passend zur Art und mit
    Trainingsgrenzen vor dem Testbeginn (kein Trainings- oder Validierungslabel aus dem Testfenster)."""
    if not f.test_von < f.embargo_bis or (f.test_bis is not None and f.embargo_bis > f.test_bis):
        raise ValueError("Embargo liegt nicht im Testfenster")
    if naechstes is not None and (f.test_bis is None or f.test_bis > naechstes.test_von):
        raise ValueError("Testfenster überlappen oder ein offenes Fenster steht nicht am Ende")
    if f.modell is None:
        return
    if tuple(f.modell["merkmale"]) != merkmal_namen(art):
        raise ValueError("Modellmerkmale passen nicht zur Art")
    tr = f.modell.get("training")
    if not isinstance(tr, Mapping):
        raise ValueError("Modell ohne Trainingsgrenzen")
    try:
        ok = (tr["fit_bis"] <= f.test_von and tr["max_t_exit"] <= f.test_von and tr["max_t_ent"] < f.test_von
              and tr["val_max_t_exit"] <= f.test_von and tr["val_von"] < tr["fit_bis"])
    except (KeyError, TypeError) as exc:
        raise ValueError("Modell ohne vollständige Trainingsgrenzen") from exc
    if not ok:
        raise ValueError("Trainings- oder Validierungsdaten des Modells reichen ins Testfenster")


class MetaFilter:
    """Strategie-Hülle: gleiche Symbole, Zeitrahmen und Zeitbarriere wie die Basis; rueckblick = max(Basis, FENSTER). Die Basis
    erhält wie im Takt genau ihre letzten rueckblick Kerzen."""

    def __init__(self, basis, fenster: Sequence[Fenster], *, art: str, name: str, modell_sha: str = "") -> None:
        merkmal_namen(art)
        self.basis = basis
        self.art = art
        self.name = name
        self.zeitrahmen = basis.zeitrahmen
        self.symbole = tuple(basis.symbole)
        self.max_halte_s = basis.max_halte_s
        self.rueckblick = max(int(basis.rueckblick), FENSTER)
        self.spanne_l = getattr(basis, "L", None) if art == "REV02" else None
        self.modell_sha = modell_sha
        self._fenster = sorted(fenster, key=lambda f: f.test_von)
        self._von = [f.test_von for f in self._fenster]
        for i, f in enumerate(self._fenster):
            fenster_pruefen(f, art, self._fenster[i + 1] if i + 1 < len(self._fenster) else None)

    def parameter(self) -> dict:
        return {"basis": self.basis.name, "basis_parameter": self.basis.parameter(), "basis_hash": strategie_hash(self.basis), "art": self.art,
                "merkmal_fenster": str(FENSTER), "fenster": str(len(self._fenster)), "modell_sha": self.modell_sha}

    def fenster_fuer(self, t_ent: int) -> Fenster | None:
        i = bisect.bisect_right(self._von, t_ent) - 1
        if i < 0:
            return None
        f = self._fenster[i]
        return f if f.test_bis is None or t_ent < f.test_bis else None

    def bewerten(self, symbol: str, kerzen: list[Bar]) -> tuple[Signal | None, float | None, str]:
        """(Basissignal, Wahrscheinlichkeit, Entscheidung) – für Signal und Diagnose; Entscheidung HANDELN oder der Grund dagegen."""
        sig = self.basis.signal(symbol, list(kerzen[-int(self.basis.rueckblick):]))
        if sig is None:
            return None, None, "KEIN_BASISSIGNAL"
        t_ent = kerzen[-1].time + TF_S[self.zeitrahmen]
        f = self.fenster_fuer(t_ent)
        if f is None:
            return sig, None, "KEIN_FENSTER"
        if t_ent < f.embargo_bis:
            return sig, None, "EMBARGO"
        if f.schwelle is None or f.modell is None:
            return sig, None, "KEINE_SCHWELLE"
        x = merkmale(kerzen, sig.side, self.art, spanne_l=self.spanne_l)
        if x is None:
            return sig, None, "KEINE_MERKMALE"
        p = wahrscheinlichkeit(f.modell, x)
        return sig, p, "HANDELN" if p > f.schwelle else "UNTER_SCHWELLE"

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        sig, _, entscheidung = self.bewerten(symbol, kerzen)
        return sig if entscheidung == "HANDELN" else None


# ---------------------------------------------------------------------------------------------------- Laden
def datei_sha(pfad: Path | str) -> str:
    return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()


def fenster_aus_json(daten: Mapping) -> list[Fenster]:
    return [Fenster(int(f["test_von"]), None if f.get("test_bis") is None else int(f["test_bis"]), int(f["embargo_bis"]),
                    None if f.get("schwelle") is None else float(f["schwelle"]), f.get("modell")) for f in daten["fenster"]]


def laden(pfad: Path | str, basis, *, holdout: bool = False) -> MetaFilter:
    """MetaFilter aus der eingefrorenen Modelldatei (forschung/modelle/...): Walk-Forward-Fenster der Entwicklung oder (holdout=True)
    nur das Holdout-Modell. basis = Basisstrategie der Variante (Parameter laut Vorregistrierung)."""
    daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
    if daten.get("schema") != "meta_filter/1":
        raise ValueError("unbekanntes Modellschema")
    if basis.name != daten["basis_name"] or basis.parameter() != daten["basis_parameter"]:
        raise ValueError("Basisstrategie passt nicht zum Modell")
    fenster = fenster_aus_json({"fenster": [daten["holdout"]]} if holdout else daten)
    return MetaFilter(basis, fenster, art=daten["art"], name=daten["variante"], modell_sha=datei_sha(pfad))
