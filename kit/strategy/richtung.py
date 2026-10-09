"""Richtungsmodell (Runde 3, F-05b; Vorregistrierung docs/bot/prereg/F05B_ENTWURF.md): Hülle um eine Basisstrategie. Je handelbarem
Entscheidungspunkt schätzen zwei eingefrorene Modelle die Gewinnwahrscheinlichkeit für Kauf und für Verkauf zu denselben Abständen
(Ziel und Stop der Basis in Ticks, gespiegelt um den Einstieg der jeweiligen Richtung); gehandelt wird die besser geschätzte Richtung,
wenn ihr Vorsprung Δp = p_Richtung − p_Gegenrichtung größer als die Schwelle d* des Testfensters ist. Kein Sprachmodell im Handelspfad.

Nur Standardbibliothek: Merkmale, Modellrechnung, Fenster und Modellbindung aus kit.strategy.meta_filter. Die Basis liefert nur Zeitpunkt
und Abstände, nicht die Richtung. Handelbar = im Handelsfenster des Takts (kit.risk.guards.im_fenster) und Stop ≤ stop_ziel_max × Ziel
für beide Richtungen mit den Rundungen des Takts (kit.domain.rounding) gegen den Einstieg der Kerze (Kauf Ask, Verkauf Bid) – dieselbe
Prüfung baut den Datensatz (kit.research.richtung), deshalb sieht das Training genau die Punkte, an denen die Hülle entscheidet.
"""
from __future__ import annotations

import bisect
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from kit.domain import rounding
from kit.domain.types import Bar, Side
from kit.risk import guards
from kit.strategy import meta_filter as mf
from kit.strategy.base import Signal, strategie_hash
from kit.strategy.rev import punkt


def einstieg(k: Bar, side: Side) -> Decimal:
    """Einstieg der Kerze wie Takt und SIM: Kauf zum Ask (Schluss + Spread), Verkauf zum Bid (Schluss)."""
    return k.close + k.spread_points * punkt(k.symbol) if side is Side.BUY else k.close


def abstaende(sig: Signal, k: Bar) -> tuple[Decimal, Decimal]:
    """(Ziel, Stop) des Basissignals als Preisabstände zu seinem Einstieg e."""
    e = einstieg(k, sig.side)
    return abs(sig.tp - e), abs(e - sig.sl)


def spiegeln(sig: Signal, k: Bar, side: Side) -> Signal:
    """Signal der Richtung side mit denselben Abständen wie die Basis, um den Einstieg dieser Richtung; SL und TP wie im Takt auf das
    Raster gerundet (vom Markt weg), damit Label, Prüfung und gehandelter Trade auch bei Kursen unter dem Raster gleich sind."""
    ziel, stop = abstaende(sig, k)
    e = einstieg(k, side)
    p = punkt(sig.symbol)
    sl = rounding.auf_raster(e - side.sign * stop, p, aufrunden=side is Side.SELL)
    tp = rounding.auf_raster(e + side.sign * ziel, p, aufrunden=side is Side.BUY)
    return Signal(sig.symbol, side, sl, tp, sig.kerze, f"{sig.grund} R"[:40])


def stop_ziel_ok(sig: Signal, k: Bar, stop_ziel_max: Decimal) -> bool:
    """Prüfung des Takts (loop.einstieg_strategie): gerundete SL/TP gegen den Einstieg, |Einstieg − SL| ≤ max · |TP − Einstieg|."""
    p = punkt(sig.symbol)
    e = einstieg(k, sig.side)
    sl = rounding.auf_raster(sig.sl, p, aufrunden=sig.side is Side.SELL)
    tp = rounding.auf_raster(sig.tp, p, aufrunden=sig.side is Side.BUY)
    return abs(e - sl) <= stop_ziel_max * abs(tp - e)


def handelbar(t_ent: int, kauf: Signal, verkauf: Signal, k: Bar, konf, stop_ziel_max: Decimal) -> bool:
    """Zustandsunabhängig handelbar: Handelsfenster und Stop ≤ max × Ziel für beide Richtungen."""
    return guards.im_fenster(float(t_ent), konf) and stop_ziel_ok(kauf, k, stop_ziel_max) and stop_ziel_ok(verkauf, k, stop_ziel_max)


