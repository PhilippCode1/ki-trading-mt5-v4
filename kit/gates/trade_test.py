"""Trade-Test (Tor 85, Plan F-1 §5; Vorregistrierung docs/bot/prereg/F04_ENTWURF.md §1, §5): reine Auswertung fertiger Backtests.

Eingaben: geschlossene Strategie-Trades (TestTrade, Zählregeln config/tore.toml [zaehlregeln]), Equity-Kurve, Signale,
Schattenereignisse (LOSS_LOCK/STOP50) und Zufallspaare. Schwellen allein aus config/tore.toml ([tor_85], [stop50], [band],
[limits]); Verfahren aus config/trade_test.toml (SHA-256-gepinnt wie tore()).

Kriterien je Variante auf den OOS-Trades der Entwicklung (Plan §5 Tor 85; Prereg §1 „Bewertung“):
  trades ≥ min_trades_oos · Quote ≥ quote_min · Erwartungswert in R: Bootstrap-Untergrenze > 0 · Gewinnfaktor ≥ gewinnfaktor_min ·
  Ø Verlust ≤ verlust_zu_gewinn_max × Ø Gewinn · Quote über dem Perzentil der Zufallsbasis · Max-Drawdown vom laufenden Hoch
  < drawdown_max_prozent · kein 50-%-Ereignis in der Tradefolge und kein Schattenereignis im OOS-Zeitraum · Hebelband und
  Tagesbudget beim Einstieg eingehalten (unabhängige Nachrechnung, ruft kit.risk.band bewusst nicht auf).
  Auswahl (Prereg §5): nur bestandene Varianten; höchste Wilson-95-%-Untergrenze, bei Gleichstand mehr Trades je Monat.
  Holdout allein (≥ min_trades_holdout, ≥ quote_min_holdout) prüft F-06 mit denselben Bausteinen.
Auslegungen:
  - Das Tor zählt ≥ 200 Trades über Entwicklung + Holdout gemeinsam; hier wird die Entwicklung allein dagegen geprüft (strenger).
  - Erwartungswert: einseitige 95-%-Untergrenze = 5. Perzentil der Mittelwerte aus iid-Bootstrap (n Ziehungen mit Zurücklegen
    je Wiederholung, random.Random(saat).choices).
  - Perzentile (Bootstrap, Zufallsbasis) nach nächstem Rang: Rang = ⌈p/100 · N⌉ (mindestens 1) der aufsteigend sortierten Werte.
  - Gewinnfaktor und Ø Verlust/Ø Gewinn in EUR inkl. Kosten (R nur berichtet); Verlust = Ergebnis ≤ 0 (Zählregel), der Ø-Verlust
    mittelt aber nur Ergebnisse < 0 (Null-Trades verdünnen ihn nicht, Review F-04).
    Ohne Verluste ist der Gewinnfaktor unendlich (erfüllt, wenn Gewinne > 0).
  - Quoten werden exakt verglichen (Decimal/ganze Zahlen); Statistik in float.
  - 50-%-Folge: OOS-Trades nach Schließzeit, das Fenster beginnt mit dem ersten OOS-Trade; Sperren des durchlaufenden
    Backtests kommen als Schattenereignisse hinzu.
  - Band: Hebel = Nominal / Equity nach Einstiegskosten (h0), beim Kurs = TP bzw. SL nach Kosten beider Seiten. „Minimal“ nach der
    Größenregel des Takts (kleinstes Rastervolumen, das die Untergrenzen erfüllt): ein Schritt weniger verletzt Nominal / Equity
    ≥ unten (Größenregel ohne Einstiegskosten, kit.risk.band unter0) oder htp ≥ unten.
  - Nicht bewertbar (ok = None, z. B. leere Tradeliste, fehlende Kurve oder Einstiegskontexte) = nicht bestanden.
Plan-Zusatzkriterien (DSR, Teilperioden, Gewinnfaktor bei Kosten × 1,5) werden nur berichtet (zusatz()).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import random
import tomllib
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from kit.gates import ROOT
from kit.research.stats import wilson

ZERO = Decimal(0)
HUNDERT = Decimal(100)
UNENDLICH = Decimal("Infinity")
TAG_S = 86400
TRADE_TEST_PFAD = ROOT / "config" / "trade_test.toml"
TRADE_TEST_SHA256 = "06f9973e73b6d0597943e17f28dd72835447998a3c2bb470480520854e806b86"
SCHATTEN_ARTEN = ("LOSS_LOCK", "STOP50")


class TradeTestVeraendert(RuntimeError):
    """config/trade_test.toml weicht vom eingefrorenen Stand ab – nichts läuft (fail-closed)."""


def konfig(pfad: Path | None = None) -> dict:
    roh = (pfad or TRADE_TEST_PFAD).read_bytes()
    if hashlib.sha256(roh).hexdigest() != TRADE_TEST_SHA256:
        raise TradeTestVeraendert("config/trade_test.toml weicht vom eingefrorenen Stand ab (SHA-256) – Änderungen nur durch den "
                                  "Betreiber.")
    return tomllib.loads(roh.decode("utf-8"))


@dataclass(frozen=True)
class Einstieg:
    """Kontext eines gefüllten Strategie-Einstiegs (für die unabhängige Band-/Budget-Prüfung)."""

    symbol: str
    side: str                          # "BUY"/"SELL"
    t: int                             # Einstiegszeit UTC s
    lots: Decimal
    preis: Decimal
    sl: Decimal
    tp: Decimal
    equity: Decimal                    # Equity unmittelbar vor dem Einstieg (Kontowährung EUR)
    budget: Decimal                    # erlaubter Verlust heute (limits.budget) beim Einstieg
    provision: Decimal                 # Provision je Lot und Seite, mit der der Takt die Größe rechnet
    waehrung: str                      # "EUR"
    tick_size: Decimal
    tick_value: Decimal
    contract_size: Decimal
    currency_base: str
    volume_min: Decimal
    volume_step: Decimal
    volume_max: Decimal
    offene_nominal: Decimal = ZERO     # andere offene eigene Positionen (bei V5 = 0)
    offene_risiko: Decimal = ZERO


@dataclass(frozen=True)
class TestTrade:
    """Ein vollständig geschlossener Strategie-Trade (Zählregeln config/tore.toml)."""

    __test__ = False                   # kein pytest-Testfall trotz des Namens

    symbol: str
    side: str
    t_auf: int
    t_zu: int
    ergebnis: Decimal                  # EUR, Summe aller Deals der Position inkl. Kommission und Swap
    risiko: Decimal                    # EUR > 0: geplanter Verlust bis SL inkl. Kommission beider Seiten zu den Kosten des Laufs
    grund: str                         # Ausstieg: TP, SL, ZEITBARRIERE, BAND_BODEN, BAND_DECKEL, K3, SONST
    einstieg: Einstieg | None = None

    @property
    def r(self) -> float:
        return float(self.ergebnis / self.risiko)

    @property
    def gewinn(self) -> bool:
        return self.ergebnis > ZERO


# ---------------------------------------------------------------- Zeitfenster
def _datum(wert: str | dt.date) -> dt.date:
    return wert if isinstance(wert, dt.date) else dt.date.fromisoformat(str(wert))


def _plus_jahre(d: dt.date, jahre: int) -> dt.date:
    try:
        return d.replace(year=d.year + jahre)
    except ValueError:                 # 29.02. → 28.02.
        return d.replace(year=d.year + jahre, day=28)


def _utc_s(j: int, m: int, t: int = 1) -> int:
    return int(dt.datetime(j, m, t, tzinfo=dt.UTC).timestamp())


def walk_forward(start: str | dt.date, ende: str | dt.date, anpassung_jahre: int, test_jahre: int) -> list[tuple[int, int]]:
    """Testfenster [von, bis) in UTC s: ab start + anpassung_jahre Kalenderjahre je test_jahre lang; das letzte endet (abgeschnitten)
    an ende + 1 Tag 00:00 UTC."""
    if anpassung_jahre < 0 or test_jahre < 1:
        raise ValueError("anpassung_jahre >= 0 und test_jahre >= 1 nötig")
    a = _datum(start)
    e = _datum(ende) + dt.timedelta(days=1)
    schluss = _utc_s(e.year, e.month, e.day)
    fenster: list[tuple[int, int]] = []
    i = 0
    while True:
        v = _plus_jahre(a, anpassung_jahre + i * test_jahre)
        von = _utc_s(v.year, v.month, v.day)
        if von >= schluss:
            return fenster
        b = _plus_jahre(a, anpassung_jahre + (i + 1) * test_jahre)
        fenster.append((von, min(_utc_s(b.year, b.month, b.day), schluss)))
        i += 1


def oos(trades: Iterable[TestTrade], fenster: Sequence[tuple[int, int]]) -> list[TestTrade]:
    """Trades, deren Eröffnung in einem Testfenster liegt (außerhalb der Anpassung)."""
    return [t for t in trades if any(von <= t.t_auf < bis for von, bis in fenster)]


# ---------------------------------------------------------------- Kennzahlen
def _dez(x: object) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _zahl(x: Decimal | float | None) -> float | None:
    return None if x is None else float(x)


def quote(trades: Sequence[TestTrade]) -> Decimal:
    """Anteil Gewinntrades (Ergebnis > 0); 0 ohne Trades."""
    return Decimal(sum(1 for t in trades if t.gewinn)) / len(trades) if trades else ZERO


def _naechster_rang(sortiert: Sequence[float], perzentil: object) -> float:
    n = len(sortiert)
    rang = int((_dez(perzentil) * n / HUNDERT).to_integral_value(rounding=ROUND_CEILING))
    return sortiert[min(max(rang, 1), n) - 1]


def bootstrap_untergrenze(werte: Sequence[float | Decimal], wiederholungen: int, saat: int, perzentil: object) -> float | None:
    """Perzentil (nächster Rang) der Bootstrap-Mittelwerte (iid, n Ziehungen mit Zurücklegen); None ohne Werte."""
    xs = [float(w) for w in werte]
    if not xs:
        return None
    if wiederholungen < 1:
        raise ValueError("wiederholungen >= 1 nötig")
    rng = random.Random(saat)
    n = len(xs)
    mittel = sorted(math.fsum(rng.choices(xs, k=n)) / n for _ in range(wiederholungen))
    return _naechster_rang(mittel, perzentil)


def gewinnfaktor(ergebnisse: Iterable[Decimal | float]) -> Decimal | None:
    """Summe Gewinne / Summe |Verluste|; None ohne Verluste (Bewertung: unendlich, wenn Gewinne > 0)."""
    xs = [_dez(x) for x in ergebnisse]
    gewinne = sum((x for x in xs if x > ZERO), ZERO)
    verluste = -sum((x for x in xs if x < ZERO), ZERO)
    return gewinne / verluste if verluste > ZERO else None


def verlust_zu_gewinn(ergebnisse: Iterable[Decimal | float]) -> Decimal | None:
    """Ø |Verlust| / Ø Gewinn; der Betrag des Ø-Verlusts mittelt nur echte Verluste (< 0), damit Null-Ergebnisse ihn nicht verdünnen
    (für die Quote bleibt 0 ein Verlust). 0 ohne Verluste, unendlich ohne Gewinne, None ohne Werte."""
    xs = [_dez(x) for x in ergebnisse]
    if not xs:
        return None
    gewinne = [x for x in xs if x > ZERO]
    verluste = [-x for x in xs if x < ZERO]
    if not verluste:
        return ZERO
    if not gewinne:
        return UNENDLICH
    return (sum(verluste, ZERO) / len(verluste)) / (sum(gewinne, ZERO) / len(gewinne))


def max_drawdown_prozent(kurve: Sequence[tuple[int, Decimal]]) -> Decimal | None:
    """Größter Rückgang vom laufenden Equity-Hoch in Prozent; None ohne Kurve."""
    hoch: Decimal | None = None
    dd = ZERO
    for _, e in kurve:
        if hoch is None or e > hoch:
            hoch = e
        elif hoch > ZERO:
            dd = max(dd, (hoch - e) / hoch * HUNDERT)
    return None if hoch is None else dd


def stop50_ereignisse(trades: Sequence[TestTrade], fenster: int, ab: int, quote_max: object) -> list[int]:
    """Indizes, an denen „ab n ≥ ab Trades: Quote der letzten min(n, fenster) ≤ quote_max“ von falsch auf wahr wechselt."""
    q = _dez(quote_max)
    gewinne = [t.ergebnis > ZERO for t in trades]
    aus: list[int] = []
    vorher = False
    for i in range(len(gewinne)):
        letzte = gewinne[max(0, i + 1 - fenster):i + 1]
        jetzt = i + 1 >= ab and Decimal(sum(letzte)) <= q * len(letzte)
        if jetzt and not vorher:
            aus.append(i)
        vorher = jetzt
    return aus


def zufallsbasis(paare: Sequence[tuple[bool, bool]], wiederholungen: int, saat: int, perzentil: object) -> dict:
    """Je Wiederholung je Trade zufällige Richtung (Kauf bei random() < 0,5) → Trefferquote; Perzentil nach nächstem Rang."""
    n = len(paare)
    if n == 0:
        return {"p95": None, "mittel": None, "n": 0}
    if wiederholungen < 1:
        raise ValueError("wiederholungen >= 1 nötig")
    rng = random.Random(saat)
    quoten = sorted(sum(1 for kauf, verkauf in paare if (kauf if rng.random() < 0.5 else verkauf)) / n for _ in range(wiederholungen))
    return {"p95": _naechster_rang(quoten, perzentil), "mittel": math.fsum(quoten) / wiederholungen, "n": n}


def tagesverluste(kurve: Sequence[tuple[int, Decimal]], versatz_s: int, grenze_prozent: object = "3") -> dict:
    """Größter Tagesverlust in % vom Tagesanker (erste Equity des Servertags; Servertag = UTC + versatz_s) und Anzahl Tage
    mit Verlust über grenze_prozent."""
    tage: dict[int, list[Decimal]] = {}
    for t, e in kurve:
        tag = (t + versatz_s) // TAG_S
        if tag not in tage:
            tage[tag] = [e, e]
        else:
            tage[tag][1] = min(tage[tag][1], e)
    verluste = [(anker - tief) / anker * HUNDERT for anker, tief in tage.values() if anker > ZERO]
    grenze = _dez(grenze_prozent)
    return {"max_prozent": max(verluste, default=ZERO), "tage_ueber_3": sum(1 for v in verluste if v > grenze)}


def _monat(t: int) -> tuple[int, int]:
    d = dt.datetime.fromtimestamp(t, dt.UTC)
    return d.year, d.month


def monatsrenditen(kurve: Sequence[tuple[int, Decimal]], von: int, bis: int) -> list[float]:
    """Renditen der Monatsend-Equity je Kalendermonat (UTC) in [von, bis); Basis des ersten Monats = erste Equity im Zeitraum,
    Monat ohne Punkte = unverändert."""
    punkte = [(t, e) for t, e in kurve if von <= t < bis]
    if not punkte:
        return []
    j, m = _monat(von)
    vorher = letzter = punkte[0][1]
    i = 0
    renditen: list[float] = []
    while True:
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
        m_ende = min(_utc_s(j, m), bis)
        while i < len(punkte) and punkte[i][0] < m_ende:
            letzter = punkte[i][1]
            i += 1
        renditen.append(float(letzter / vorher - 1))
        vorher = letzter
        if m_ende >= bis:
            return renditen


def teilperioden(trades: Iterable[TestTrade], n: int, von: int, bis: int) -> list[Decimal]:
    """Nettoergebnis je gleich langem Abschnitt von [von, bis) nach t_zu (Schließung davor/danach → erster/letzter Abschnitt)."""
    if n < 1 or bis <= von:
        raise ValueError("n >= 1 und von < bis nötig")
    summen = [ZERO] * n
    for t in trades:
        summen[min(n - 1, max(0, (t.t_zu - von) * n // (bis - von)))] += t.ergebnis
    return summen


# ---------------------------------------------------------------- Hebelband und Tagesbudget (unabhängig von kit.risk.band)
def _vorzeichen(side: str) -> int:
    if side not in ("BUY", "SELL"):
        raise ValueError(f"unbekannte Seite {side!r}")
    return 1 if side == "BUY" else -1


def _teilen(nominal: Decimal, basis: Decimal) -> Decimal:
    return nominal / basis if basis > ZERO else UNENDLICH


def _band_werte(e: Einstieg, lots: Decimal | None = None) -> dict[str, Decimal]:
    lots = e.lots if lots is None else lots
    sign = _vorzeichen(e.side)

    def nominal(kurs: Decimal) -> Decimal:
        return e.contract_size * lots if e.currency_base == e.waehrung else kurs / e.tick_size * e.tick_value * lots

    def ergebnis(kurs: Decimal) -> Decimal:
        return (kurs - e.preis) * sign / e.tick_size * e.tick_value * lots

    k_seite = lots * e.provision
    k = 2 * k_seite
    verlust = -ergebnis(e.sl) + k
    return {"h0": _teilen(nominal(e.preis), e.equity - k_seite), "h0_groesse": _teilen(nominal(e.preis), e.equity),
            "htp": _teilen(nominal(e.tp), e.equity + ergebnis(e.tp) - k),
            "hsl": _teilen(nominal(e.sl), e.equity - verlust), "verlust": verlust,
            "gesamt0": _teilen(e.offene_nominal + nominal(e.preis), e.equity),
            "gesamt_sl": _teilen(e.offene_nominal + nominal(e.sl), e.equity - verlust - e.offene_risiko)}


def band_pruefen(e: Einstieg, band: dict, stop_ziel_max: object = "3") -> list[str]:
    """Befunde der Band-/Budget-Regeln für einen Einstieg (leer = eingehalten); band = tore()["band"], stop_ziel_max =
    tore()["limits"]["stop_zu_ziel_max"] (D4/V1: geplanter Stop-Abstand ≤ 3 × Ziel-Abstand ab dem Einstiegskurs)."""
    unten, oben = _dez(band["korridor_unten"]), _dez(band["korridor_oben"])
    sign = _vorzeichen(e.side)
    befunde: list[str] = []
    if e.sl <= ZERO or e.tp <= ZERO or (e.sl - e.preis) * sign >= ZERO or (e.tp - e.preis) * sign <= ZERO:
        befunde.append("SCHUTZ")
    if e.lots % e.volume_step != ZERO or e.lots < e.volume_min or e.lots > e.volume_max:
        befunde.append("LOT_RASTER")
    if abs(e.preis - e.sl) > _dez(stop_ziel_max) * abs(e.tp - e.preis):
        befunde.append("STOP_ZU_ZIEL")
    w = _band_werte(e)
    if not unten <= w["h0"] <= oben:
        befunde.append("BAND_EINSTIEG")
    if w["htp"] < unten:
        befunde.append("BAND_TP")
    if w["hsl"] > oben:
        befunde.append("BAND_SL")
    if w["gesamt0"] > oben or w["gesamt_sl"] > oben:
        befunde.append("BAND_GESAMT")
    if w["verlust"] + e.offene_risiko > e.budget:
        befunde.append("TAGESBUDGET")
    kleiner = e.lots - e.volume_step
    if kleiner >= e.volume_min:
        wk = _band_werte(e, kleiner)
        if wk["h0_groesse"] >= unten and wk["htp"] >= unten:
            befunde.append("LOT_NICHT_MINIMAL")
    return befunde


# ---------------------------------------------------------------- Bewertung und Auswahl
def _konsistenz(tore: dict, konf: dict) -> None:
    t85 = tore["tor_85"]
    if _dez(konf["bootstrap"]["untergrenze_perzentil"]) != HUNDERT - _dez(t85["erwartung_untergrenze_prozent"]):
        raise ValueError("Bootstrap-Perzentil passt nicht zu tor_85.erwartung_untergrenze_prozent")
    z = konf["zufall"]
    if int(z["wiederholungen"]) < int(t85["zufall_wiederholungen"]) or _dez(z["perzentil"]) != _dez(t85["zufall_perzentil"]):
        raise ValueError("Zufallsbasis passt nicht zu tor_85 (Wiederholungen/Perzentil)")


def _kriterium(wert: object, schwelle: object, ok: bool | None, text: str) -> dict:
    return {"wert": wert, "schwelle": schwelle, "ok": ok, "text": text}


def _basis(trades: Sequence[TestTrade], basis: str) -> list[Decimal] | list[float]:
    return [t.r for t in trades] if basis == "R" else [t.ergebnis for t in trades]


def bewerten(trades_oos: Sequence[TestTrade], kurve_oos: Sequence[tuple[int, Decimal]], signale: Sequence[dict],
             schatten: Sequence[dict], zufall_paare: Sequence[tuple[bool, bool]], tore: dict, konf: dict, *, monate: float,
             zeitraum: tuple[int, int] | None = None) -> dict:
    """Alle Entwicklungskriterien des 85-%-Tors und die Berichtskennzahlen einer Variante.

    zeitraum [von, bis) für die Schattenereignisse; ohne Angabe die Spanne aus Kurve und Trades."""
    _konsistenz(tore, konf)
    t85, s50, band = tore["tor_85"], tore["stop50"], tore["band"]
    folge = sorted(trades_oos, key=lambda t: (t.t_zu, t.t_auf))
    n = len(folge)
    leer = n == 0
    gewinner = sum(1 for t in folge if t.gewinn)
    eur = [t.ergebnis for t in folge]
    rr = [t.r for t in folge]
    k: dict[str, dict] = {}

    k["trades"] = _kriterium(n, t85["min_trades_oos"], None if leer else n >= int(t85["min_trades_oos"]),
                             f"OOS-Trades ≥ {t85['min_trades_oos']}; das Tor zählt Entwicklung + Holdout gemeinsam, "
                             "hier nur die Entwicklung (strenger)")
    q_min = _dez(t85["quote_min"])
    k["quote"] = _kriterium(None if leer else gewinner / n, t85["quote_min"], None if leer else Decimal(gewinner) >= q_min * n,
                            f"Gewinntrades (Ergebnis > 0) {gewinner}/{n} ≥ {t85['quote_min']}")

    b = konf["bootstrap"]
    unter = bootstrap_untergrenze(rr, int(b["wiederholungen"]), int(b["saat"]), b["untergrenze_perzentil"])
    k["erwartung_r"] = _kriterium(unter, "0", None if unter is None else unter > 0.0,
                                  f"einseitige {t85['erwartung_untergrenze_prozent']}-%-Untergrenze von E[R] (iid-Bootstrap, "
                                  f"{b['wiederholungen']} Wiederholungen, {b['untergrenze_perzentil']}. Perzentil) > 0")

    pf_basis = konf["kennzahlen"]["gewinnfaktor_basis"]
    werte_pf = _basis(folge, pf_basis)
    pf, pf_wert = gewinnfaktor(werte_pf), _pf_zahl(werte_pf)
    pf_ok = None if leer else (pf >= _dez(t85["gewinnfaktor_min"]) if pf is not None else pf_wert == math.inf)
    k["gewinnfaktor"] = _kriterium(pf_wert, t85["gewinnfaktor_min"], pf_ok,
                                   f"Summe Gewinne / Summe Verluste ({pf_basis}) ≥ {t85['gewinnfaktor_min']}")

    vzg_basis = konf["kennzahlen"]["verlust_zu_gewinn_basis"]
    vzg = verlust_zu_gewinn(_basis(folge, vzg_basis))
    k["verlust_zu_gewinn"] = _kriterium(_zahl(vzg), t85["verlust_zu_gewinn_max"],
                                        None if vzg is None else vzg <= _dez(t85["verlust_zu_gewinn_max"]),
                                        f"Ø Verlust / Ø Gewinn ({vzg_basis}, realisiert) ≤ {t85['verlust_zu_gewinn_max']}")

    z = konf["zufall"]
    zuf = zufallsbasis(zufall_paare, int(z["wiederholungen"]), int(z["saat"]), z["perzentil"])
    if leer or zuf["n"] != n:
        z_ok, z_text = None, f"nicht bewertbar: {zuf['n']} Zufallspaare zu {n} Trades"
    else:
        z_ok = gewinner / n > zuf["p95"]
        z_text = f"Quote > {z['perzentil']}. Perzentil der Zufallsbasis ({z['wiederholungen']} Wiederholungen, zufällige Richtung)"
    k["zufallsbasis"] = _kriterium(zuf["p95"], z["perzentil"], z_ok, z_text)

    dd = max_drawdown_prozent(kurve_oos)
    k["drawdown"] = _kriterium(_zahl(dd), t85["drawdown_max_prozent"],
                               None if leer or dd is None else dd < _dez(t85["drawdown_max_prozent"]),
                               f"Max-Drawdown vom laufenden Equity-Hoch < {t85['drawdown_max_prozent']} % (kein LOSS_LOCK)")

    ereignisse = stop50_ereignisse(folge, int(s50["fenster"]), int(s50["ab_trades"]), s50["quote_max"])
    if zeitraum is None:
        zeiten = [t for t, _ in kurve_oos] + [t.t_auf for t in folge] + [t.t_zu for t in folge]
        zeitraum = (min(zeiten), max(zeiten) + 1) if zeiten else (0, 0)
    schatten_oos = [s for s in schatten if s.get("art") in SCHATTEN_ARTEN and zeitraum[0] <= int(s["t"]) < zeitraum[1]]
    k["stop50"] = _kriterium(len(ereignisse) + len(schatten_oos), 0, None if leer else not ereignisse and not schatten_oos,
                             f"keine 50-%-Ereignisse in der Folge (letzte {s50['fenster']}, ab {s50['ab_trades']} Trades, "
                             f"≤ {s50['quote_max']}) und keine Schattenereignisse LOSS_LOCK/STOP50 im OOS-Zeitraum")

    befunde: Counter[str] = Counter()
    ohne = 0
    for t in folge:
        if t.einstieg is None:
            ohne += 1
        else:
            befunde.update(band_pruefen(t.einstieg, band, tore["limits"]["stop_zu_ziel_max"]))
    band_ok = None if leer else (False if befunde else (None if ohne else True))
    k["band_budget"] = _kriterium(sum(befunde.values()), 0, band_ok,
                                  f"Hebelband {band['korridor_unten']}–{band['korridor_oben']} und Tagesbudget je Einstieg "
                                  f"(unabhängig nachgerechnet); {ohne} Trades ohne Einstiegskontext")

    hebel = [float(_band_werte(t.einstieg)["h0"]) for t in folge if t.einstieg is not None]
    erg = Counter(str(s.get("ergebnis")) for s in signale)
    abgelehnt = Counter(str(s.get("grund", "")) for s in signale if s.get("ergebnis") == "ABGELEHNT")
    tv = tagesverluste(kurve_oos, int(konf["konto"]["versatz_s"]), tore["limits"]["tagesbudget_prozent"])
    kennzahlen = {
        "n": n, "gewinner": gewinner, "quote": None if leer else gewinner / n,
        "wilson_95": None if leer else list(wilson(gewinner, n)),
        "e_r": None if leer else math.fsum(rr) / n, "e_r_untergrenze": unter,
        "pf_eur": _pf_zahl(eur), "pf_r": _pf_zahl(rr),
        "verlust_zu_gewinn_eur": _zahl(verlust_zu_gewinn(eur)), "verlust_zu_gewinn_r": _zahl(verlust_zu_gewinn(rr)),
        "max_dd_prozent": _zahl(dd), "stop50_ereignisse": ereignisse,
        "schatten": dict(sorted(Counter(str(s["art"]) for s in schatten_oos).items())),
        "trades_pro_monat": n / monate if monate > 0 else None,
        "zufall": {"p95": zuf["p95"], "mittel": zuf["mittel"]},
        "ausstiege": dict(sorted(Counter(t.grund for t in folge).items())),
        "signale": {"gesamt": len(signale), "erledigt": erg["ERLEDIGT"], "abgelehnt": dict(sorted(abgelehnt.items())),
                    "sonst": len(signale) - erg["ERLEDIGT"] - erg["ABGELEHNT"],
                    "quote_signal_trade": erg["ERLEDIGT"] / len(signale) if signale else None},
        "hebel": {"min": min(hebel, default=None), "mittel": math.fsum(hebel) / len(hebel) if hebel else None,
                  "max": max(hebel, default=None)},
        "tagesverluste": {"max_prozent": float(tv["max_prozent"]), "tage_ueber_3": tv["tage_ueber_3"]},
        "band_befunde": dict(sorted(befunde.items())),
    }
    return {"kriterien": k, "kennzahlen": kennzahlen, "bestanden": all(x["ok"] is True for x in k.values())}


def _pf_zahl(werte: Sequence[Decimal] | Sequence[float]) -> float | None:
    """Gewinnfaktor als Berichtszahl: unendlich ohne Verluste (mit Gewinnen), None ohne Werte bzw. ohne Gewinne und Verluste."""
    if not werte:
        return None
    pf = gewinnfaktor(werte)
    if pf is None:
        return math.inf if any(x > 0 for x in werte) else None
    return float(pf)


def auswahl(bewertungen: dict[str, dict]) -> str | None:
    """Prereg §5: nur bestandene Varianten; höchste Wilson-Untergrenze, bei Gleichstand mehr Trades je Monat, danach die erste
    in der Reihenfolge des dict (Variantenliste). None = kein Holdout-Kandidat."""
    kandidaten = [(name, b["kennzahlen"]) for name, b in bewertungen.items() if b.get("bestanden") is True]
    if not kandidaten:
        return None
    return max(kandidaten, key=lambda nk: (nk[1]["wilson_95"][0], nk[1]["trades_pro_monat"] or 0.0))[0]


def zusatz(konf: dict, *, teilperioden_werte: Sequence[Decimal] | None = None, gewinnfaktor_kosten: Decimal | float | None = None,
           dsr: float | None = None) -> dict:
    """Plan-Zusatzkriterien – nur berichten (gehen nicht in „bestanden“ ein). Der Gewinnfaktor bei Kosten × kostenfaktor kommt
    als fertige Zahl aus einem eigenen Backtest; None = nicht berechnet."""
    z = konf["zusatz"]
    positiv = None if teilperioden_werte is None else sum(1 for w in teilperioden_werte if w > ZERO)
    gk_ok = None if gewinnfaktor_kosten is None else _dez(gewinnfaktor_kosten) > _dez(z["gewinnfaktor_kosten_min"])
    return {
        "nur_berichten": bool(z["nur_berichten"]),
        "dsr": {"wert": dsr, "schwelle": z["dsr_min"], "ok": None if dsr is None else dsr >= float(z["dsr_min"])},
        "teilperioden": {"werte": None if teilperioden_werte is None else [str(w) for w in teilperioden_werte], "positiv": positiv,
                         "schwelle": f"{z['teilperioden_positiv_min']}/{z['teilperioden']}",
                         "ok": None if positiv is None else positiv >= int(z["teilperioden_positiv_min"])},
        "gewinnfaktor_kosten": {"wert": _zahl(gewinnfaktor_kosten), "schwelle": z["gewinnfaktor_kosten_min"],
                                "ok": gk_ok},
    }
