"""Backtest-Runner (Plan F-1 §4 „ein Takt für alles“, §5 Tor 85): kit.run.loop.Bot über dem BacktestTerminal, Historienkerzen.

Schritt je H1-Schluss jetzt = T + 1 h (T = Kerzenbeginn, Vereinigung über alle Symbole), in dieser Reihenfolge:
  1. Servertageswechsel in (vorheriger Schritt, T]: Swap für offene Positionen (Rollover lag in einer Lücke, z. B. Wochenende)
  2. H1-Kerzen aller Symbole mit Beginn T abspielen: SL/TP nach SIM-Regeln (Lücke = Eröffnungskurs, SL vor TP), Kurs = Schluss
  3. Mittelkurse → Kreuzkurs EURJPY → Tickwerte; Kerzen höherer Zeitrahmen mit Schluss ≤ jetzt in den Speicher
  4. Servertageswechsel genau bei jetzt: Swap (Positionen, die in der Kerze davor per SL/TP schlossen, zahlen ihn nicht)
  5. Bot.schritt(): Schutz/Abgleich, Grenzen, Band-Prüfpunkt, Handel (Zeitbarriere, Signal der abgeschlossenen Kerze, Einstieg)
  6. Equity (inkl. schwebender Ergebnisse) in die Kurve
Kein Schritt sieht eine Kerze vor ihrem Schluss (BacktestTerminal prüft fail-closed).

Sperrereignisse LOSS_LOCK und STOP50 werden als Schatten weitergerechnet (Equity läuft durch, Plan §5): Der Takt bucht sie als
SCHATTEN-Satz statt als Sperre; der Trade-Test wertet jedes Ereignis als nicht bestanden. Jede andere Sperre oder ein Vorfall
(Abgleichdifferenz, Programmfehler) macht den Lauf technisch ungültig (Ergebnis.technik_ok = False). Tagesstopp, Technik-Pause,
Band, Budget und Handelsfenster wirken wie im Betrieb.

Gezählt wird mit dem Tradebuch des Takts (Zählregeln config/tore.toml): Trade = Position bis zur vollständigen Schließung, Ergebnis =
Summe aller Deals inkl. Kommission und Swap. R = Ergebnis / geplanter Verlust bis SL (inkl. Kommission beider Seiten).

Journal: Der Takt schreibt dieselben Sätze mit derselben Hashkette, im Backtest aber in den Arbeitsspeicher (SpeicherJournal) statt je
Satz in eine Datei – über 11 Jahre sind das Zehntausende Sätze je Lauf, und viele parallele Läufe bremsten sich beim Dateizugriff aus.
Die Gleichheit beider Wege prüft kit_tests/test_backtest.py (Datei- und Speicherjournal liefern bytegleiche Ergebnisse).
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from kit.backtest import kosten
from kit.backtest.kosten import Kostenprofil
from kit.backtest.terminal import TF_S, BacktestTerminal
from kit.broker.sim import Uhr
from kit.config import Konfiguration
from kit.config import laden as konf_laden
from kit.domain import rounding
from kit.domain.types import ZERO, Action, Bar, Deal, Namensraum, OpStatus, Side
from kit.gates import ROOT, tore
from kit.gates.trade_test import Einstieg, TestTrade
from kit.risk import limits
from kit.run.loop import Bot
from kit.run.melder import ListenMelder
from kit.state import journal as journalmod
from kit.state.journal import Journal
from kit.strategy.base import Signal, Strategie

UTC = dt.UTC
H1_S = TF_S["H1"]
SCHATTEN = frozenset({"LOSS_LOCK", "STOP50"})
AUSSTIEGE = {"SL": "SL", "TP": "TP", "ZEITBARRIERE": "ZEITBARRIERE", "BAND_BODEN": "BAND_BODEN", "BAND_DECKEL": "BAND_DECKEL", "K3": "K3"}


@dataclass(frozen=True)
class Einstellungen:
    kostenprofil: Kostenprofil
    start_equity: Decimal = Decimal("10000")
    hebel: int = 100
    versatz_s: int = 10800


@dataclass(frozen=True)
class TradeDetail:
    """Ein geschlossener Strategie-Trade mit Preisen (für Parität, Handrechnung und Zufallsbasis)."""

    position_id: int
    symbol: str
    side: Side
    lots: Decimal
    t_auf: int
    preis_auf: Decimal
    sl: Decimal
    tp: Decimal
    t_zu: int
    preis_zu: Decimal
    grund: str
    ergebnis: Decimal
    gewinn_brutto: Decimal
    provision: Decimal
    swap: Decimal
    tick_value_auf: Decimal


@dataclass
class Ergebnis:
    strategie: str
    strategie_hash: str
    mechanik_hash: str
    kostenprofil: dict
    trades: list[TestTrade] = field(default_factory=list)
    details: list[TradeDetail] = field(default_factory=list)
    offen_am_ende: int = 0
    kurve: list[tuple[int, Decimal]] = field(default_factory=list)
    signale: list[dict] = field(default_factory=list)
    schatten: list[dict] = field(default_factory=list)
    sperren: list[str] = field(default_factory=list)
    vorfaelle: list[dict] = field(default_factory=list)
    tagesstopps: int = 0
    einstieg_nachteil_ticks: list[int] = field(default_factory=list)   # Fill gegen den erwarteten Einstieg e der Strategie
    schritte: int = 0
    erste_zeit: int = 0
    letzte_zeit: int = 0

    @property
    def technik_ok(self) -> bool:
        return not self.sperren and not self.vorfaelle


class SpeicherJournal(Journal):
    """Journal mit denselben Sätzen, Schlüsselprüfung und Hashkette wie kit.state.journal.Journal, aber im Arbeitsspeicher."""

    def __init__(self, ordner: Path, uhr) -> None:
        self._saetze: list[dict] = []
        super().__init__(ordner, uhr=uhr, fsync=False)       # leerer Ordner: liest nichts, schreibt nichts

    def schreiben(self, art: str, code: str, text: str, **daten: object) -> dict:
        journalmod._pruefe_schluessel(daten)
        satz = {"seq": self._seq + 1, "t": round(self.uhr(), 6), "art": art, "code": code, "text": text, "daten": daten, "prev": self._kopf}
        satz = json.loads(json.dumps(satz, ensure_ascii=False, default=str))   # Decimal -> str, Form wie beim Lesen
        satz["h"] = journalmod._hash(satz)
        self._saetze.append(satz)
        self._seq, self._kopf = satz["seq"], satz["h"]
        return satz

    def lesen(self) -> list[dict]:
        return list(self._saetze)

    def hat_eintraege(self) -> bool:
        return bool(self._saetze)


class BacktestBot(Bot):
    """Der Takt unverändert – nur LOSS_LOCK/STOP50 als Schattenereignis, der Einstiegskontext für die Band-Prüfung und (Standard)
    das Journal im Arbeitsspeicher."""

    def __init__(self, *args, speicher_journal: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if speicher_journal:
            if self.journal.hat_eintraege():
                raise RuntimeError("Backtest-Ablage nicht leer")
            self.journal = SpeicherJournal(self.ablage / "journal", self.t.zeit)
            self.lz.j = self.journal                          # der Lebenszyklus schreibt in dasselbe Journal
        self.schatten: list[dict] = []
        self._schatten_aktiv: dict[str, bool] = {}
        self._schatten_jetzt: set[str] = set()
        self.einstiege: dict[int, Einstieg] = {}
        self.einstieg_nachteil: dict[int, int] = {}       # Ticks, um die der Fill schlechter ist als e = Schluss (+ Spread) der Signalkerze

    def _sperren(self, grund: str, text: str) -> bool:
        if grund not in SCHATTEN:
            return super()._sperren(grund, text)
        self._schatten_jetzt.add(grund)
        if not self._schatten_aktiv.get(grund):
            self._schatten_aktiv[grund] = True
            konto = self._konto()
            self.schatten.append({"art": grund, "t": int(self.t.zeit()), "equity": str(konto.equity), "text": text[:120]})
            self.journal.schreiben("SCHATTEN", grund, f"Schattenereignis {grund} – Backtest rechnet weiter: {text}"[:200])
        return False

    def _grenzen(self, konto) -> None:
        self._schatten_jetzt = set()
        super()._grenzen(konto)
        for grund in SCHATTEN - self._schatten_jetzt:
            self._schatten_aktiv[grund] = False          # Bedingung vorbei: ein späteres Eintreten ist ein neues Ereignis

    def einstieg_strategie(self, sig: Signal, kerzen: list[Bar]):
        name = self.konf.broker_name(sig.symbol)
        konto = self._konto()                            # nur lesen (wie der Takt selbst), vor dem Einstieg
        spec = self.t.symbol(name)
        q = self.t.quote(name)
        offene = self.bewertet(konto.currency)
        budget = limits.budget(self.tag_anker, konto.equity, self.budget_prozent)
        op = super().einstieg_strategie(sig, kerzen)
        if op is not None and op.status in (OpStatus.ERLEDIGT, OpStatus.TEILWEISE) and op.order:
            k = kerzen[-1]
            preis = q.ask if sig.side is Side.BUY else q.bid
            e = k.close + k.spread_points * spec.point if sig.side is Side.BUY else k.close
            self.einstieg_nachteil[op.order] = int((preis - e) * sig.side.sign / spec.point)
            self.einstiege[op.order] = Einstieg(
                symbol=name, side=str(sig.side), t=int(self.t.zeit()), lots=op.absicht.volume,
                preis=q.ask if sig.side is Side.BUY else q.bid, sl=rounding.sl_runden(sig.sl, sig.side, spec),
                tp=rounding.tp_runden(sig.tp, sig.side, spec), equity=konto.equity, budget=budget,
                provision=self.konf.provision_je_lot_seite, waehrung=konto.currency, tick_size=spec.tick_size,
                tick_value=spec.tick_value, contract_size=spec.contract_size, currency_base=spec.currency_base,
                volume_min=spec.volume_min, volume_step=spec.volume_step, volume_max=spec.volume_max,
                offene_nominal=sum((b.nominal for b in offene), ZERO), offene_risiko=sum((b.restrisiko for b in offene), ZERO))
        return op


def bot_konfiguration() -> Konfiguration:
    """Betriebskonfiguration aus config/kit_demo.toml (ohne rechnerspezifische lokal.toml): Fenster, Wächter, Provision der Größe."""
    return konf_laden(ROOT / "config" / "kit_demo.toml")


def _zeiten(h1: Mapping[str, Sequence[Bar]]) -> list[int]:
    return sorted({b.time for kerzen in h1.values() for b in kerzen})


def _pruefe_reihen(h1: Mapping[str, Sequence[Bar]], tf_kerzen: Mapping[str, Sequence[Bar]] | None) -> None:
    for reihen in (h1, tf_kerzen or {}):
        for sym, kerzen in reihen.items():
            for a, b in zip(kerzen, kerzen[1:], strict=False):
                if b.time <= a.time:
                    raise ValueError(f"{sym}: Kerzen nicht streng aufsteigend ({a.time} → {b.time})")
            if any(k.symbol != sym for k in kerzen):
                raise ValueError(f"{sym}: Kerze mit fremdem Symbol")


def laufen(strategie: Strategie, h1: Mapping[str, Sequence[Bar]], ablage: Path, einst: Einstellungen, *,
           tf_kerzen: Mapping[str, Sequence[Bar]] | None = None, konf: Konfiguration | None = None,
           tor_werte: dict | None = None, speicher_journal: bool = True) -> Ergebnis:
    """Ein Backtest-Lauf über die ganze Kerzenreihe. h1 enthält alle gehandelten Symbole plus EURUSD (und USDJPY bei JPY-Paaren)
    für die Umrechnung; tf_kerzen die Kerzen des Strategie-Zeitrahmens, wenn dieser nicht H1 ist. ablage = leerer Arbeitsordner."""
    tf = strategie.zeitrahmen
    if tf != "H1" and not tf_kerzen:
        raise ValueError(f"Strategie-Zeitrahmen {tf} braucht tf_kerzen")
    if einst.versatz_s % H1_S:
        raise ValueError("Serverversatz muss ein Vielfaches einer Stunde sein")
    if einst.kostenprofil.fx_gebuehr != 0:
        raise ValueError("Umrechnungsgebühr wirkt im SIM-Geldpfad nicht – Kostenprofil mit fx_gebuehr ≠ 0 abgelehnt (fail-closed)")
    fehlend = [s for s in strategie.symbole if s not in h1]
    jpy = any(s.endswith("JPY") for s in h1)
    fehlend += [s for s in ("EURUSD", "USDJPY") if s not in h1 and (s == "EURUSD" or jpy)]
    if fehlend:
        raise ValueError(f"H1-Kerzen fehlen für {fehlend} (gehandelte Symbole und Umrechnung)")
    _pruefe_reihen(h1, tf_kerzen if tf != "H1" else None)
    zeiten = _zeiten(h1)
    if not zeiten:
        raise ValueError("keine Kerzen")
    uhr = Uhr(zeiten[0] + H1_S)
    term = BacktestTerminal(sorted(h1), kostenprofil=einst.kostenprofil, balance=einst.start_equity, uhr=uhr, hebel=einst.hebel,
                            versatz_s=einst.versatz_s)
    bot = BacktestBot(term, Path(ablage), konf or bot_konfiguration(), modus="backtest", strategie=strategie, melder=ListenMelder(),
                      journal_fsync=False, tor_werte=tor_werte or tore(), speicher_journal=speicher_journal)
    zeiger = {s: 0 for s in h1}
    tf_zeiger = {s: 0 for s in (tf_kerzen or {})} if tf != "H1" else {}
    erg = Ergebnis(strategie.name, bot.strat_hash, bot.mechanik, einst.kostenprofil.beschreibung())
    vorher: int | None = None
    gestartet = False
    for t in zeiten:
        jetzt = t + H1_S
        uhr.t = float(jetzt)
        wechsel = kosten.servertag_wechsel(vorher, jetzt, einst.versatz_s) if vorher is not None else []
        for b in (w for w in wechsel if w < jetzt):
            term.swap_buchen(kosten.swap_faktor(kosten.wochentag_der_nacht(b, einst.versatz_s), einst.kostenprofil.dreifachtag))
        _kerzen_abspielen(term, h1, zeiger, t)
        term.umrechnung_aktualisieren()
        if tf_zeiger:
            _zeitrahmen_einstellen(term, tf_kerzen or {}, tf_zeiger, tf, jetzt)
        if wechsel and wechsel[-1] == jetzt:
            term.swap_buchen(kosten.swap_faktor(kosten.wochentag_der_nacht(jetzt, einst.versatz_s), einst.kostenprofil.dreifachtag))
        if not gestartet:
            bot.starten()
            gestartet = True
        bot.schritt()
        erg.kurve.append((jetzt, term.account().equity))
        erg.schritte += 1
        vorher = jetzt
    bot.schutz()                                          # letzte Takt-Schließungen ins Tradebuch
    erg.erste_zeit, erg.letzte_zeit = zeiten[0] + H1_S, int(uhr())
    _auswerten(erg, bot, term)
    return erg


def _kerzen_abspielen(term: BacktestTerminal, h1: Mapping[str, Sequence[Bar]], zeiger: dict[str, int], t: int) -> None:
    for sym in sorted(h1):
        kerzen, i = h1[sym], zeiger[sym]
        if i < len(kerzen) and kerzen[i].time == t:
            term.kerze_spielen(kerzen[i])
            zeiger[sym] = i + 1


def _zeitrahmen_einstellen(term: BacktestTerminal, tf_kerzen: Mapping[str, Sequence[Bar]], zeiger: dict[str, int], tf: str,
                           jetzt: int) -> None:
    dauer = TF_S[tf]
    for sym in sorted(tf_kerzen):
        kerzen = tf_kerzen[sym]
        while zeiger[sym] < len(kerzen) and kerzen[zeiger[sym]].time + dauer <= jetzt:
            term.zeitrahmen_kerze(kerzen[zeiger[sym]], tf)
            zeiger[sym] += 1


# ---------------------------------------------------------------------------------------------------- Auswertung
def _auswerten(erg: Ergebnis, bot: BacktestBot, term: BacktestTerminal) -> None:
    deals = term.deals(0, 2**62)
    je_position: dict[int, list[Deal]] = {}
    for d in deals:
        if d.side is not None and d.position_id:
            je_position.setdefault(d.position_id, []).append(d)
    abbau_grund: dict[int, str] = {}
    for op in bot.lz.ops.values():
        if op.absicht.action is Action.REDUCE_DEAL and op.absicht.ticket and op.status in (OpStatus.ERLEDIGT, OpStatus.TEILWEISE):
            abbau_grund[op.absicht.ticket] = op.absicht.grund
    provision = term.kostenprofil.provision()
    for tr in bot.buch.geschlossene(Namensraum.STRATEGIE, 0):
        liste = je_position.get(tr.position_id, [])
        ein = next((d for d in liste if d.entry == "IN"), None)
        aus = [d for d in liste if d.entry in ("OUT", "OUT_BY")]
        e = bot.einstiege.get(tr.position_id)
        if ein is None or not aus or e is None:
            erg.vorfaelle.append({"art": "TRADE_UNVOLLSTAENDIG", "position_id": tr.position_id})
            continue
        letzter = aus[-1]
        grund = letzter.reason if letzter.reason in ("SL", "TP") else AUSSTIEGE.get(abbau_grund.get(tr.position_id, ""), "SONST")
        spec_auf = term.eroeffnung.get(tr.position_id)
        tv = spec_auf.tick_value if spec_auf else e.tick_value
        risiko = abs(ein.price - e.sl) / e.tick_size * tv * tr.lots_ein + 2 * provision * tr.lots_ein
        side = Side(str(ein.side))
        erg.trades.append(TestTrade(symbol=tr.symbol, side=str(side), t_auf=tr.t_auf, t_zu=tr.t_zu, ergebnis=tr.ergebnis, risiko=risiko,
                                    grund=grund, einstieg=e))
        erg.details.append(TradeDetail(
            position_id=tr.position_id, symbol=tr.symbol, side=side, lots=tr.lots_ein, t_auf=tr.t_auf, preis_auf=ein.price, sl=e.sl, tp=e.tp,
            t_zu=tr.t_zu, preis_zu=letzter.price, grund=grund, ergebnis=tr.ergebnis, gewinn_brutto=sum((d.profit for d in liste), ZERO),
            provision=sum((d.commission for d in liste), ZERO), swap=sum((d.swap for d in liste), ZERO), tick_value_auf=tv))
    erg.offen_am_ende = sum(1 for p in term.positions() if p.ticket in bot.einstiege)
    erg.einstieg_nachteil_ticks = [bot.einstieg_nachteil[d.position_id] for d in erg.details if d.position_id in bot.einstieg_nachteil]
    saetze = bot.journal.lesen()
    for s in saetze:
        d = s.get("daten", {})
        if s["art"] == "SIGNAL" and d.get("namensraum") == str(Namensraum.STRATEGIE):
            erg.signale.append({"symbol": d.get("symbol"), "kerze": d.get("kerze"), "side": d.get("side"), "ergebnis": s["code"],
                                "grund": d.get("grund", ""), "t": s["t"]})
        elif s["art"] == "TAGESSTOPP":
            erg.tagesstopps += 1
        elif s["art"] == "VORFALL":
            erg.vorfaelle.append({"art": s["code"], "t": s["t"], "text": s.get("text", "")[:160]})
    erg.vorfaelle += [{"art": v.get("art"), "text": str(v.get("text", ""))[:160]} for v in bot.lz.vorfaelle]
    erg.schatten = list(bot.schatten)
    erg.sperren = sorted(bot.sperren)


def bars_bis(kerzen: Sequence[Bar], bis: int) -> list[Bar]:
    """Kerzen mit Beginn < bis (Hilfe für Tests und Präfix-Läufe)."""
    zeiten = [b.time for b in kerzen]
    return list(kerzen[:bisect.bisect_left(zeiten, bis)])
