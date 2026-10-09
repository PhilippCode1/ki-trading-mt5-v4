"""Abgleich Journal ↔ Broker für einen Betreiber (Herkunft: mt5-trading-ai execution/reconcile.py, v4 MONEYPATH_SPEC §5.8,
für einen Betreiber geändert: eigene SL/TP-Ausführung = normaler Ausstieg, keine Zwei-Personen-Freigabe).

- SL/TP-Ausführung einer eigenen Position: eigener Ausstieg (Preis, Gebühr, Swap gebucht), kein Halt.
- Stop-out (Grund SO): K2 + Meldung (Margin erschöpft – schweres Risikoereignis).
- Ein-/Auszahlungen (KAPITAL) verschieben Anker, nie Fremdaktivität; Gebühren/Zinsen (GEBUEHR, SONSTIGES) sind Kosten.
- Manueller Eingriff (CLIENT/MOBILE/WEB) an eigener Position: Einstiege im Symbol gesperrt + Meldung. Zuordnung über die
  Positions-ID: ein Handschluss im Terminal trägt magic 0, SL/TP-Schlüsse mancher Broker ebenfalls; Python-Aufträge tragen
  DEAL_REASON_EXPERT und den magic des Auftrags (MQL5-Doku/-Buch, Recherche F-03b).
- Fremde Positionen/Deals (fremder oder fehlender magic): Einstiege im Symbol gesperrt; nie automatisch angefasst. Im
  Netting-Konto (Fremdvolumen verschmilzt mit der eigenen Position) gibt es dann auch keine automatische Schutzaktion.
- Eigene Position ohne Server-SL: SL innerhalb von 30 s setzen (geplanter SL), sonst per Ticket schließen.
- Jeder verarbeitete Deal wird als DEAL-Satz journalisiert und nach einem Neustart nicht erneut gezählt.
- Deals vor `ab_zeit` (Beginn dieses Journals) gehören zu keinem Lauf dieser Ablage und werden nicht bewertet (z. B. Probe-
  Historie beim ersten Demo-Live-Start); eigene offene Positionen ohne Operation sperren trotzdem.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from kit.domain.types import ZERO, Absicht, Action, Deal, DealArt, KontoModus, OpStatus, Position
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.state.journal import Journal

SCHUTZ_FRIST_S = 30.0
RUECKBLICK_S = 3 * 86400.0
UEBERLAPP_S = 3 * 3600.0                  # Folgeläufe lesen ab letztem Lauf − 3 h (Zeitumstellung des Servers, späte Deals)
VOLLLAUF_S = 3600.0                       # stündlich wieder das volle Rückblickfenster
HERZSCHLAG_S = 3600.0
MANUELL = frozenset({"CLIENT", "MOBILE", "WEB"})
FREMD_SPERREN = frozenset({"FREMDAKTIVITAET", "FREMDPOSITION", "MANUELLER_EINGRIFF"})


@dataclass
class Bericht:
    eigene: list[Position] = field(default_factory=list)
    fremde: list[Position] = field(default_factory=list)
    server_ausstiege: list[Deal] = field(default_factory=list)
    stop_outs: list[Deal] = field(default_factory=list)
    manuelle_eingriffe: list[Deal] = field(default_factory=list)
    fremd_deals: list[Deal] = field(default_factory=list)
    unerwartet: list[Position] = field(default_factory=list)
    kapital: Decimal = ZERO
    kosten: Decimal = ZERO
    neue_deals: int = 0
    aktionen: list[tuple[str, Absicht]] = field(default_factory=list)
    k2: bool = False
    meldungen: list[str] = field(default_factory=list)
    differenzen: list[str] = field(default_factory=list)
    deal_saetze: list[dict] = field(default_factory=list)

    @property
    def auffaellig(self) -> bool:
        return bool(self.differenzen or self.unerwartet or self.aktionen or self.fremde or self.k2 or self.neue_deals
                    or self.meldungen)


def buch_aus_deals(modus: KontoModus, deals: Iterable[Deal]) -> dict[str, Decimal]:
    """Positionsbuch aus Handelsdeals (jedes Deal-Ticket einmal): Netting je Symbol, Hedging je Positions-ID."""
    gesehen: set[int] = set()
    buch: dict[str, Decimal] = {}
    for d in deals:
        if d.art is not DealArt.HANDEL or d.side is None or d.ticket in gesehen:
            continue
        gesehen.add(d.ticket)
        schluessel = str(d.position_id) if modus is KontoModus.HEDGING else d.symbol
        buch[schluessel] = buch.get(schluessel, ZERO) + d.volume * d.side.sign
    return {k: v for k, v in buch.items() if v != ZERO}


class Abgleich:
    def __init__(self, lz: Lebenszyklus, journal: Journal, *, schutz_frist_s: float = SCHUTZ_FRIST_S,
                 rueckblick_s: float = RUECKBLICK_S, ab_zeit: float = 0.0) -> None:
        self.lz = lz
        self.ab_zeit = ab_zeit
        self.j = journal
        self.schutz_frist_s = schutz_frist_s
        self.rueckblick_s = rueckblick_s
        self.gesehen: dict[int, int] = {}                 # Deal-Ticket → Zeit
        self.deal_position: dict[int, int] = {}           # Deal-Ticket → Positions-ID
        self.geschlossene_positionen: set[int] = set()
        self.ohne_sl_seit: dict[int, float] = {}
        self.letzter_herzschlag: float = 0.0
        self._letzter_lauf: float | None = None
        self._letzter_volllauf: float = 0.0
        self._geprueft: set[str] = set()                 # Einstiegsoperationen, deren Position nachweislich geschlossen ist
        self._menge: dict[tuple[int, str], Decimal] = {}  # (magic, IN/OUT) → beobachtete Lots eigener Deals (Doppel-Fill-Erkennung)
        self.eigene_pos: dict[int, int] = {}              # Positions-ID → magic der eigenen Eröffnung
        self._n = 0
        self._wiederherstellen()

    def _wiederherstellen(self) -> None:
        for satz in self.j.lesen():
            if satz["art"] != "DEAL":
                continue
            d = satz["daten"]
            self.gesehen[int(d["deal"])] = int(d["zeit"])
            self.deal_position[int(d["deal"])] = int(d["position_id"])
            if d.get("deal_art") == "HANDEL" and ids.ist_eigen(int(d["magic"])):
                schluessel = (int(d["magic"]), "IN" if d["entry"] == "IN" else "OUT")
                self._menge[schluessel] = self._menge.get(schluessel, ZERO) + Decimal(str(d["volumen"]))
                if d["entry"] == "IN":
                    self.eigene_pos[int(d["position_id"])] = int(d["magic"])
                self._deal_zur_operation(int(d["magic"]), int(d["deal"]))
            if d["entry"] in ("OUT", "OUT_BY", "INOUT"):
                self.geschlossene_positionen.add(int(d["position_id"]))

    def _deal_zur_operation(self, magic: int, deal: int) -> None:
        """Erledigt ohne Deal-Ticket (10009 mit deal=0): das beobachtete Ticket nachtragen, damit die Positionsprüfung greift."""
        op = self.lz.op_mit_magic(magic)
        if op is not None and deal not in op.deals:
            op.deals.append(deal)

    def volllauf_erzwingen(self) -> None:
        self._letzter_lauf = None

    def _doppel_fill(self, d: Deal) -> None:
        """Mehr Lots unter einem magic als die Absicht wollte = doppelte Ausführung (z. B. Auftrag zweimal ausgeführt)."""
        richtung = "IN" if d.entry == "IN" else "OUT"
        schluessel = (d.magic, richtung)
        self._menge[schluessel] = self._menge.get(schluessel, ZERO) + d.volume
        op = self.lz.op_mit_magic(d.magic)
        if op is None:
            return
        erwartet = op.absicht.action is (Action.ENTRY_DEAL if richtung == "IN" else Action.REDUCE_DEAL)
        if erwartet and self._menge[schluessel] > op.absicht.volume:
            self.lz.vorfall("DOPPEL_FILL", f"{self._menge[schluessel]} Lots unter einer Operation ({op.op_id}), gewollt "
                            f"{op.absicht.volume}", op_id=op.op_id, symbol=d.symbol)
            self.lz.sperren(d.symbol, "DOPPEL_FILL")

    def _cid(self, art: str, ticket: int) -> str:
        self._n += 1
        return ids.client_id("ABGLEICH", art, int(self.lz.uhr()), str(ticket), self._n)

    def laufen(self) -> Bericht:
        t = self.lz.t
        jetzt = self.lz.uhr()
        b = Bericht()
        self.lz.klaeren()
        positionen = t.positions()                         # zuerst Bestand, dann Historie (kein Fehlalarm bei Schluss dazwischen)
        for p in positionen:
            if ids.ist_eigen(p.magic):
                self.eigene_pos.setdefault(p.ticket, p.magic)
        modus = t.account().margin_mode
        if self._letzter_lauf is None or jetzt - self._letzter_volllauf >= VOLLLAUF_S:
            seit = jetzt - self.rueckblick_s
            self._letzter_volllauf = jetzt
        else:
            seit = min(self._letzter_lauf, jetzt) - UEBERLAPP_S
        self._letzter_lauf = jetzt
        for d in sorted(t.deals(int(seit), int(jetzt) + 3600), key=lambda x: x.ticket):
            if d.ticket in self.gesehen or (d.time < self.ab_zeit and self.lz.op_mit_magic(d.magic) is None):
                continue                                   # Vorgeschichte ohne eigene Operation (Zeitumrechnung kann springen)
            self.gesehen[d.ticket] = d.time
            self._deal(d, b)
        grenze = jetzt - 2 * self.rueckblick_s
        self.gesehen = {k: v for k, v in self.gesehen.items() if v >= grenze}
        for p in positionen:
            self._position(p, b, jetzt, modus)
        self._differenzen(b, positionen)
        if b.auffaellig or jetzt - self.letzter_herzschlag >= HERZSCHLAG_S:
            self.j.schreiben("ABGLEICH", "OK" if not (b.differenzen or b.unerwartet) else "DIFFERENZ",
                             f"Abgleich: {len(b.eigene)} eigene, {len(b.fremde)} fremde Positionen, {len(b.aktionen)} Schutzaktionen",
                             eigene=len(b.eigene), fremde=len(b.fremde), aktionen=len(b.aktionen), differenzen=b.differenzen,
                             kapital=str(b.kapital), kosten=str(b.kosten), k2=b.k2, neue_deals=b.neue_deals)
            self.letzter_herzschlag = jetzt
        return b

    def _eigener_auftrag(self, d: Deal) -> bool:
        """Deal aus einem eigenen Auftrag (gleiche Order bzw. bekanntes Ticket), auch wenn der Server einen Handgrund meldet."""
        op = self.lz.op_mit_magic(d.magic) if ids.ist_eigen(d.magic) else None
        return op is not None and (bool(op.order and d.order == op.order) or d.ticket in op.deals)

    def _deal(self, d: Deal, b: Bericht) -> None:
        b.neue_deals += 1
        eigen = ids.ist_eigen(d.magic)
        if eigen and d.entry == "IN" and d.art is DealArt.HANDEL:
            self.eigene_pos[d.position_id] = d.magic
        pos_magic = d.magic if eigen else self.eigene_pos.get(d.position_id)
        self.deal_position[d.ticket] = d.position_id
        if d.entry in ("OUT", "OUT_BY", "INOUT"):
            self.geschlossene_positionen.add(d.position_id)
        if d.art is DealArt.KAPITAL:
            klasse = "KAPITAL"
            b.kapital += d.geld
        elif d.art is not DealArt.HANDEL:
            klasse = "KOSTEN"
            b.kosten += d.geld
        elif d.reason == "SO":
            klasse = "STOP_OUT"
            b.stop_outs.append(d)
            b.k2 = True
            b.meldungen.append(f"Stop-out in {d.symbol} – K2, Betreiber prüfen")
            self.lz.vorfall("STOP_OUT", f"Stop-out {d.symbol}", symbol=d.symbol, deal=d.ticket, geld=str(d.geld))
        elif pos_magic and d.reason in ("SL", "TP"):
            klasse = "SERVER_AUSSTIEG"
            b.server_ausstiege.append(d)
        elif pos_magic and d.reason in MANUELL and not self._eigener_auftrag(d):
            klasse = "MANUELLER_EINGRIFF"
            b.manuelle_eingriffe.append(d)
            b.meldungen.append(f"Manueller Eingriff an eigener Position in {d.symbol} – Einstiege gesperrt")
            self.lz.sperren(d.symbol, "MANUELLER_EINGRIFF")
        elif eigen:
            klasse = "EIGEN"
            self._doppel_fill(d)
            self._deal_zur_operation(d.magic, d.ticket)
            if self.lz.op_mit_magic(d.magic) is None:
                klasse = "EIGEN_OHNE_OPERATION"
                self.lz.vorfall("EIGENER_DEAL_OHNE_OPERATION", f"Eigener Deal ohne Journal in {d.symbol}", symbol=d.symbol,
                                deal=d.ticket)
                self.lz.sperren(d.symbol, "EIGENER_DEAL_OHNE_OPERATION")
        else:
            klasse = "FREMD"
            b.fremd_deals.append(d)
            b.meldungen.append(f"Fremdaktivität in {d.symbol} – Einstiege gesperrt, nichts wird angefasst")
            self.lz.sperren(d.symbol, "FREMDAKTIVITAET")
        b.deal_saetze.append(self.j.schreiben(
            "DEAL", klasse, f"Deal {d.ticket} {d.symbol} {d.entry} {d.reason} → {klasse}", deal=d.ticket, position_id=d.position_id,
            symbol=d.symbol, entry=d.entry, reason=d.reason, magic=d.magic, deal_art=str(d.art), geld=str(d.geld), preis=str(d.price),
            volumen=str(d.volume), zeit=d.time))

    def _position(self, p: Position, b: Bericht, jetzt: float, modus: KontoModus) -> None:
        if not ids.ist_eigen(p.magic):
            b.fremde.append(p)
            self.lz.sperren(p.symbol, "FREMDPOSITION")
            return
        b.eigene.append(p)
        op = self.lz.op_mit_magic(p.magic)
        if op is None:
            b.unerwartet.append(p)
            self.lz.sperren(p.symbol, "EIGENE_POSITION_OHNE_OPERATION")
        if p.sl > ZERO:
            self.ohne_sl_seit.pop(p.ticket, None)
            return
        if modus is KontoModus.NETTING and self.lz.symbol_sperren.get(p.symbol) in FREMD_SPERREN:
            b.meldungen.append(f"{p.symbol}: Netting-Position mit Fremdvolumen ohne SL – keine automatische Aktion, Betreiber prüfen")
            return
        erst = self.ohne_sl_seit.setdefault(p.ticket, jetzt)
        geplant = op.absicht.sl if op is not None else ZERO
        ns = ids.namensraum(p.magic)
        if geplant > ZERO and jetzt - erst < self.schutz_frist_s:
            a = Absicht(f"SCHUTZ-{p.ticket}", Action.PROTECT_SLTP, p.symbol, p.side, p.volume, ns, geplant,
                        op.absicht.tp if op is not None else ZERO, p.ticket, "SL fehlt auf dem Server")
            b.aktionen.append((self._cid("SCHUTZ", p.ticket), a))
        else:
            a = Absicht(f"NOTSCHLUSS-{p.ticket}", Action.REDUCE_DEAL, p.symbol, p.side.opposite, p.volume, ns, ZERO, ZERO, p.ticket,
                        "Position ohne SL nach Frist – schließen")
            b.aktionen.append((self._cid("NOTSCHLUSS", p.ticket), a))
        b.meldungen.append(f"Eigene Position {p.symbol} ohne Server-SL – Schutzaktion")

    def _differenzen(self, b: Bericht, positionen: list[Position]) -> None:
        offen = {p.ticket for p in positionen}
        for op in self.lz.ops.values():
            a = op.absicht
            if op.op_id in self._geprueft or a.action is not Action.ENTRY_DEAL or op.status is not OpStatus.ERLEDIGT                     or op.gefuellt <= ZERO:
                continue
            ids_pos = {self.deal_position[d] for d in op.deals if d in self.deal_position}
            if not ids_pos:
                continue                                    # Deal noch nicht in der Historie gesehen
            if ids_pos <= self.geschlossene_positionen:
                self._geprueft.add(op.op_id)                # geschlossen bleibt geschlossen
                continue
            if not (ids_pos & offen) and not (ids_pos & self.geschlossene_positionen):
                b.differenzen.append(f"POSITION_FEHLT {op.op_id} {a.symbol}")