@dataclass(frozen=True)
class Fenster:
    """Testfenster mit Kauf- und Verkaufsmodell und der Schwelle d* für den Vorsprung (None = kein Handel)."""

    test_von: int
    test_bis: int | None
    embargo_bis: int
    schwelle: float | None
    modell_kauf: Mapping | None
    modell_verkauf: Mapping | None


class Richtungsfilter:
    """Strategie-Hülle: gleiche Symbole, Zeitrahmen und Zeitbarriere wie die Basis; rueckblick = max(Basis, FENSTER)."""

    def __init__(self, basis, fenster: Sequence[Fenster], *, art: str, name: str, konf, stop_ziel_max: Decimal | str,
                 modell_sha: str = "") -> None:
        mf.merkmal_namen(art)
        self.basis = basis
        self.art = art
        self.name = name
        self.zeitrahmen = basis.zeitrahmen
        self.symbole = tuple(basis.symbole)
        self.max_halte_s = basis.max_halte_s
        self.rueckblick = max(int(basis.rueckblick), mf.FENSTER)
        self.spanne_l = getattr(basis, "L", None) if art == "REV02" else None
        self.stop_ziel_max = Decimal(str(stop_ziel_max))
        self.handelsfenster = (konf.fenster_von, konf.fenster_bis, konf.freitag_bis)
        self.modell_sha = modell_sha
        self._konf = konf
        self._fenster = sorted(fenster, key=lambda f: f.test_von)
        self._von = [f.test_von for f in self._fenster]
        for i, f in enumerate(self._fenster):
            naechstes = self._fenster[i + 1] if i + 1 < len(self._fenster) else None
            nf = None if naechstes is None else mf.Fenster(naechstes.test_von, naechstes.test_bis, naechstes.embargo_bis, None, None)
            if (f.modell_kauf is None) != (f.modell_verkauf is None):
                raise ValueError("Kauf- und Verkaufsmodell nur gemeinsam")
            for modell in (f.modell_kauf, f.modell_verkauf):
                mf.fenster_pruefen(mf.Fenster(f.test_von, f.test_bis, f.embargo_bis, f.schwelle, modell), art, nf)

    def parameter(self) -> dict:
        return {"basis": self.basis.name, "basis_parameter": self.basis.parameter(), "basis_hash": strategie_hash(self.basis), "art": self.art,
                "merkmal_fenster": str(mf.FENSTER), "fenster": str(len(self._fenster)), "modell_sha": self.modell_sha,
                "stop_ziel_max": str(self.stop_ziel_max), "handelsfenster": list(self.handelsfenster)}

    def fenster_fuer(self, t_ent: int) -> Fenster | None:
        i = bisect.bisect_right(self._von, t_ent) - 1
        if i < 0:
            return None
        f = self._fenster[i]
        return f if f.test_bis is None or t_ent < f.test_bis else None

    def bewerten(self, symbol: str, kerzen: list[Bar]) -> tuple[Signal | None, float | None, float | None, str]:
        """(Signal der gewählten Richtung, p_Kauf, p_Verkauf, Entscheidung) – Entscheidung HANDELN oder der Grund dagegen."""
        sig = self.basis.signal(symbol, list(kerzen[-int(self.basis.rueckblick):]))
        if sig is None:
            return None, None, None, "KEIN_BASISSIGNAL"
        k = kerzen[-1]
        t_ent = k.time + mf.TF_S[self.zeitrahmen]
        f = self.fenster_fuer(t_ent)
        if f is None:
            return None, None, None, "KEIN_FENSTER"
        if t_ent < f.embargo_bis:
            return None, None, None, "EMBARGO"
        kauf, verkauf = spiegeln(sig, k, Side.BUY), spiegeln(sig, k, Side.SELL)
        if not handelbar(t_ent, kauf, verkauf, k, self._konf, self.stop_ziel_max):
            return None, None, None, "NICHT_HANDELBAR"
        if f.schwelle is None or f.modell_kauf is None:
            return None, None, None, "KEINE_SCHWELLE"
        x = mf.merkmale(kerzen, sig.side, self.art, spanne_l=self.spanne_l)
        if x is None:
            return None, None, None, "KEINE_MERKMALE"
        pk, pv = mf.wahrscheinlichkeit(f.modell_kauf, x), mf.wahrscheinlichkeit(f.modell_verkauf, x)
        gewaehlt = kauf if pk >= pv else verkauf
        return gewaehlt, pk, pv, "HANDELN" if abs(pk - pv) > f.schwelle else "UNTER_SCHWELLE"

    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None:
        sig, _, _, entscheidung = self.bewerten(symbol, kerzen)
        return sig if entscheidung == "HANDELN" else None


