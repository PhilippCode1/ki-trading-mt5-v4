"""Differenztest gegen das v4-Orakel T-15 (UNKNOWN-Regeln): dieselben Szenarien, dieselben handabgeleiteten Erwartungen.

Die Schrittsprache des Orakels wird auf den kit-Lebenszyklus abgebildet. Nicht abgebildet (bewusste Abweichung, siehe
ABWEICHUNGEN.md): R5 Fencing/Epoche (Szenarien mit acquire+submit_as) – im kit ersetzt durch die Ein-Schreiber-Sperre.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from kit.broker.sim import Fehler
from kit.domain.types import Absicht, Action, Namensraum, OpStatus, Side
from kit.orders import ids
from kit.orders.lifecycle import Lebenszyklus
from kit.state.journal import Journal
from kit_tests.hilfen import aufbau
from kit_tests.orakel import t15_unknown as t15

SYM = "SYM-CFD-EURUSD"
FENCING = {"T15-04-OLD-WRITER", "T15-05-SPLIT-BRAIN", "T15-14-SAME-WRITER-NEW-EPOCH"}
STATUS = {"UNKNOWN": OpStatus.UNBEKANNT, "NOT_EXECUTED": OpStatus.ABGELEHNT, "DONE": OpStatus.ERLEDIGT, "PARTIAL": OpStatus.TEILWEISE}


def _magic(cid: str) -> int:
    return ids.magic(Namensraum.STRATEGIE, cid)


def _absicht(spec: dict, term) -> Absicht:
    ticket = spec.get("ticket")
    if ticket == "$T":
        ticket = term.positions()[0].ticket
    return Absicht(spec["intent"], Action(spec["action"]), SYM, Side(spec.get("side", "BUY")), Decimal(spec["volume"]),
                   Namensraum.STRATEGIE, Decimal(spec["sl"]), Decimal(0), ticket)


def _netto(term) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for p in term.positions():
        out[p.symbol] = out.get(p.symbol, Decimal(0)) + p.volume * p.side.sign
    return {k: v for k, v in out.items() if v}


def _pruefe(erwartet: dict, term, lz: Lebenszyklus, abgelehnt: dict[str, str]) -> None:
    for cid, st in erwartet.get("status", {}).items():
        assert lz.ops[cid].status is STATUS[st], (cid, lz.ops[cid].status, st)
    if "reserved" in erwartet:
        assert lz.reserviert(SYM) == Decimal(erwartet["reserved"])
    if "position" in erwartet:
        assert _netto(term) == {k: Decimal(v) for k, v in erwartet["position"].items()}
    if "account_flat" in erwartet:
        flach = not term.positions() and lz.reserviert(SYM) == 0
        assert flach is erwartet["account_flat"]
    for cid, code in erwartet.get("refused", {}).items():
        assert abgelehnt.get(cid) == code, (cid, abgelehnt.get(cid), code)
    for cid in erwartet.get("not_sent", []) + erwartet.get("sim_never_saw", []):
        assert term.gesendet(_magic(cid)) == 0, cid
    for cid in erwartet.get("sent_once", []):
        assert term.gesendet(_magic(cid)) == 1, cid
    if "cash" in erwartet:
        einmal = {d.ticket: d for d in term.deals(0, 2**62)}
        assert sum((d.geld for d in einmal.values()), Decimal(0)) == Decimal(erwartet["cash"])
    arten = [v["art"] for v in lz.vorfaelle]
    for art in erwartet.get("incidents", []):
        assert art in arten
    for art in erwartet.get("no_incidents", []):
        assert art not in arten
    if erwartet.get("integrity_block"):
        assert lz.symbol_sperren.get(SYM)


def test_alle_szenarien_zugeordnet():
    alle = {s["id"] for s in t15.SCENARIOS}
    assert FENCING <= alle
    assert len(alle - FENCING) >= 11


@pytest.mark.parametrize("szenario", [s for s in t15.SCENARIOS if s["id"] not in FENCING], ids=lambda s: s["id"])
def test_szenario_wie_orakel(szenario, tmp_path):
    term, lz, uhr, journal = aufbau(tmp_path, provision="3.50", symbol=SYM)
    abgelehnt: dict[str, str] = {}
    for schritt in szenario["steps"]:
        art = schritt[0]
        if art == "fault":
            code = schritt[3] if len(schritt) > 3 else None
            anteil = Decimal(schritt[4]) if len(schritt) > 4 and schritt[4] else None
            term.setze_fehler(_magic(schritt[1]), Fehler(schritt[2], code, anteil))
        elif art == "submit":
            op = lz.ausfuehren(_absicht(schritt[2], term), schritt[1])
            if op.status is OpStatus.LOKAL_ABGELEHNT:
                abgelehnt[schritt[1]] = op.grund
        elif art == "crash_before_send":
            lz.planen(_absicht(schritt[2], term), schritt[1])
        elif art == "restart":
            journal = Journal(tmp_path / "journal", uhr=uhr)
            lz = Lebenszyklus(term, journal)
            lz.wiederherstellen()
        elif art == "timeout":
            lz.zeitueberschreitung(schritt[1])
        elif art == "late":
            term.liefere_spaete()
            lz.klaeren()
        elif art == "negproof":
            op = lz.ops[schritt[1]]
            uhr.t = (op.t_gesendet or op.t_geplant) + schritt[2]
            code = lz.negativnachweis(schritt[1])
            if code:
                abgelehnt[schritt[1]] = code
        elif art == "snapshot":
            lz.klaeren()
        elif art == "acquire":
            pass                                   # Ein-Schreiber-Sperre statt Epoche (ABWEICHUNGEN.md)
        elif art == "check":
            _pruefe(schritt[1], term, lz, abgelehnt)
        else:
            raise AssertionError(f"Schritt {art} nicht abgebildet")
