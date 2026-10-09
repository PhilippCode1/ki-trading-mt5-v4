"""Lebenszyklus einer Orderoperation für genau einen Betreiber (Teilmenge der v4-Engine-Semantik, Regeln R1–R4, R6, R7 aus
oracles/t15_unknown.py; Fencing/Epoche R5 ist durch die Schreibsperre ersetzt).

R1 Timeout/Verbindung/unbekannter Code → UNBEKANNT; Reservierung bleibt; keine Risikozunahme im Symbol.
R2 Freigabe nur bei bestätigter Nichtausführung oder Negativnachweis nach 60 s; vorzeitiger Nachweis wird abgelehnt.
R3 Späte Fills werden immer verbucht (Broker autoritativ); nach Negativnachweis → Vorfall NEGPROOF_FALSIFIED + Symbolsperre.
R4 Doppelte Beobachtungen (gleiches Deal-Ticket) zählen genau einmal.
R6 Absturz nach Journal, vor Sendung → nach Neustart UNBEKANNT.
R7 Nie blind neu senden: eine Absicht bekommt erst eine neue Operation, wenn keine ihrer Operationen mehr offen ist; eine
   neue Operation sendet nur den noch nicht gefüllten Rest der Absicht; eine Operation wird genau einmal angestoßen.
Demo-Vorrang (Standard, fail-closed): ist das Konto nicht DEMO oder nicht lesbar, wird nichts gesendet – auch kein Schutz.
Pending-Orders sind im Fast-Track nicht freigegeben (lokal abgelehnt).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

from kit.broker.seam import Terminal
from kit.domain.types import (
    OFFEN,
    RISIKO_ERHOEHEND,
    ZERO,
    Absicht,
    Action,
    HandelsModus,
    Namensraum,
    Operation,
    OpStatus,
    OrderRequest,
    SendResult,
    Side,
)
from kit.orders import ids
from kit.orders.retcodes import einordnen
from kit.state.journal import Journal

NEGATIVNACHWEIS_S = 60.0
BESTAETIGUNG_RAND_S = 120.0                  # Uhrabweichung PC ↔ Server: Deal-Suche je magic großzügig (magic ist eindeutig)
RETCODE_SPERRE_S = 3600.0                    # Sperren aus Retcodes (z. B. Markt zu) laufen ab; Sperren aus Beobachtungen nicht
NEUVERSUCH_FENSTER_S = 30.0
MAX_VERSUCHE = 3
KONTO = "*"                                  # Schlüssel der kontoweiten Sperre


class Lebenszyklus:
    def __init__(self, terminal: Terminal, journal: Journal, *, demo_pruefung: Callable[[], str | None] | None = None,
                 max_versuche: int = MAX_VERSUCHE, neuversuch_fenster_s: float = NEUVERSUCH_FENSTER_S,
                 negativnachweis_s: float = NEGATIVNACHWEIS_S) -> None:
        self.t = terminal
        self.j = journal
        self.demo_pruefung = demo_pruefung       # zusätzliche Prüfung (z. B. Terminalpfad, Allowlist); die DEMO-Prüfung gilt immer
        self.max_versuche = max_versuche
        self.neuversuch_fenster_s = neuversuch_fenster_s
        self.negativnachweis_s = negativnachweis_s
        self.ops: dict[str, Operation] = {}
        self.vorfaelle: list[dict] = []
        self.symbol_sperren: dict[str, str] = {}          # dauerhaft, Aufheben nur Betreiber (kit entsperren --grund SYMBOL:x)
        self.zeit_sperren: dict[str, tuple[str, float]] = {}   # Symbol → (Grund, bis)
        self._gruende: dict[str, set[str]] = {}               # alle dauerhaften Gründe je Symbol seit der letzten Aufhebung
        self.ablehnungen: dict[str, str] = {}

    # ------------------------------------------------------------------------------------------------ Zustand
    def uhr(self) -> float:
        return self.t.zeit()

    def demo_grund(self) -> str | None:
        """None = senden erlaubt. Fail-closed: Konto nicht DEMO oder nicht lesbar → Grund."""
        try:
            konto = self.t.account()
        except Exception as exc:  # noqa: BLE001
            return f"Konto nicht lesbar ({type(exc).__name__})"
        if konto.trade_mode is not HandelsModus.DEMO:
            return f"Konto ist {konto.trade_mode}, nicht DEMO"
        if self.demo_pruefung is not None:
            try:
                return self.demo_pruefung()
            except Exception as exc:  # noqa: BLE001
                return f"Demo-Prüfung fehlgeschlagen ({type(exc).__name__})"
        return None

    def reserviert(self, symbol: str) -> Decimal:
        return sum((o.reserviert for o in self.ops.values() if o.absicht.symbol == symbol), ZERO)

    def offene(self) -> list[Operation]:
        return [o for o in self.ops.values() if o.status in OFFEN]

    def op_mit_magic(self, magic: int) -> Operation | None:
        for o in self.ops.values():
            if o.magic == magic and o.status is not OpStatus.LOKAL_ABGELEHNT:
                return o
        return None

    def gesperrt(self, symbol: str) -> str | None:
        for schluessel in (KONTO, symbol):
            if schluessel in self.symbol_sperren:
                return self.symbol_sperren[schluessel]
            grund, bis = self.zeit_sperren.get(schluessel, ("", 0.0))
            if grund and self.uhr() < bis:
                return grund
        if any(o.absicht.symbol == symbol and o.status in OFFEN for o in self.ops.values()):
            return "OFFENE_OPERATION"
        return None

    def sperren(self, symbol: str, grund: str, *, dauer_s: float | None = None) -> None:
        wo = "allen Symbolen" if symbol == KONTO else symbol
        if dauer_s:
            bis = self.uhr() + dauer_s
            self.zeit_sperren[symbol] = (grund, bis)
            self.j.schreiben("SPERRE", grund, f"Einstiege in {wo} bis auf Weiteres ({dauer_s / 60:.0f} min) gesperrt: {grund}",
                             symbol=symbol, grund=grund, bis=bis)
            return
        gruende = self._gruende.setdefault(symbol, set())
        if grund not in gruende:                         # jeder Grund wird einmal journalisiert; der erste bleibt maßgeblich
            gruende.add(grund)
            self.symbol_sperren.setdefault(symbol, grund)
            self.j.schreiben("SPERRE", grund, f"Einstiege in {wo} gesperrt: {grund}", symbol=symbol, grund=grund)

    def vorfall(self, art: str, text: str, **daten: object) -> None:
        self.vorfaelle.append({"art": art, "text": text, **daten})
        self.j.schreiben("VORFALL", art, text, **daten)

    # ------------------------------------------------------------------------------------------------ Journal
    def _daten(self, op: Operation) -> dict:
        a = op.absicht
        return {"op_id": op.op_id, "absicht_id": a.absicht_id, "action": str(a.action), "symbol": a.symbol, "side": str(a.side),
                "volume": str(a.volume), "sl": str(a.sl), "tp": str(a.tp), "ticket": a.ticket, "namensraum": str(a.namensraum),
                "grund_absicht": a.grund, "magic": op.magic, "status": str(op.status), "versuche": op.versuche,
                "retcodes": list(op.retcodes), "t_geplant": op.t_geplant, "t_gesendet": op.t_gesendet, "gefuellt": str(op.gefuellt),
                "deals": list(op.deals), "order": op.order, "grund": op.grund, "negativnachweis": op.negativnachweis}

    def _j(self, art: str, op: Operation, text: str) -> None:
        self.j.schreiben(art, str(op.status), text, **self._daten(op))

    # ------------------------------------------------------------------------------------------------ Ausführen
    def _rest(self, a: Absicht) -> Decimal:
        gefuellt = sum((o.gefuellt for o in self.ops.values()
                        if o.absicht.absicht_id == a.absicht_id and o.status is not OpStatus.LOKAL_ABGELEHNT), ZERO)
        return a.volume - gefuellt

    def _vorpruefung(self, a: Absicht, cid: str) -> tuple[str, str] | None:
        demo = self.demo_grund()
        if demo:
            return "NICHT_DEMO", demo
        if cid in self.ops and self.ops[cid].status is not OpStatus.LOKAL_ABGELEHNT:
            return "OP_EXISTIERT", "Diese Kennung wurde schon gesendet – nie dieselbe Operation erneut senden."
        if any(o.absicht.absicht_id == a.absicht_id and o.status in OFFEN for o in self.ops.values()):
            return "INTENT_HAS_OPEN_ATTEMPT", "Für diese Absicht arbeitet noch eine Operation (kein blindes Neusenden)."
        if a.action is Action.PLACE_PENDING:
            return "PENDING_NICHT_FREIGEGEBEN", "Pending-Orders sind im Fast-Track nicht freigegeben."
        if a.action in RISIKO_ERHOEHEND:
            sperre = self.gesperrt(a.symbol)
            if sperre:
                return "STATE_BLOCK", f"Keine Risikozunahme in {a.symbol}: {sperre}"
            if a.sl <= ZERO:
                return "SL_FEHLT", "Einstieg ohne Stop-Loss ist verboten."
            if self._rest(a) <= ZERO:
                return "ABSICHT_ERFUELLT", "Die Absicht ist bereits vollständig gefüllt."
        if a.action in (Action.REDUCE_DEAL, Action.PROTECT_SLTP, Action.CANCEL_PENDING) and not a.ticket:
            return "TICKET_FEHLT", "Abbau/Schutz nur per Ticket."
        if a.action is Action.REDUCE_DEAL and any(o.absicht.action is Action.REDUCE_DEAL and o.absicht.ticket == a.ticket
                                                  and o.status in OFFEN for o in self.ops.values()):
            return "TICKET_OFFENER_ABBAU", "Für dieses Ticket läuft schon ein Abbau (nie doppelt schließen)."
        if a.action in (Action.ENTRY_DEAL, Action.REDUCE_DEAL) and a.volume <= ZERO:
            return "VOLUMEN_UNGUELTIG", "Volumen muss positiv sein."
        return None

    def lokal_ablehnen(self, a: Absicht, cid: str, code: str, text: str) -> Operation:
        op = Operation(cid, a, ids.magic(a.namensraum, cid), status=OpStatus.LOKAL_ABGELEHNT, t_geplant=self.uhr(), grund=code)
        self.ablehnungen[cid] = code
        if cid in self.ops and self.ops[cid].status is not OpStatus.LOKAL_ABGELEHNT:
            # Die echte Operation bleibt maßgeblich – die Ablehnung darf sie im Journal nie überdecken.
            self.j.schreiben("OP_LOKAL_ABGELEHNT", code, text, abgelehnte_op_id=cid, absicht_id=a.absicht_id, symbol=a.symbol,
                             action=str(a.action), grund=code)
            return op
        self.ops[cid] = op
        self._j("OP_LOKAL_ABGELEHNT", op, text)
        return op

    def planen(self, a: Absicht, cid: str) -> Operation:
        """Vorprüfung und Journal (fsync) – noch keine Sendung. Liefert die Operation (ggf. LOKAL_ABGELEHNT)."""
        nein = self._vorpruefung(a, cid)
        if nein:
            return self.lokal_ablehnen(a, cid, *nein)
        if a.action is Action.ENTRY_DEAL:
            a = replace(a, volume=self._rest(a))
        op = Operation(cid, a, ids.magic(a.namensraum, cid), t_geplant=self.uhr())
        self.ops[cid] = op
        self._j("OP_GEPLANT", op, f"{a.action} {a.side} {a.volume} {a.symbol} geplant")
        return op

    def ausfuehren(self, a: Absicht, cid: str) -> Operation:
        op = self.planen(a, cid)
        if op.status is OpStatus.LOKAL_ABGELEHNT:
            return op
        return self.senden(op)

    def _anfrage(self, op: Operation) -> OrderRequest:
        a = op.absicht
        volumen = a.volume - op.gefuellt if a.action in (Action.ENTRY_DEAL, Action.REDUCE_DEAL) else a.volume
        return OrderRequest(action=a.action, symbol=a.symbol, side=a.side, volume=volumen, magic=op.magic,
                            comment=ids.kommentar(op.op_id), sl=a.sl, tp=a.tp, ticket=a.ticket)

    def senden(self, op: Operation) -> Operation:
        """Stößt eine geplante Operation genau einmal an (Neuversuche nur in dieser Schleife)."""
        if op.status is not OpStatus.GEPLANT or op.versuche != 0:
            return op
        while True:
            try:
                demo = self.demo_grund()
                if demo:   # Vorrang auch zwischen Neuversuchen
                    op.status, op.grund = OpStatus.ABGELEHNT, "NICHT_DEMO"
                    self._j("OP_ERGEBNIS", op, f"Nicht gesendet: {demo}")
                    return op
                req = self._anfrage(op)
                pruefung = self.t.check(req)
                if pruefung.retcode != 0:
                    op.status, op.grund = OpStatus.ABGELEHNT, f"CHECK_{pruefung.retcode}"
                    self._j("OP_ERGEBNIS", op, f"order_check abgelehnt: {pruefung.retcode} {pruefung.comment}")
                    return op
                op.versuche += 1
                op.t_gesendet = self.uhr()
                op.status = OpStatus.GESENDET
                self._j("OP_GESENDET", op, f"Versuch {op.versuche} gesendet")
            except Exception as exc:  # noqa: BLE001 - vor der Sendung: nachweislich nichts gesendet
                if op.status is OpStatus.GESENDET:
                    raise                                 # Journal nach Statuswechsel gescheitert: nicht senden, laut scheitern
                op.status, op.grund = OpStatus.ABGELEHNT, f"VOR_SENDUNG:{type(exc).__name__}"
                self._j("OP_ERGEBNIS", op, f"Fehler vor der Sendung – nicht gesendet: {str(exc)[:160]}")
                return op
            try:
                res = self.t.send(req)
            except Exception:  # noqa: BLE001 - Ausgang unbekannt
                res = None
            self._nach_sendung_pruefen(op)
            nochmal = self._einordnen(op, res)
            self._j("OP_ERGEBNIS", op, f"Ergebnis {op.retcodes[-1] if op.retcodes else '-'} → {op.status}")
            if not nochmal:
                return op

    def _nach_sendung_pruefen(self, op: Operation) -> None:
        """Gegenprobe nach der Sendung: Wurde das Konto zwischen Prüfung und Sendung gewechselt, ist das ein Vorfall."""
        try:
            modus = self.t.account().trade_mode
        except Exception:  # noqa: BLE001 - nicht lesbar: nächste Demo-Prüfung sperrt ohnehin
            return
        if modus is not HandelsModus.DEMO:
            self.vorfall("NICHT_DEMO_SENDUNG", f"Konto war nach der Sendung {modus}", op_id=op.op_id, symbol=op.absicht.symbol)

    def _einordnen(self, op: Operation, res: SendResult | None) -> bool:
        a = op.absicht
        if res is None:
            op.retcodes.append(-1)
            op.status = OpStatus.UNBEKANNT
            return False
        op.retcodes.append(res.retcode)
        e = einordnen(res.retcode, a.action, ticket=res.order or res.deal, volumen=res.volume)
        if res.order:
            op.order = res.order
        if res.deal and res.deal not in op.deals:
            op.deals.append(res.deal)
        handel = a.action in (Action.ENTRY_DEAL, Action.REDUCE_DEAL)
        if e.klasse == "DONE":
            if handel and (res.volume <= ZERO or not (res.order or res.deal)):
                op.status = OpStatus.UNBEKANNT        # Erfolg ohne Menge oder ohne Ticket: über Abgleich klären
                return False
            op.gefuellt = op.gefuellt + res.volume if handel else a.volume
            op.status = OpStatus.ERLEDIGT if (not handel or op.gefuellt >= a.volume) else OpStatus.TEILWEISE
        elif e.klasse == "PARTIAL":
            op.gefuellt += res.volume
            op.status = OpStatus.TEILWEISE
        elif e.klasse in ("NOOP_OK", "PLACED"):
            op.status = OpStatus.ERLEDIGT
        elif e.klasse == "NOT_EXECUTED":
            nochmal = (e.retry.startswith("NEUER_VERSUCH") and op.versuche < self.max_versuche
                       and self.uhr() - op.t_geplant <= self.neuversuch_fenster_s)
            op.status = OpStatus.GEPLANT if nochmal else OpStatus.ABGELEHNT
            op.grund = f"RETCODE_{res.retcode}"
            return nochmal
        elif e.klasse == "REJECT_FINAL":
            op.status, op.grund = OpStatus.ABGELEHNT, f"RETCODE_{res.retcode}"
            if e.sperre == "SYMBOL" and a.action in RISIKO_ERHOEHEND:
                self.sperren(a.symbol, f"RETCODE_{res.retcode}", dauer_s=RETCODE_SPERRE_S)
            elif e.sperre == "ACCOUNT":
                self.sperren(KONTO, f"RETCODE_{res.retcode}", dauer_s=RETCODE_SPERRE_S)
        else:                                           # UNKNOWN, RECONCILE
            op.status = OpStatus.UNBEKANNT
        return False

    # ------------------------------------------------------------------------------------------------ Klären
    def zeitueberschreitung(self, cid: str) -> None:
        op = self.ops[cid]
        if op.status in (OpStatus.GEPLANT, OpStatus.GESENDET):
            op.status = OpStatus.UNBEKANNT
            self._j("OP_GEKLAERT", op, "Zeitüberschreitung → UNBEKANNT")

    def _bestaetigt(self, op: Operation) -> Decimal:
        """Vom Broker beobachtete Menge dieser Operation (Deals mit ihrem magic, jedes Deal-Ticket einmal)."""
        seit = int(op.t_geplant - BESTAETIGUNG_RAND_S)
        gesehen: set[int] = set()
        menge = ZERO
        einstieg = op.absicht.action is Action.ENTRY_DEAL
        for d in self.t.deals(seit, int(self.uhr() + BESTAETIGUNG_RAND_S)):
            if d.magic != op.magic or d.ticket in gesehen or d.reason in ("SL", "TP", "SO"):    # magic je Operation eindeutig
                continue
            if einstieg and d.entry not in ("IN", "INOUT"):
                continue
            if not einstieg and d.entry not in ("OUT", "OUT_BY", "INOUT"):
                continue
            gesehen.add(d.ticket)
            menge += d.volume
            if d.ticket not in op.deals:
                op.deals.append(d.ticket)
        return menge

    def klaeren(self) -> list[Operation]:
        """Offene Ausgänge über Positionen/Deals klären; nach Ablauf des Prüffensters Negativnachweis; späte Fills nach
        Negativnachweis (auch nach TEILWEISE → ERLEDIGT) werden verbucht und gemeldet (R3)."""
        geaendert: list[Operation] = []
        for op in list(self.ops.values()):
            offen = op.status in (OpStatus.UNBEKANNT, OpStatus.TEILWEISE, OpStatus.GESENDET)
            nach_nachweis = op.negativnachweis and op.status in (OpStatus.ABGELEHNT, OpStatus.ERLEDIGT)
            if not (offen or nach_nachweis):
                continue
            vorher = (op.status, op.gefuellt)
            a = op.absicht
            if a.action in (Action.ENTRY_DEAL, Action.REDUCE_DEAL):
                menge = self._bestaetigt(op)
                if nach_nachweis:
                    if menge > op.gefuellt:
                        op.gefuellt, op.status = menge, OpStatus.ERLEDIGT
                        self.vorfall("NEGPROOF_FALSIFIED", f"Später Fill nach Negativnachweis ({op.op_id})", op_id=op.op_id,
                                     symbol=a.symbol)
                        self.sperren(a.symbol, "NEGPROOF_FALSIFIED")
                elif menge > op.gefuellt:
                    op.gefuellt = menge
                    op.status = OpStatus.ERLEDIGT if menge >= a.volume else OpStatus.TEILWEISE
                elif a.action is Action.REDUCE_DEAL and op.status is OpStatus.UNBEKANNT and \
                        not any(p.ticket == a.ticket for p in self.t.positions()):
                    op.status = OpStatus.ERLEDIGT                     # Zielzustand erreicht: Position existiert nicht mehr
            elif a.action is Action.PROTECT_SLTP and op.status is OpStatus.UNBEKANNT:
                pos = next((p for p in self.t.positions() if p.ticket == a.ticket), None)
                if pos is not None and pos.sl == a.sl and pos.tp == a.tp:
                    op.status = OpStatus.ERLEDIGT
            if op.status in (OpStatus.UNBEKANNT, OpStatus.TEILWEISE, OpStatus.GESENDET) and \
                    self.uhr() - (op.t_gesendet or op.t_geplant) >= self.negativnachweis_s:
                self._negativ(op)
            if (op.status, op.gefuellt) != vorher:
                self._j("OP_GEKLAERT", op, f"geklärt → {op.status}")
                geaendert.append(op)
        return geaendert

    def _negativ(self, op: Operation) -> None:
        op.negativnachweis = True
        if op.status is OpStatus.TEILWEISE:
            op.status = OpStatus.ERLEDIGT          # Rest verworfen, Reservierung frei
        else:
            op.status = OpStatus.ABGELEHNT
            op.grund = op.grund or "NEGATIVNACHWEIS"

    def negativnachweis(self, cid: str) -> str | None:
        """Ausdrücklicher Negativnachweis (v4-Schritt negproof): vor Ablauf des Fensters abgelehnt (NEGPROOF_INSUFFICIENT)."""
        op = self.ops[cid]
        if op.status not in (OpStatus.UNBEKANNT, OpStatus.TEILWEISE, OpStatus.GESENDET, OpStatus.GEPLANT):
            return None
        if self.uhr() - (op.t_gesendet or op.t_geplant) < self.negativnachweis_s:
            self.ablehnungen[cid] = "NEGPROOF_INSUFFICIENT"
            return "NEGPROOF_INSUFFICIENT"
        self.klaeren()
        if op.status in (OpStatus.UNBEKANNT, OpStatus.TEILWEISE, OpStatus.GESENDET, OpStatus.GEPLANT):
            self._negativ(op)
            self._j("OP_GEKLAERT", op, "Negativnachweis")
        return None

    # ------------------------------------------------------------------------------------------------ Wiederherstellen
    def wiederherstellen(self) -> list[Operation]:
        """Zustand aus dem Journal; ohne Ergebnis gebliebene Operationen werden UNBEKANNT (R6). Lokale Ablehnungen überdecken
        nie eine echte Operation."""
        self.ops.clear()
        self.vorfaelle.clear()                         # alles wird aus dem Journal neu aufgebaut
        self.symbol_sperren.clear()
        self.zeit_sperren.clear()
        self._gruende.clear()
        for satz in self.j.lesen():
            d = satz.get("daten", {})
            if satz["art"] == "SPERRE":
                if d.get("bis"):
                    self.zeit_sperren[d["symbol"]] = (d["grund"], float(d["bis"]))
                else:
                    self.symbol_sperren.setdefault(d["symbol"], d["grund"])
                    self._gruende.setdefault(d["symbol"], set()).add(d["grund"])
                continue
            if satz["art"] == "BOT_ENTSPERRT":           # Betreiber (PIN): Symbolsperre aufgehoben (Altformat ALLE: alles)
                ziele = list(self.symbol_sperren) + list(self.zeit_sperren) if satz["code"] == "ALLE" else \
                    [satz["code"][7:]] if satz["code"].startswith("SYMBOL:") else []
                for sym in ziele:
                    self.symbol_sperren.pop(sym, None)
                    self.zeit_sperren.pop(sym, None)
                    self._gruende.pop(sym, None)
                continue
            if satz["art"] == "VORFALL":
                self.vorfaelle.append({"art": satz["code"], "text": satz["text"], **d})
                continue
            if not satz["art"].startswith("OP_") or "op_id" not in d:
                continue                                   # nur Operationssätze (andere Sätze dürfen op_id nicht tragen)
            vorhanden = self.ops.get(d["op_id"])
            if satz["art"] == "OP_LOKAL_ABGELEHNT" and vorhanden is not None and vorhanden.status is not OpStatus.LOKAL_ABGELEHNT:
                continue
            a = Absicht(d["absicht_id"], Action(d["action"]), d["symbol"], Side(d["side"]), Decimal(d["volume"]),
                        Namensraum(d["namensraum"]), Decimal(d["sl"]), Decimal(d["tp"]), d["ticket"], d.get("grund_absicht", ""))
            self.ops[d["op_id"]] = Operation(d["op_id"], a, d["magic"], OpStatus(d["status"]), d["versuche"], list(d["retcodes"]),
                                             d["t_geplant"], d["t_gesendet"], Decimal(d["gefuellt"]), list(d["deals"]), d["order"],
                                             d["grund"], d["negativnachweis"])
        offen = []
        for op in self.ops.values():
            if op.status in (OpStatus.GEPLANT, OpStatus.GESENDET):
                op.status = OpStatus.UNBEKANNT
                self._j("OP_GEKLAERT", op, "Neustart: Sendung nicht ausschließbar → UNBEKANNT")
                offen.append(op)
        return offen