def packen(modell: Mapping | None) -> Mapping | None:
    """Kompakte, verlustfreie Form eines HGB-Modells für die Datei (zwei Modelle je Fenster): Blatt = Wert, innerer Knoten =
    [Merkmal, Schwelle, links, rechts, fehlend_links 0/1]. Für die Rechnung unbenutzte Felder entfallen; LOGREG bleibt unverändert."""
    if modell is None or modell.get("art") != "HGB":
        return modell
    baeume = [[n[0] if n[6] else [n[1], n[2], n[4], n[5], int(bool(n[3]))] for n in baum] for baum in modell["baeume"]]
    return {k: v for k, v in modell.items() if k != "baeume"} | {"baeume_kompakt": baeume}


def entpacken(modell: Mapping | None) -> Mapping | None:
    """Umkehrung von packen: Knoten [Wert, Merkmal, Schwelle, fehlend_links, links, rechts, Blatt] wie meta_filter._blatt."""
    if modell is None or "baeume_kompakt" not in modell:
        return modell
    baeume = [[[float(n), 0, 0.0, False, 0, 0, True] if not isinstance(n, list) else [0.0, int(n[0]), float(n[1]), bool(n[4]), int(n[2]),
                                                                                        int(n[3]), False] for n in baum]
              for baum in modell["baeume_kompakt"]]
    return {k: v for k, v in modell.items() if k != "baeume_kompakt"} | {"baeume": baeume}


def rechengleich(a: Mapping | None, b: Mapping | None) -> bool:
    """Zwei Modelle rechnen identisch (alle für die Wahrscheinlichkeit benutzten Felder bitgleich)."""
    if a is None or b is None:
        return a is b
    if a.get("art") != b.get("art") or list(a["merkmale"]) != list(b["merkmale"]):
        return False
    if a["art"] == "LOGREG":
        return all(a[k] == b[k] for k in ("mittel", "skala", "koeffizienten", "achsenabschnitt"))
    if a["basis"] != b["basis"] or len(a["baeume"]) != len(b["baeume"]):
        return False
    for ta, tb in zip(a["baeume"], b["baeume"], strict=True):
        if len(ta) != len(tb):
            return False
        for na, nb in zip(ta, tb, strict=True):
            if bool(na[6]) != bool(nb[6]):
                return False
            if na[6] and na[0] != nb[0]:
                return False
            if not na[6] and (na[1], na[2], bool(na[3]), na[4], na[5]) != (nb[1], nb[2], bool(nb[3]), nb[4], nb[5]):
                return False
    return True


def fenster_aus_json(daten: Mapping) -> list[Fenster]:
    return [Fenster(int(f["test_von"]), None if f.get("test_bis") is None else int(f["test_bis"]), int(f["embargo_bis"]),
                    None if f.get("schwelle") is None else float(f["schwelle"]), entpacken(f.get("modell_kauf")),
                    entpacken(f.get("modell_verkauf")))
            for f in daten["fenster"]]


def laden(pfad: Path | str, basis, *, konf, stop_ziel_max: Decimal | str, holdout: bool = False) -> Richtungsfilter:
    """Richtungsfilter aus der eingefrorenen Modelldatei (Schema richtung/1): Walk-Forward-Fenster oder (holdout=True) nur das
    Holdout-Modell; basis = Basisstrategie der Variante, konf = Betriebskonfiguration (Handelsfenster)."""
    daten = json.loads(Path(pfad).read_text(encoding="utf-8"))
    if daten.get("schema") != "richtung/1":
        raise ValueError("unbekanntes Modellschema")
    if basis.name != daten["basis_name"] or basis.parameter() != daten["basis_parameter"]:
        raise ValueError("Basisstrategie passt nicht zum Modell")
    fenster = fenster_aus_json({"fenster": [daten["holdout"]]} if holdout else daten)
    return Richtungsfilter(basis, fenster, art=daten["art"], name=daten["variante"], konf=konf, stop_ziel_max=stop_ziel_max,
                           modell_sha=mf.datei_sha(pfad))
