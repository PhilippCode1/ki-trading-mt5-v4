"""Takt des Bots (Plan F-1 §4). Ein Prozess, ein Schreiber je Ablage (Schreibsperre hält der Aufrufer).

Jede Sekunde: STOP-/BEENDEN-Datei, laufendes K3.  Alle ≤ 5 s und direkt nach jedem Fill: Demo-Wache, Abgleich mit
Schutzaktionen, Kapital/Anker, Grenzen (LOSS_LOCK, Tagesstopp, 50-%-Stopp), Technik-Wächter, Band-Prüfpunkt nach Fill.
Je Minute: Handelslogik der Strategie; die Probe-Mechanik läuft im Schutztakt (≤ 5 s).  Täglich 21:30 Berlin: Band-Prüfpunkt.
Neustart: Journal → Sperren/Anker/Tradebuch → Lebenszyklus → Abgleich – erst danach Handel.

Stufen: K1 (STOP-Datei) keine Einstiege, vorübergehend · K2 keine Einstiege, dauerhaft (PIN) · K3 eigene Positionen flach
(≤ 60 s) + K2.  Demo-Vorrang: Konto nicht DEMO → nichts senden, dauerhafte Sperre, Meldung, Prozessende.  Abbau und Schutz
werden nie durch eine Sperre oder Risikogrenze blockiert.
"""
from __future__ import annotations

import datetime as dt
import math
import os
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from kit import __version__
from kit.broker.seam import BrokerFehler
from kit.config import Konfiguration
from kit.domain import rounding
from kit.domain.types import (
    OFFEN,
    ZERO,
    Absicht,
    AccountSnapshot,
    Action,
    Bar,
    HandelsModus,
    KontoModus,
    Namensraum,
    Operation,
    OpStatus,
    Side,
)
from kit.domain.zeit import nach_berlin
from kit.gates import tore
from kit.gates.tor_t import mechanik_hash
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.orders.reconcile import Abgleich
from kit.risk import band as bandmod
from kit.risk import guards, limits, sizing
from kit.run.melder import DateiMelder
from kit.state import sperren as sp
from kit.state.journal import Journal
from kit.state.store import StateStore, stop_stufe
from kit.strategy.base import Signal, Strategie, strategie_hash

UTC = dt.UTC
SCHUTZ_TAKT_S = 5.0
HANDEL_TAKT_S = 60.0
TECHNIK_FENSTER = 20
TECHNIK_MAX_FEHLER = 3
TECHNIK_PAUSE_S = 1800.0
UNBEKANNT_MAX_S = 900.0
TF_S = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
VORFALL_NULLTOLERANZ = frozenset({"NEGPROOF_FALSIFIED", "EIGENER_DEAL_OHNE_OPERATION", "DOPPEL_FILL", "NICHT_DEMO_SENDUNG"})
ABBAU_PAUSE_S = 30.0                       # nach endgültig abgelehntem Abbau: Wartezeit, verdoppelt je weiterer Ablehnung
ABBAU_PAUSE_MAX_S = 900.0


class Ende(Exception):
    """Der Takt endet geordnet (Demo-Vorrang, BEENDEN)."""

    def __init__(self, grund: str, code: int = 2) -> None:
        super().__init__(grund)
        self.grund = grund
        self.code = code


