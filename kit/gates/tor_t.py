"""Tor T – Technik (Plan F-1 §5, D9): Auswertung allein aus dem Journal (Replay), gebunden an den mechanik_hash.

Fenster: alle Sätze ab dem ersten START unter dem aktuellen mechanik_hash (ein START mit anderem Hash beginnt neu).
Gezählt werden gesendete Orderoperationen (mindestens ein Sendeversuch) ohne Skripte; fehlerfrei = ERLEDIGT. Skripte (SK-…)
zählen getrennt über ihr deklariertes Soll-Ergebnis (FAIL = Defekt).
Null-Toleranz: Position > 30 s ohne SL (Notschluss), Doppel-Fill/Nachweis widerlegt/eigener Deal ohne Operation, Sendung auf
Nicht-Demo, UNBEKANNT > 15 min, Abgleichdifferenz, Kill außerhalb Zielzeit, Schutz-/Schließabsicht lokal abgewiesen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sys
from decimal import Decimal
from pathlib import Path

from kit.domain.types import OFFEN
from kit.gates import ROOT

ERLAUBT_LOKAL_SCHUTZ = frozenset({"OP_EXISTIERT", "INTENT_HAS_OPEN_ATTEMPT", "NICHT_DEMO", "TICKET_OFFENER_ABBAU"})
VORFALL_DEFEKT = frozenset({"NEGPROOF_FALSIFIED", "EIGENER_DEAL_OHNE_OPERATION", "NICHT_DEMO_SENDUNG", "DOPPEL_FILL"})
HANDEL = {"ENTRY_DEAL": "eroeffnen", "REDUCE_DEAL": "schliessen", "PROTECT_SLTP": "aendern"}
OFFENE_STATUS = frozenset(s.value for s in OFFEN)


def mechanik_dateien(muster: list[str], root: Path = ROOT) -> list[Path]:
    dateien: set[Path] = set()
    for m in muster:
        if m.endswith("/**"):
            basis = root / m[:-3]
            dateien |= {p for p in basis.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
        elif (root / m).is_file():
            dateien.add(root / m)
    return sorted(dateien, key=lambda p: p.relative_to(root).as_posix())


def mechanik_hash(root: Path = ROOT, muster: list[str] | None = None) -> str:
    if muster is None:
        from kit.gates import tore
        muster = list(tore()["tor_t"]["mechanik"])
    h = hashlib.sha256(f"python {sys.version_info.major}.{sys.version_info.minor}\n".encode())
    for p in mechanik_dateien(muster, root):
        h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def _utc(t: float) -> str:
    return dt.datetime.fromtimestamp(float(t), dt.UTC).isoformat(timespec="seconds")


def _fenster(saetze: list[dict], mechanik: str) -> list[dict] | None:
    beginn = None
    for i, s in enumerate(saetze):
        if s["art"] != "START":
            continue
        if s["daten"].get("mechanik_hash") != mechanik:
            beginn = None
        elif beginn is None:
            beginn = i
    return None if beginn is None else saetze[beginn:]


def auswerten(saetze: list[dict], t: dict, *, mechanik: str, jetzt: float) -> dict:
    """Urteil BESTANDEN / NICHT_BESTANDEN / LAEUFT / NICHT_BEWERTBAR mit allen Zählungen und Defekten (ohne Geldbeträge)."""
    fenster = _fenster(saetze, mechanik)
    if fenster is None:
        return {"urteil": "NICHT_BEWERTBAR", "grund": "kein Lauf unter diesem mechanik_hash", "mechanik_hash": mechanik}
    ops: dict[str, dict] = {}
    im_fenster: set[str] = set()                      # nur Operationen, die in diesem Fenster geplant wurden
    unbekannt_seit: dict[str, float] = {}
    unbekannt_max: dict[str, float] = {}
    defekte: list[dict] = []
    lokal = 0
    skripte: dict[str, str] = {}
    skript_fail: set[str] = set()
    kills: list[dict] = []
    for s in fenster:
        art, d = s["art"], s.get("daten", {})
        if art.startswith("OP_") and "op_id" in d:
            oid = d["op_id"]
            if art == "OP_LOKAL_ABGELEHNT":
                lokal += 1
                if d["action"] in ("REDUCE_DEAL", "PROTECT_SLTP") and d.get("grund") not in ERLAUBT_LOKAL_SCHUTZ:
                    defekte.append({"art": "SCHUTZ_LOKAL_ABGEWIESEN", "seq": s["seq"], "text": f"{d['action']} {d.get('grund')}"})
                if oid in ops and ops[oid]["status"] != "LOKAL_ABGELEHNT":
                    continue
            if art in ("OP_GEPLANT", "OP_LOKAL_ABGELEHNT"):
                im_fenster.add(oid)
            ops[oid] = d
            if d["status"] == "UNBEKANNT":
                unbekannt_seit.setdefault(oid, float(d.get("t_gesendet") or d.get("t_geplant") or s["t"]))
            elif oid in unbekannt_seit:
                unbekannt_max[oid] = max(unbekannt_max.get(oid, 0.0), s["t"] - unbekannt_seit.pop(oid))
        elif art == "OP_LOKAL_ABGELEHNT":
            lokal += 1
            if d.get("action") in ("REDUCE_DEAL", "PROTECT_SLTP") and d.get("grund") not in ERLAUBT_LOKAL_SCHUTZ:
                defekte.append({"art": "SCHUTZ_LOKAL_ABGEWIESEN", "seq": s["seq"], "text": f"{d.get('action')} {d.get('grund')}"})
        elif art == "VORFALL" and s["code"] in VORFALL_DEFEKT:
            defekte.append({"art": s["code"], "seq": s["seq"], "text": s["text"]})
        elif art == "ABGLEICH" and s["code"] == "DIFFERENZ":
            defekte.append({"art": "ABGLEICHDIFFERENZ", "seq": s["seq"], "text": "; ".join(d.get("differenzen", []))[:200]})
        elif art == "KILL":
            kills.append({"stufe": d["stufe"], "dauer_s": d["dauer_s"], "drill": d.get("drill", False), "seq": s["seq"]})
            if d.get("drill") and d["stufe"] in (1, 2) and d["dauer_s"] > t["kill_k1_k2_max_s"]:
                defekte.append({"art": "KILL_ZEIT", "seq": s["seq"], "text": f"K{d['stufe']} {d['dauer_s']} s"})
        elif art == "KILL_FLACH":
            kills.append({"stufe": 3, "dauer_s": d["dauer_s"], "drill": d.get("drill", False), "seq": s["seq"]})
            if d.get("drill") and (d["dauer_s"] > t["kill_k3_max_s"] or d.get("flach") is False):
                defekte.append({"art": "KILL_ZEIT", "seq": s["seq"], "text": f"K3 {d['dauer_s']} s"})
        elif art == "SKRIPT":
            skripte[d["skript"]] = "FAIL" if d["skript"] in skript_fail else s["code"]
            if s["code"] == "FAIL":
                skript_fail.add(d["skript"])
                skripte[d["skript"]] = "FAIL"
    for oid, seit in unbekannt_seit.items():
        unbekannt_max[oid] = max(unbekannt_max.get(oid, 0.0), jetzt - seit)
    for oid, dauer in unbekannt_max.items():
        if dauer > t["unbekannt_max_s"]:
            defekte.append({"art": "UNBEKANNT_ZU_LANG", "seq": 0, "text": f"{oid} {dauer:.0f} s"})
    ops = {k: v for k, v in ops.items() if k in im_fenster}
    notschluss = {o["ticket"]: o["symbol"] for o in ops.values() if o["absicht_id"].startswith("NOTSCHLUSS-")}   # je Ticket einmal,
    for symbol in notschluss.values():                                                                          # egal ob gesendet
        defekte.append({"art": "POSITION_OHNE_SL", "seq": 0, "text": symbol})
    for o in ops.values():
        if o["action"] in ("ENTRY_DEAL", "REDUCE_DEAL") and Decimal(o["gefuellt"]) > Decimal(o["volume"]):
            defekte.append({"art": "DOPPEL_FILL", "seq": 0, "text": o["op_id"]})
    for name in sorted(skript_fail):
        defekte.append({"art": "SKRIPT_FAIL", "seq": 0, "text": name})
    gesendet = [o for o in ops.values() if o["versuche"] >= 1 and not o["absicht_id"].startswith("SK-")
                and o["status"] != "LOKAL_ABGELEHNT"]
    je_art = {v: 0 for v in HANDEL.values()}
    for o in gesendet:
        if o["action"] in HANDEL:
            je_art[HANDEL[o["action"]]] += 1
    fehlerfrei = sum(1 for o in gesendet if o["status"] == "ERLEDIGT")
    quote = Decimal(fehlerfrei) / len(gesendet) if gesendet else Decimal(0)
    genug = (len(gesendet) >= t["min_operationen"] and je_art["eroeffnen"] >= t["min_eroeffnen"]
             and je_art["schliessen"] >= t["min_schliessen"] and je_art["aendern"] >= t["min_aendern"])
    if defekte:
        urteil = "NICHT_BESTANDEN"
    elif not genug:
        urteil = "LAEUFT"
    else:
        urteil = "BESTANDEN" if quote >= Decimal(t["quote_min"]) else "NICHT_BESTANDEN"
    planbar = len([o for o in ops.values() if not o["absicht_id"].startswith("SK-") and o["status"] != "LOKAL_ABGELEHNT"]) + lokal
    return {"urteil": urteil, "mechanik_hash": mechanik, "fenster_ab_seq": fenster[0]["seq"], "fenster_bis_seq": fenster[-1]["seq"],
            "fenster_von_utc": _utc(fenster[0]["t"]), "fenster_bis_utc": _utc(fenster[-1]["t"]), "gesendet": len(gesendet), **je_art,
            "fehlerfrei": fehlerfrei, "quote": f"{quote:.4f}", "quote_min": t["quote_min"], "quote_ziel": t["quote_ziel"],
            "absicht_zu_operation": f"{Decimal(len(gesendet)) / planbar:.4f}" if planbar else "0", "lokal_abgelehnt": lokal,
            "offen": sum(1 for o in ops.values() if o["status"] in OFFENE_STATUS),
            "skripte": skripte, "kills": kills, "defekte": defekte,
            "mindestens": {k: t[k] for k in ("min_operationen", "min_eroeffnen", "min_schliessen", "min_aendern")}}