class Bot:
    def __init__(self, terminal, ablage: Path, konf: Konfiguration, *, modus: str, strategie: Strategie | None = None,
                 probe: bool = False, demo_pruefung: Callable[[], str | None] | None = None, melder=None,
                 journal_fsync: bool = True, tor_werte: dict | None = None, versatz_takt_s: float | None = None) -> None:
        self.t = terminal
        self.ablage = Path(ablage)
        self.konf = konf
        self.modus = modus
        self.tore = tor_werte or tore()
        self.band = bandmod.Band.aus_toren(self.tore)
        lim = self.tore["limits"]
        self.budget_prozent = Decimal(lim["tagesbudget_prozent"])
        self.loss_prozent = Decimal(lim["loss_lock_prozent"])
        self.stop_ziel_max = Decimal(lim["stop_zu_ziel_max"])
        self.margin_min = Decimal(lim["margin_level_min_prozent"])
        s50 = self.tore["stop50"]
        self.s50 = (int(s50["fenster"]), int(s50["ab_trades"]), Decimal(s50["quote_max"]))
        self.demo_pruefung = demo_pruefung
        self.journal = Journal(self.ablage / "journal", uhr=terminal.zeit, fsync=journal_fsync)
        self.store = StateStore(self.ablage)
        self.lz = Lebenszyklus(terminal, self.journal, demo_pruefung=demo_pruefung)
        self.abgleich: Abgleich | None = None
        self.melder = melder or DateiMelder(self.ablage, windows=konf.meldungen_windows)
        self.strategie = strategie
        self.strat_hash = strategie_hash(strategie) if strategie else ""
        self.mechanik = mechanik_hash()
        from kit.probe.mechanik import ProbeMechanik
        self.probe = ProbeMechanik(self) if probe else None
        self.sperren: dict[str, dict] = {}
        self.k1 = False
        self.drill_stufe = 0
        self.tag = ""
        self.tag_anker = ZERO
        self.loss_anker = ZERO
        self.tagesstopp_tag = ""
        self.technik_pause_bis = 0.0
        self._technik_ab = 0.0
        self.buch = limits.Tradebuch()
        self.zaehlstart = 0
        self.beenden = False
        self._t_schutz = -math.inf
        self._t_handel = -math.inf
        self._pruefpunkt_tag = ""
        self._fill = False
        self._letzte_kerze: dict[str, int] = {}
        self._k3_seit: float | None = None
        self._k3_ausloeser = ""
        self._vorfaelle_gesehen = 0
        self._gemeldet_unbekannt: set[str] = set()
        self._erste_pruefung = True
        self._pfad_beenden = str(self.ablage / "BEENDEN")
        self._pfad_stop = str(self.ablage / "STOP")
        self._ops_n = -1
        self._t_technik = -math.inf
        self.versatz_takt_s = versatz_takt_s           # echtes MT5: Serverversatz stündlich neu messen (Zeitumstellung)
        self._t_versatz = -math.inf
        self.tag_anker_t = 0.0                          # Zeitpunkt der Equity-Lesung des Ankers (Kapital danach verschiebt ihn)
        self.loss_anker_t = 0.0
        self._fill_pruefpunkt = False
        self._letzte_dateipruefung = 0.0

    # ------------------------------------------------------------------------------------------------ Start
    def starten(self) -> None:
        if getattr(self.t, "versatz_s", 0.0) is None:
            raise Ende("Serverversatz unbekannt – Zeiten wären um Stunden verschoben (erst messen).")
        saetze = self.journal.lesen()
        zustand = self.store.laden(journal_vorhanden=bool(saetze))        # ZustandFehler → Aufrufer (Sperre)
        self.sperren = sp.aus_journal(saetze)
        for g in zustand.get("sperren", []):
            self.sperren.setdefault(g, {"seq": 0, "t": 0, "text": "aus Zustand"})
        nachholen: dict[str, int] = {}                  # Auslöser im Journal, deren Sperrsatz fehlt (Absturz dazwischen)
        loss_seq = 0
        for s in saetze:
            d = s.get("daten", {})
            art, code = s["art"], s["code"]
            if art == "ANKER" and code == "LOSS_LOCK":
                self.loss_anker, self.loss_anker_t, loss_seq = Decimal(d["wert"]), float(d.get("basis_t", s["t"])), s["seq"]
            elif art == "ANKER" and code == "TAG":
                self.tag, self.tag_anker, self.tag_anker_t = d["tag"], Decimal(d["wert"]), float(d.get("basis_t", s["t"]))
            elif art == "DEAL" and code == "KAPITAL":
                self._kapital(Decimal(d["geld"]), int(d["zeit"]), schreiben=False)
            elif art == "DEAL" and code == "STOP_OUT":
                nachholen["STOP_OUT"] = s["seq"]
            elif (art == "ABGLEICH" and code == "DIFFERENZ") or (art == "VORFALL" and code in VORFALL_NULLTOLERANZ):
                nachholen["NULLTOLERANZ"] = s["seq"]
            elif art == "TAGESSTOPP":
                self.tagesstopp_tag = d["tag"]
            elif art == "TECHNIK_PAUSE":
                self.technik_pause_bis = max(self.technik_pause_bis, s["t"] + TECHNIK_PAUSE_S)
            self.buch.deal(s)
        if sp.letzte_entsperrung(saetze, "LOSS_LOCK") > loss_seq:
            self.loss_anker = ZERO                       # Betreiber hat LOSS_LOCK aufgehoben: neuer Anker ab jetzt
        ab_zeit = saetze[0]["t"] if saetze else self.t.zeit()
        self._technik_ab = self.t.zeit()
        self.lz.wiederherstellen()
        self._vorfaelle_gesehen = len(self.lz.vorfaelle)
        self.abgleich = Abgleich(self.lz, self.journal, ab_zeit=ab_zeit)
        start = self.journal.schreiben("START", self.modus, f"Bot gestartet ({self.modus}, kit {__version__})", modus=self.modus,
                                       mechanik_hash=self.mechanik, strategie_hash=self.strat_hash, version=__version__,
                                       sperren=sorted(self.sperren))
        self.zaehlstart = max(sp.letzte_entsperrung(saetze, "STOP50"), self._hash_beginn(saetze + [start]))
        for grund, seq in nachholen.items():
            if seq > sp.letzte_entsperrung(saetze, grund):
                self._sperren(grund, "aus dem Journal nachgeholt (Auslöser ohne Sperrsatz)")
        konto = self._konto()
        if self.loss_anker <= ZERO:
            self._anker("LOSS_LOCK", konto.equity, "Start der Messung", self.t.zeit())
        if self.sperren:
            self.melder.melden("WARNUNG", f"Start mit aktiven Sperren: {', '.join(sorted(self.sperren))} – Einstiege aus.")
        if sp.stufe(self.sperren) == 3:
            flach = max((s["seq"] for s in saetze if s["art"] == "KILL_FLACH" and not s["daten"].get("drill")), default=0)
            offen = [v["t"] for g, v in self.sperren.items() if g in sp.K3_GRUENDE and v["seq"] > flach and v["t"]]
            self._k3_seit = min(offen) if offen else self.t.zeit()       # K3-Zeit läuft seit der Sperre, nicht seit dem Neustart
            self._k3_ausloeser = "NEUSTART"
        self._speichern()
        self.schutz()

    def _hash_beginn(self, saetze: list[dict]) -> int:
        beginn = 0
        for s in saetze:
            if s["art"] != "START":
                continue
            gleich = s["daten"].get("strategie_hash", "") == self.strat_hash
            if not gleich:
                beginn = 0
            elif beginn == 0:
                beginn = int(s["seq"])
        return beginn

    # ------------------------------------------------------------------------------------------------ Takt
    def laufen(self, *, bis: float | None = None, schlaf: Callable[[float], None] = time.sleep, max_verbindungsfehler: int = 10) -> int:
        """Bis BEENDEN, Demo-Vorrang-Ende oder Zeitpunkt `bis` (Terminalzeit). Rückgabe: Exit-Code."""
        fehler = 0
        self.beenden = False
        while True:
            try:
                self.schritt()
                fehler = 0
            except Ende as e:
                self.journal.schreiben("ENDE", e.grund, f"Takt beendet: {e.grund}")
                self.melder.melden("ALARM" if e.code else "INFO", f"Bot beendet: {e.grund}")
                return e.code
            except (BrokerFehler, ConnectionError, OSError) as exc:
                fehler += 1
                self.journal.schreiben("VORFALL", "VERBINDUNG", f"Terminalfehler ({type(exc).__name__}) – Versuch {fehler}",
                                       fehler=str(exc)[:200])
                if fehler >= max_verbindungsfehler:
                    self.melder.melden("ALARM", "Terminal dauerhaft nicht erreichbar – Bot beendet (Server-SL/TP schützen).")
                    self.journal.schreiben("ENDE", "VERBINDUNG", "Takt beendet: Terminal nicht erreichbar")
                    return 3
                schlaf(min(60.0, 5.0 * fehler))
                verbinden = getattr(self.t, "verbinden", None)
                if verbinden is not None:
                    try:
                        verbinden()
                    except Exception:  # noqa: BLE001 - nächster Versuch
                        pass
                continue
            except Exception as exc:
                self.journal.schreiben("VORFALL", "PROGRAMMFEHLER", f"Unerwarteter Fehler: {type(exc).__name__}", fehler=str(exc)[:300])
                self.melder.melden("ALARM", f"Programmfehler {type(exc).__name__} – Bot beendet (Server-SL/TP schützen).")
                raise
            if self.beenden:
                self.journal.schreiben("ENDE", "BEENDEN", "Takt beendet auf Wunsch (BEENDEN-Datei)")
                return 0
            if bis is not None and self.t.zeit() >= bis:
                self.journal.schreiben("ENDE", "ZEIT", "Takt beendet: Laufzeit erreicht")
                return 0
            schlaf(1.0)

    def schritt(self) -> None:
        jetzt = self.t.zeit()
        self._dateien(jetzt)
        if self.beenden:
            return
        if self._fill or jetzt - self._t_schutz >= SCHUTZ_TAKT_S:
            self.schutz()
            if self.probe is not None:
                self.probe.schritt(self.t.zeit())
        if self._k3_aktiv():
            self._k3()
        tag = self._pruefpunkt_faellig(jetzt)
        if tag:
            self.pruefpunkt("TAEGLICH")
            self._pruefpunkt_tag = tag                   # erst nach Erfolg als erledigt markieren
        if self._t_handel == -math.inf or math.floor(jetzt / HANDEL_TAKT_S) != math.floor(self._t_handel / HANDEL_TAKT_S):
            self.handel(jetzt)

    # ------------------------------------------------------------------------------------------------ Dateien (K1–K3, BEENDEN)
    def _dateien(self, jetzt: float) -> None:
        if os.path.exists(self._pfad_beenden):
            self.beenden = True
            Path(self._pfad_beenden).unlink(missing_ok=True)
            return
        wand = time.time()
        vorher, self._letzte_dateipruefung = self._letzte_dateipruefung, wand
        if not (self.k1 or self.drill_stufe or os.path.exists(self._pfad_stop)):
            self._erste_pruefung = False
            return
        stufe = stop_stufe(self.ablage)
        # Wirkzeit: höchstens seit der letzten Prüfung (kopierte Dateien tragen alte Änderungszeiten); beim Start sofort wirksam
        alter = 0.0 if self._erste_pruefung or not vorher else min(self._datei_alter(wand), wand - vorher)
        self._erste_pruefung = False
        if stufe and self._drill_datei():
            if self.drill_stufe != stufe:
                self.drill_stufe = stufe
                if stufe == 3 and self._k3_seit is None:
                    self._k3_seit, self._k3_ausloeser = jetzt, "DRILL"
            return
        if self.drill_stufe:
            self.drill_stufe = 0                         # Drill-Datei entfernt
        if stufe >= 1 and not self.k1:
            self.k1 = True
            self._kill_eintrag(1, "STOP-Datei", alter, drill=False)
        elif stufe == 0 and self.k1:
            self.k1 = False
            self.journal.schreiben("KILL_AUFGEHOBEN", "K1", "STOP-Datei entfernt – K1 aufgehoben")
        if stufe >= 2 and self._sperren(f"K{stufe}", f"STOP-Datei K{stufe}"):
            self._kill_eintrag(stufe, "STOP-Datei", alter, drill=False)

    def _datei_alter(self, wand: float) -> float:
        try:
            return max(0.0, wand - os.path.getmtime(self._pfad_stop))
        except OSError:
            return 0.0

    def _drill_datei(self) -> bool:
        try:
            return b"DRILL" in Path(self._pfad_stop).read_bytes()
        except OSError:
            return False

    def _kill_eintrag(self, stufe: int, ausloeser: str, dauer: float, *, drill: bool) -> None:
        self.journal.schreiben("KILL", f"K{stufe}", f"K{stufe} wirksam ({ausloeser})", stufe=stufe, ausloeser=ausloeser,
                               dauer_s=round(dauer, 3), drill=drill)
        self.melder.melden("WARNUNG", f"K{stufe} wirksam ({ausloeser}) – keine neuen Einstiege.")

    # ------------------------------------------------------------------------------------------------ Sperren
    def _sperren(self, grund: str, text: str) -> bool:
        """Dauerhafte Sperre setzen; True = neu gesetzt."""
        if grund in self.sperren:
            return False
        s = self.journal.schreiben("BOT_SPERRE", grund, text, stufe=sp.stufe([grund]))
        self.sperren[grund] = {"seq": s["seq"], "t": s["t"], "text": text}
        self.melder.melden("ALARM", f"Sperre {grund}: {text} – Aufheben nur durch den Betreiber (kit entsperren).")
        if sp.stufe(self.sperren) == 3 and self._k3_seit is None:
            self._k3_seit, self._k3_ausloeser = self.t.zeit(), grund
        self._speichern()
        return True

    def _k3_aktiv(self) -> bool:
        return sp.stufe(self.sperren) == 3 or self.drill_stufe == 3

    def einstieg_gesperrt(self, jetzt: float) -> str | None:
        if self.beenden:
            return "BEENDEN"
        if self.sperren:
            return "SPERRE_" + sorted(self.sperren)[0]
        if self.drill_stufe:
            return f"DRILL_K{self.drill_stufe}"
        if self.k1:
            return "K1"
        if self.tagesstopp_tag and self.tagesstopp_tag == self.tag:
            return "TAGESSTOPP"
        if jetzt < self.technik_pause_bis:
            return "TECHNIK_PAUSE"
        return None

    # ------------------------------------------------------------------------------------------------ Schutz
    def _konto(self) -> AccountSnapshot:
        return self.t.account()

    def _demo_wache(self) -> AccountSnapshot:
        konto = self._konto()                     # Fehler → laufen(): Wiederverbinden
        if konto.trade_mode is not HandelsModus.DEMO:
            self._sperren("NICHT_DEMO", f"Konto ist {konto.trade_mode}")
            raise Ende(f"NICHT_DEMO ({konto.trade_mode})")
        if konto.margin_mode is not KontoModus.HEDGING:
            raise Ende(f"Konto ist {konto.margin_mode}, nicht HEDGING – Fremdvolumen würde mit eigenen Positionen verschmelzen")
        if self.demo_pruefung is not None:
            grund = self.demo_pruefung()
            if grund:
                raise Ende(grund)
        return konto

    def schutz(self) -> None:
        jetzt = self.t.zeit()
        self._t_schutz = jetzt
        self._fill = False
        self._demo_wache()
        self._versatz(jetzt)
        assert self.abgleich is not None
        b = self.abgleich.laufen()
        # 1. Ergebnisse sofort anwenden – ein späterer Fehler in diesem Takt darf sie nicht verlieren (Abgleich hat sie gesehen)
        if b.k2 and self._sperren("STOP_OUT", "Stop-out beobachtet (K2)"):
            self._kill_eintrag(2, "STOP_OUT", 0.0, drill=False)
        if b.differenzen:
            self._sperren("NULLTOLERANZ", f"Abgleichdifferenz: {', '.join(b.differenzen)[:200]}")
        if b.unerwartet:
            self._sperren("NULLTOLERANZ", "Eigene Position ohne Operation im Journal")
        for v in self.lz.vorfaelle[self._vorfaelle_gesehen:]:
            if v["art"] in VORFALL_NULLTOLERANZ:
                self._sperren("NULLTOLERANZ", f"Vorfall {v['art']}")
        self._vorfaelle_gesehen = len(self.lz.vorfaelle)
        for satz in b.deal_saetze:
            self.buch.deal(satz)
            d = satz["daten"]
            if satz["code"] == "KAPITAL":
                self._kapital(Decimal(d["geld"]), int(d["zeit"]))
            if d["entry"] == "IN" and ids.ist_eigen(int(d["magic"])):
                self._fill_pruefpunkt = True
        if any(a.absicht_id.startswith("NOTSCHLUSS") for _, a in b.aktionen):
            self._sperren("NULLTOLERANZ", "Eigene Position > 30 s ohne Server-SL – wird geschlossen")
        # 2. Schutzaktionen, Meldungen, Anker, Grenzen
        for cid, a in b.aktionen:
            self.lz.ausfuehren(a, cid)
        for m in b.meldungen:
            self.melder.melden("WARNUNG", m)
        konto = self._konto()
        self._tag(jetzt, konto)
        self._grenzen(konto)
        if b.aktionen or b.deal_saetze or len(self.lz.ops) != self._ops_n or jetzt - self._t_technik >= HANDEL_TAKT_S:
            self._ops_n, self._t_technik = len(self.lz.ops), jetzt
            self._technik(jetzt)
        if self._fill_pruefpunkt:
            self.pruefpunkt("FILL")

    def _versatz(self, jetzt: float) -> None:
        """Serverversatz periodisch neu messen (Zeitumstellung beim Broker); bei Änderung Volllauf des Abgleichs."""
        messen = getattr(self.t, "messe_versatz", None)
        if not self.versatz_takt_s or messen is None or jetzt - self._t_versatz < self.versatz_takt_s:
            return
        self._t_versatz = jetzt
        alt = getattr(self.t, "versatz_s", None)
        try:                                             # kurz (≤ 2 s), damit Schutz und STOP-Datei nicht warten
            neu = messen(self.konf.broker_name(self.konf.probe_symbole[0]), versuche=20, warte_s=0.1)
        except Exception:  # noqa: BLE001 - Markt ruhig/geschlossen: alter Wert bleibt
            return
        if alt is not None and neu != alt:
            self.journal.schreiben("VORFALL", "VERSATZ_GEAENDERT", f"Serverversatz {alt / 3600:+.0f} h → {neu / 3600:+.0f} h",
                                   alt=alt, neu=neu)
            self.melder.melden("WARNUNG", f"Serverzeit umgestellt ({alt / 3600:+.0f} h → {neu / 3600:+.0f} h) – Abgleich voll.")
            if self.abgleich is not None:
                self.abgleich.volllauf_erzwingen()

    def _kapital(self, betrag: Decimal, zeit: int, *, schreiben: bool = True) -> None:
        """Ein-/Auszahlung verschiebt nur Anker, deren Equity-Lesung vor dem Deal lag (sonst ist sie schon enthalten). In derselben
        Sekunde fail-safe: Einzahlung zählt (Anker eher zu hoch), Auszahlung nicht (Anker eher zu hoch)."""
        def danach(anker_t: float) -> bool:
            return zeit >= int(anker_t) if betrag > ZERO else zeit > anker_t
        if self.loss_anker > ZERO and danach(self.loss_anker_t):
            self.loss_anker += betrag
            if schreiben:
                self._anker("LOSS_LOCK", self.loss_anker, "Kapitalbewegung", self.loss_anker_t)
        if self.tag_anker > ZERO and danach(self.tag_anker_t):
            self.tag_anker += betrag
            if schreiben:
                self._anker("TAG", self.tag_anker, "Kapitalbewegung", self.tag_anker_t)

    def _anker(self, art: str, wert: Decimal, grund: str, basis_t: float) -> None:
        if art == "LOSS_LOCK":
            self.loss_anker, self.loss_anker_t = wert, basis_t
            self.journal.schreiben("ANKER", "LOSS_LOCK", f"LOSS_LOCK-Anker gesetzt ({grund})", wert=str(wert), basis_t=basis_t)
        else:
            self.tag_anker, self.tag_anker_t = wert, basis_t
            self.journal.schreiben("ANKER", "TAG", f"Tagesanker gesetzt ({grund})", tag=self.tag, wert=str(wert), basis_t=basis_t)
        self._speichern()

    def server_tag(self, jetzt: float) -> str:
        versatz = getattr(self.t, "versatz_s", None) or 0.0
        return dt.datetime.fromtimestamp(jetzt + versatz, UTC).date().isoformat()

    def _tag(self, jetzt: float, konto: AccountSnapshot) -> None:
        tag = self.server_tag(jetzt)
        if tag != self.tag:
            self.tag = tag
            self._anker("TAG", konto.equity, "neuer Servertag", jetzt)

    def _grenzen(self, konto: AccountSnapshot) -> None:
        if limits.loss_lock(self.loss_anker, konto.equity, self.loss_prozent):
            self._sperren("LOSS_LOCK", f"Equity ≤ {100 - self.loss_prozent} % des Ankers – alle eigenen Positionen schließen")
        if limits.tagesstopp(self.tag_anker, konto.equity, self.budget_prozent) and self.tagesstopp_tag != self.tag:
            self.tagesstopp_tag = self.tag
            self.journal.schreiben("TAGESSTOPP", self.tag, "Tagesverlust-Stopp erreicht – keine Einstiege bis zum nächsten Servertag",
                                   tag=self.tag)
            self.melder.melden("WARNUNG", "Tagesverlust-Stopp erreicht – keine Einstiege bis zum nächsten Servertag.")
        if self.strategie is not None:
            fenster, ab, quote_max = self.s50
            trades = self.buch.geschlossene(Namensraum.STRATEGIE, self.zaehlstart)
            ausgeloest, q, n = limits.stop50(trades, fenster, ab, quote_max)
            if ausgeloest:
                self._sperren("STOP50", f"Trefferquote {q:.2%} der letzten {n} Trades ≤ {quote_max:.0%} – alles schließen")

    def _technik(self, jetzt: float) -> None:
        gesendet = sorted((o for o in self.lz.ops.values() if o.versuche >= 1 and o.t_gesendet >= self._technik_ab
                           and o.status not in (OpStatus.GEPLANT, OpStatus.GESENDET) and not o.absicht.absicht_id.startswith("SK-")),
                          key=lambda o: o.t_gesendet)[-TECHNIK_FENSTER:]
        fehler = sum(1 for o in gesendet if o.status is OpStatus.ABGELEHNT)
        if fehler >= TECHNIK_MAX_FEHLER:
            self.technik_pause_bis = jetzt + TECHNIK_PAUSE_S
            self._technik_ab = jetzt
            self.journal.schreiben("TECHNIK_PAUSE", "AUFFAELLIG", f"{fehler} von {len(gesendet)} Sendungen abgelehnt – 30 min keine Einstiege",
                                   fehler=fehler, fenster=len(gesendet))
            self.melder.melden("WARNUNG", f"Technik auffällig ({fehler} Ablehnungen) – 30 Minuten keine Einstiege.")
        for o in self.lz.ops.values():
            if o.status is OpStatus.UNBEKANNT and jetzt - (o.t_gesendet or o.t_geplant) > UNBEKANNT_MAX_S \
                    and o.op_id not in self._gemeldet_unbekannt:
                self._gemeldet_unbekannt.add(o.op_id)
                self._sperren("NULLTOLERANZ", f"Operation {o.op_id} länger als 15 min UNBEKANNT")

    # ------------------------------------------------------------------------------------------------ K3
    def _k3(self) -> None:
        eigene = [p for p in self.t.positions() if ids.ist_eigen(p.magic)]
        jetzt = self.t.zeit()
        if eigene:
            if self._k3_seit is None:
                self._k3_seit, self._k3_ausloeser = jetzt, "K3"
            for p in eigene:
                self.abbauen(p.ticket, p.symbol, p.side, p.volume, ids.namensraum(p.magic) or Namensraum.STRATEGIE, "K3")
            eigene = [p for p in self.t.positions() if ids.ist_eigen(p.magic)]
            jetzt = self.t.zeit()
        if not eigene:
            if self._k3_seit is not None:
                dauer = jetzt - self._k3_seit
                self.journal.schreiben("KILL_FLACH", "K3", f"Alle eigenen Positionen geschlossen ({self._k3_ausloeser})",
                                       ausloeser=self._k3_ausloeser, dauer_s=round(dauer, 3), drill=self.drill_stufe == 3)
                self.melder.melden("WARNUNG", f"K3: alle eigenen Positionen geschlossen nach {dauer:.0f} s.")
                self._k3_seit = None

    def abbauen(self, ticket: int, symbol: str, side: Side, lots: Decimal, ns: Namensraum, grund: str) -> Operation | None:
        """Abbau per Ticket; nie blind neu: läuft für dieses Ticket noch irgendein Abbau (egal welcher Grund), wird gewartet.
        Nach endgültiger Ablehnung (z. B. Markt zu) wartet der nächste Versuch 30 s, dann jeweils doppelt so lang (≤ 15 min)."""
        jetzt = self.t.zeit()
        absicht_id = f"{grund}-{ticket}"
        je_ticket = sorted((o for o in self.lz.ops.values() if o.absicht.action is Action.REDUCE_DEAL and o.absicht.ticket == ticket
                            and o.status is not OpStatus.LOKAL_ABGELEHNT), key=lambda o: o.t_geplant)
        if any(o.status in OFFEN for o in je_ticket):
            return None
        abgelehnt = 0
        for o in reversed(je_ticket):
            if o.status is not OpStatus.ABGELEHNT:
                break
            abgelehnt += 1
        if abgelehnt and jetzt - je_ticket[-1].t_geplant < min(ABBAU_PAUSE_MAX_S, ABBAU_PAUSE_S * 2 ** (abgelehnt - 1)):
            return None
        vorher = [o for o in je_ticket if o.absicht.absicht_id == absicht_id]
        a = Absicht(absicht_id, Action.REDUCE_DEAL, symbol, side.opposite, lots, ns, ticket=ticket, grund=grund)
        cid = ids.client_id(grund, symbol, ticket, "CLOSE", len(vorher))
        op = self.lz.ausfuehren(a, cid)
        if op.status is not OpStatus.LOKAL_ABGELEHNT:
            self._fill = True
        return op

    # ------------------------------------------------------------------------------------------------ Drill (F-03b, nur Probe)
    def drill(self, stufe: int, *, schlaf: Callable[[float], None] = time.sleep, frist_s: float = 120.0) -> float:
        """Kill-Drill über den echten Weg (STOP-Datei mit Kennung DRILL → Takt) ohne dauerhafte Sperre. Misst die Zeit vom Setzen
        der Datei bis zur Wirkung (K1/K2: Einstiege aus; K3: alle eigenen Positionen flach). Nur ohne STOP-Datei und Sperre."""
        stop = Path(self._pfad_stop)
        if stop.exists() or self.sperren:
            raise RuntimeError("Drill nur ohne STOP-Datei und ohne aktive Sperre.")
        t0 = self.t.zeit()
        if stufe == 3:
            self._k3_seit, self._k3_ausloeser = t0, "DRILL"
        stop.write_text(f"K{stufe} DRILL\n", encoding="utf-8")
        try:
            while True:
                schlaf(1.0)                              # Takt schläft zwischen zwei Prüfungen
                self.schritt()
                jetzt = self.t.zeit()
                if stufe < 3 and self.drill_stufe >= stufe and self.einstieg_gesperrt(jetzt):
                    self._kill_eintrag(stufe, "DRILL", jetzt - t0, drill=True)
                    return jetzt - t0
                if stufe == 3 and self.drill_stufe == 3 and self._k3_seit is None:
                    return jetzt - t0
                if jetzt - t0 > frist_s:
                    if stufe == 3:
                        self.journal.schreiben("KILL_FLACH", "K3", "Drill: Frist überschritten, nicht flach", ausloeser="DRILL",
                                               dauer_s=round(jetzt - t0, 3), drill=True, flach=False)
                    else:
                        self._kill_eintrag(stufe, "DRILL_FRIST", jetzt - t0, drill=True)
                    return jetzt - t0
        finally:
            stop.unlink(missing_ok=True)
            self.drill_stufe = 0
            if sp.stufe(self.sperren) < 3:
                self._k3_seit = None

    # ------------------------------------------------------------------------------------------------ Band-Prüfpunkt
    def bewertet(self, waehrung: str) -> list[bandmod.Bewertet]:
        aus = []
        for p in self.t.positions():
            ns = ids.namensraum(p.magic)
            if ns is None:
                continue
            spec = self.t.symbol(p.symbol)
            q = self.t.quote(p.symbol)
            kurs = q.bid if p.side is Side.BUY else q.ask
            if p.sl > ZERO:
                rest = max(ZERO, -sizing.ergebnis(spec, p.side, kurs, p.sl, p.volume))
            else:
                rest = sizing.nominal(spec, kurs, p.volume, waehrung)          # ohne SL: volles Nominal als Risiko
            rest += sizing.kosten(p.volume, self.konf.provision_je_lot_seite, 1)
            aus.append(bandmod.Bewertet(p, spec, sizing.nominal(spec, kurs, p.volume, waehrung), rest, ns is Namensraum.STRATEGIE))
        return aus

    def _pruefpunkt_faellig(self, jetzt: float) -> str | None:
        b = nach_berlin(dt.datetime.fromtimestamp(jetzt, UTC))
        h, m = self.tore["band"]["pruefpunkt_berlin"].split(":")
        if b.time() >= dt.time(int(h), int(m)) and self._pruefpunkt_tag != b.date().isoformat():
            return b.date().isoformat()
        return None

    def pruefpunkt(self, art: str) -> list[Operation]:
        konto = self._konto()
        offene = self.bewertet(konto.currency)
        zwang = bandmod.pruefpunkt(self.band, offene, konto.equity)
        h_strat = bandmod.hebel(sum((b.nominal for b in offene if b.strategie), ZERO), konto.equity)
        h_alle = bandmod.hebel(sum((b.nominal for b in offene), ZERO), konto.equity)
        self.journal.schreiben("PRUEFPUNKT", art, f"Band-Prüfpunkt {art}: Strategie {h_strat:.2f}, gesamt {h_alle:.2f}, "
                               f"{len(zwang)} Zwangsausstiege", hebel_strategie=f"{h_strat:.4f}", hebel_gesamt=f"{h_alle:.4f}",
                               zwang=[z.grund for z in zwang])
        ops = []
        for z in zwang:
            pos = next(b.position for b in offene if b.position.ticket == z.ticket)
            op = self.abbauen(z.ticket, z.symbol, z.side, z.lots, ids.namensraum(pos.magic) or Namensraum.STRATEGIE, z.grund)
            if op is not None:
                ops.append(op)
        if art == "FILL":
            self._fill_pruefpunkt = False                # erst nach Erfolg erledigt
        return ops

    # ------------------------------------------------------------------------------------------------ Handel
    def handel(self, jetzt: float) -> None:
        self._t_handel = jetzt
        if self.strategie is None:
            return
        halte = getattr(self.strategie, "max_halte_s", None)
        if halte:                                       # Zeitbarriere: eigener Ausstieg per Ticket, nie durch Sperren blockiert
            for p in self.t.positions():
                if ids.namensraum(p.magic) is Namensraum.STRATEGIE and jetzt - p.time >= halte:
                    self.abbauen(p.ticket, p.symbol, p.side, p.volume, Namensraum.STRATEGIE, "ZEITBARRIERE")
        tf = TF_S[self.strategie.zeitrahmen]
        for sym in self.strategie.symbole:
            name = self.konf.broker_name(sym)
            kerzen = [b for b in self.t.bars(name, self.strategie.zeitrahmen, int(jetzt - (self.strategie.rueckblick + 5) * tf * 3),
                                             int(jetzt)) if b.is_closed]
            if not kerzen or kerzen[-1].time <= self._letzte_kerze.get(name, 0):
                continue
            self._letzte_kerze[name] = kerzen[-1].time
            if jetzt - (kerzen[-1].time + tf) > 2 * HANDEL_TAKT_S:
                continue                                  # Kerze nicht frisch (Neustart, Lücke): kein verspätetes Signal
            sig = self.strategie.signal(sym, kerzen[-self.strategie.rueckblick:])
            if sig is not None:
                self.einstieg_strategie(sig, kerzen)

    def umrechnung(self, waehrung: str, gewinn: str) -> Decimal | None:
        if gewinn == waehrung:
            return Decimal(1)
        endungen = {""} | {v[len(k):] for k, v in self.konf.symbol_namen.items() if v.startswith(k)}   # z. B. ".a"
        for kandidat in (waehrung + gewinn, gewinn + waehrung):
            for name in dict.fromkeys([self.konf.broker_name(kandidat)] + [kandidat + e for e in sorted(endungen)]):
                try:
                    self.t.symbol(name)                  # wählt das Symbol in der Marktübersicht aus (sonst kein Tick)
                    q = self.t.quote(name)
                except Exception:  # noqa: BLE001 - Symbol gibt es nicht
                    continue
                wert = sizing.umrechnung_aus_kurs(waehrung, gewinn, kandidat, q.bid, q.ask)
                if wert is not None:
                    return wert
        return None

    def offener_einstieg(self) -> str | None:
        """Solange ein Einstieg unterwegs ist (Ausgang offen), zählen Band, Budget und Positionsgrenze nicht verlässlich."""
        if any(o.absicht.action is Action.ENTRY_DEAL and o.status in OFFEN for o in self.lz.ops.values()):
            return "OFFENE_OPERATION"
        return None

    def _signal_eintrag(self, ns: Namensraum, symbol: str, side: Side, ergebnis: str, grund: str, **daten: object) -> None:
        self.journal.schreiben("SIGNAL", ergebnis, f"{ns} {side} {symbol}: {ergebnis} {grund}".strip(), namensraum=str(ns),
                               symbol=symbol, side=str(side), grund=grund, **daten)

    def einstieg_strategie(self, sig: Signal, kerzen: list[Bar]) -> Operation | None:
        assert self.strategie is not None
        jetzt = self.t.zeit()
        name = self.konf.broker_name(sig.symbol)
        konto = self._konto()
        spec = self.t.symbol(name)
        q = self.t.quote(name)
        grund = self.einstieg_gesperrt(jetzt) or self.offener_einstieg() or \
            guards.einstieg(jetzt, konto, spec, q, kerzen, self.konf, self.margin_min)
        preis = q.ask if sig.side is Side.BUY else q.bid
        sl = rounding.sl_runden(sig.sl, sig.side, spec)
        tp = rounding.tp_runden(sig.tp, sig.side, spec)
        if not grund and (tp <= ZERO or not rounding.schutz_richtig(sig.side, preis, sl, tp)):
            grund = "SL_TP_UNGUELTIG"
        if not grund and not (rounding.abstand_ok(preis, sl, spec) and rounding.abstand_ok(preis, tp, spec)):
            grund = "STOPS_LEVEL"
        if not grund and abs(preis - sl) > self.stop_ziel_max * abs(tp - preis):
            grund = "STOP_ZU_ZIEL"
        if not grund:
            grund = sizing.gegenprobe(spec, self.umrechnung(konto.currency, spec.currency_profit))
        groesse = None
        if not grund:
            groesse = bandmod.einstieg_strategie(self.band, spec, konto.currency, sig.side, preis, sl, tp, equity=konto.equity,
                                                 offene=self.bewertet(konto.currency),
                                                 budget=limits.budget(self.tag_anker, konto.equity, self.budget_prozent),
                                                 provision=self.konf.provision_je_lot_seite)
            grund = "" if groesse.lots is not None else groesse.grund
        if grund or groesse is None or groesse.lots is None:
            self._signal_eintrag(Namensraum.STRATEGIE, name, sig.side, "ABGELEHNT", grund, kerze=sig.kerze)
            return None
        a = Absicht(f"S-{name}-{sig.kerze}", Action.ENTRY_DEAL, name, sig.side, groesse.lots, Namensraum.STRATEGIE, sl, tp,
                    grund=sig.grund[:40])
        op = self.lz.ausfuehren(a, ids.client_id(self.strategie.name, name, sig.kerze, "ENTRY"))
        self._signal_eintrag(Namensraum.STRATEGIE, name, sig.side, str(op.status), op.grund, kerze=sig.kerze, operation=op.op_id,
                             hebel=f"{groesse.hebel:.4f}", hebel_tp=f"{groesse.hebel_tp:.4f}", hebel_sl=f"{groesse.hebel_sl:.4f}")
        if op.status is not OpStatus.LOKAL_ABGELEHNT:
            self._fill = True
        return op

    # ------------------------------------------------------------------------------------------------ Zustand
    def _speichern(self) -> None:
        self.store.speichern({"modus": self.modus, "sperren": sorted(self.sperren), "tag": self.tag, "tag_anker": str(self.tag_anker),
                              "loss_anker": str(self.loss_anker), "tagesstopp_tag": self.tagesstopp_tag,
                              "mechanik_hash": self.mechanik, "strategie_hash": self.strat_hash})

    def status(self) -> dict:
        trades = self.buch.geschlossene(Namensraum.STRATEGIE, self.zaehlstart)
        return {"modus": self.modus, "sperren": sorted(self.sperren), "k1": self.k1, "tagesstopp": self.tagesstopp_tag == self.tag,
                "technik_pause": self.t.zeit() < self.technik_pause_bis, "trades": limits.stand95(trades),
                "mechanik_hash": self.mechanik[:16], "strategie_hash": self.strat_hash[:16]}
