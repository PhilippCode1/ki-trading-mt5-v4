"""Tor-T-Zertifikat (Plan F-1 §5, D9): nur bei BESTANDEN, gebunden an mechanik_hash, Commit, config/tore.toml und den redigierten Export.

Das Urteil wird allein aus dem redigierten Export und den Schwellen aus tore.toml nachgerechnet (gleiche Regel wie tor_t.auswerten);
weicht es ab, gibt es kein Zertifikat. Strenger als das Tor: Am Fensterende darf keine Operation mehr offen sein. Der Export wird
byte-gleich neben das Zertifikat gelegt, damit jeder den SHA-256 prüfen kann. Belege aus Simulation, Trockenlauf und T-PROBE zählen nur,
wenn sie denselben mechanik_hash nennen. Nichts wird überschrieben (exklusives Anlegen, bei Fehler wieder entfernt).
"""
from __future__ import annotations

import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

from kit.gates import ROOT, TORE_PFAD, tore
from kit.gates.tor_t import mechanik_hash

BELEGE = ("2026-10-05_f03c_nachweise.md", "2026-10-05_f03c_trockenlauf.json", "2026-10-05_tprobe.md")
ZAEHLUNG = ("gesendet", "eroeffnen", "schliessen", "aendern", "fehlerfrei")
MINDESTENS = ("min_operationen", "min_eroeffnen", "min_schliessen", "min_aendern")
NULL_TOLERANZ = ("Position > 30 s ohne SL", "Doppel-Fill", "Negativnachweis widerlegt", "eigener Deal ohne Operation",
                 "Sendung auf Nicht-Demo", "UNBEKANNT > 15 min", "Abgleichdifferenz", "Kill außerhalb der Zielzeit (Drill)",
                 "Schutz-/Schließabsicht lokal abgewiesen", "Skript FAIL")
EINORDNUNG = ("Einordnung: Tor T belegt die Technik (Orderweg, Schutz, Abgleich, Kill-Stufen) auf dem Demokonto, nicht einen Gewinn. "
              "Es gibt keinen belegten Handelsvorteil. Keine Anlageberatung, keine Gewinnzusage.")


class ZertifikatFehler(RuntimeError):
    """Kein Zertifikat (fail-closed)."""


def sha256(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def urteil_nachrechnen(stand: dict, t: dict) -> str:
    """Urteil allein aus dem redigierten Export und den eingefrorenen Schwellen (Regel wie tor_t.auswerten)."""
    if stand.get("defekte") or "FAIL" in stand.get("skripte", {}).values():
        return "NICHT_BESTANDEN"
    z = {k: int(stand[k]) for k in ZAEHLUNG}
    if z["eroeffnen"] + z["schliessen"] + z["aendern"] > z["gesendet"] or z["fehlerfrei"] > z["gesendet"]:
        raise ZertifikatFehler("Zählungen im Export sind widersprüchlich.")
    quote = Decimal(z["fehlerfrei"]) / z["gesendet"] if z["gesendet"] else Decimal(0)
    if stand.get("quote") != f"{quote:.4f}":
        raise ZertifikatFehler("Quote im Export passt nicht zu den Zählungen.")
    genug = (z["gesendet"] >= t["min_operationen"] and z["eroeffnen"] >= t["min_eroeffnen"] and z["schliessen"] >= t["min_schliessen"]
             and z["aendern"] >= t["min_aendern"])
    if not genug:
        return "LAEUFT"
    return "BESTANDEN" if quote >= Decimal(t["quote_min"]) else "NICHT_BESTANDEN"


def _ziel_s(stufe: int, t: dict) -> float:
    return t["kill_k3_max_s"] if stufe == 3 else t["kill_k1_k2_max_s"]


def _kills(stand: dict, t: dict) -> dict:
    """Je Stufe: Drills (an die Zielzeit gebunden) und echte Kills getrennt."""
    aus: dict[str, dict] = {}
    for k in stand.get("kills", []):
        e = aus.setdefault(f"K{k['stufe']}", {"drills": 0, "drill_max_s": 0.0, "ziel_max_s": _ziel_s(int(k["stufe"]), t), "echt": 0})
        if k.get("drill"):
            e["drills"] += 1
            e["drill_max_s"] = max(e["drill_max_s"], float(k["dauer_s"]))
        else:
            e["echt"] += 1
    return dict(sorted(aus.items()))


def _pruefen(stand: dict, t: dict, jetzt: str) -> None:
    if stand.get("urteil") != "BESTANDEN":
        raise ZertifikatFehler(f"Urteil ist {stand.get('urteil')}, nicht BESTANDEN – kein Zertifikat.")
    if urteil_nachrechnen(stand, t) != "BESTANDEN":
        raise ZertifikatFehler("Nachgerechnetes Urteil ist nicht BESTANDEN – kein Zertifikat.")
    if stand.get("offen") != 0:
        raise ZertifikatFehler(f"Am Fensterende sind Operationen offen ({stand.get('offen')}) – später erneut versuchen.")
    if stand.get("mindestens") != {k: t[k] for k in MINDESTENS} or stand.get("quote_min") != t["quote_min"]:
        raise ZertifikatFehler("Schwellen im Export weichen von config/tore.toml ab.")
    if stand.get("mechanik_hash") != jetzt:
        raise ZertifikatFehler("mechanik_hash des Exports weicht vom Code ab – kein Zertifikat (neue Messung nötig).")
    if any(k.get("drill") and float(k["dauer_s"]) > _ziel_s(int(k["stufe"]), t) for k in stand.get("kills", [])):
        raise ZertifikatFehler("Kill-Drill außerhalb der Zielzeit.")


def erstellen(export: Path, *, datum: str, commit: str, modus: str = "probe", ziel: Path | None = None,
              root: Path = ROOT) -> tuple[Path, Path]:
    """Zertifikat <datum>.json + .md und Exportkopie <datum>_export.json in `ziel` (Standard berichte/tor_t)."""
    ziel = ziel or root / "berichte" / "tor_t"
    roh = export.read_bytes()
    stand = json.loads(roh)
    t = tore()["tor_t"]
    jetzt = mechanik_hash(root)
    _pruefen(stand, t, jetzt)
    belege = []
    for name in BELEGE:
        pfad = root / "berichte" / "tor_t" / name
        text = pfad.read_text(encoding="utf-8") if pfad.is_file() else ""
        if jetzt not in text and f"{jetzt[:8]}…" not in text:            # T-PROBE nennt den Hash gekürzt
            raise ZertifikatFehler(f"Beleg {name} fehlt oder nennt nicht denselben mechanik_hash.")
        belege.append({"datei": name, "sha256": sha256(pfad)})
    kopie = ziel / f"{datum}_export.json"
    zert = {"schema": "tor_t_zertifikat/1", "datum": datum, "urteil": "BESTANDEN", "modus": modus, "mechanik_hash": jetzt,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}", "commit": commit, "tore_toml_sha256": sha256(TORE_PFAD),
            "export": {"datei": kopie.name, "sha256": hashlib.sha256(roh).hexdigest()},
            "fenster": {k: stand.get(k) for k in ("fenster_ab_seq", "fenster_bis_seq", "fenster_von_utc", "fenster_bis_utc")},
            "zaehlungen": {k: stand[k] for k in ZAEHLUNG}, "quote": stand["quote"], "quote_min": stand["quote_min"],
            "quote_ziel": stand["quote_ziel"], "mindestens": stand["mindestens"], "absicht_zu_operation": stand["absicht_zu_operation"],
            "lokal_abgelehnt": stand["lokal_abgelehnt"], "offen": stand["offen"], "skripte": stand["skripte"], "kills": _kills(stand, t),
            "defekte": stand["defekte"], "null_toleranz": list(NULL_TOLERANZ), "belege": belege}
    dateien = ((kopie, roh), (ziel / f"{datum}.json", (json.dumps(zert, ensure_ascii=False, indent=1) + "\n").encode("utf-8")),
               (ziel / f"{datum}.md", markdown(zert).encode("utf-8")))
    ziel.mkdir(parents=True, exist_ok=True)
    angelegt: list[Path] = []
    try:
        for pfad, inhalt in dateien:
            with pfad.open("xb") as f:                                   # exklusiv: nie überschreiben
                angelegt.append(pfad)
                f.write(inhalt)
    except FileExistsError as exc:
        for p in angelegt:
            p.unlink()
        raise ZertifikatFehler(f"Zertifikat {datum} existiert schon – nie überschreiben.") from exc
    except BaseException:
        for p in angelegt:
            p.unlink(missing_ok=True)
        raise
    return dateien[1][0], dateien[2][0]


def markdown(z: dict) -> str:
    n, m, f = z["zaehlungen"], z["mindestens"], z["fenster"]
    kills = "; ".join(f"{k}: {v['drills']} Drills, höchstens {v['drill_max_s']:.2f} s (Ziel ≤ {v['ziel_max_s']} s)"
                      + (f", {v['echt']} echt" if v["echt"] else "") for k, v in z["kills"].items()) or "–"
    zeilen = [f"# Tor-T-Zertifikat ({z['datum']})", "", "**Urteil: BESTANDEN** – Technik-Tor nach Plan F-1 §5 (D9), allein aus dem Journal "
              "nachgerechnet.", "",
              "| Punkt | Wert |", "|---|---|",
              f"| Modus | {z['modus']} |",
              f"| mechanik_hash | `{z['mechanik_hash']}` (Python {z['python']}) |", f"| Commit | `{z['commit']}` |",
              f"| config/tore.toml (SHA-256) | `{z['tore_toml_sha256']}` |",
              f"| Redigierter Export | `{z['export']['datei']}` (SHA-256 `{z['export']['sha256']}`) |",
              f"| Fenster | Satz {f['fenster_ab_seq']} ({f['fenster_von_utc']}) bis Satz {f['fenster_bis_seq']} ({f['fenster_bis_utc']}), UTC |",
              f"| Gesendete Orderoperationen | {n['gesendet']} (≥ {m['min_operationen']}) |",
              f"| Eröffnen / Schließen / Ändern | {n['eroeffnen']} / {n['schliessen']} / {n['aendern']} (≥ {m['min_eroeffnen']} / "
              f"{m['min_schliessen']} / {m['min_aendern']}) |",
              f"| Fehlerfrei | {n['fehlerfrei']} = Quote {float(z['quote']):.2%} (Tor ≥ {float(z['quote_min']):.0%}, Ziel "
              f"{float(z['quote_ziel']):.0%}) |",
              f"| Absicht → Operation | {float(z['absicht_zu_operation']):.2%} (lokal abgelehnt: {z['lokal_abgelehnt']}) |",
              f"| Offene Operationen am Fensterende | {z['offen']} |",
              f"| Null-Toleranz-Defekte | {len(z['defekte'])} |",
              "| Skripte | " + (", ".join(f"{k} {v}" for k, v in sorted(z["skripte"].items())) or "keine im Fenster") + " |",
              f"| Kill-Stufen | {kills} |",
              "", "Geprüfte Null-Toleranz-Arten: " + ", ".join(z["null_toleranz"]) + ".", "",
              "## Belege unter demselben mechanik_hash", ""]
    zeilen += [f"- `{b['datei']}` (SHA-256 `{b['sha256'][:16]}…`)" for b in z["belege"]]
    probe = ("Die T-PROBE-Skripte liegen zusätzlich im gemessenen Fenster selbst (Zeile Skripte). "
             if "PASS" in z["skripte"].values() else "Im gemessenen Fenster liegen keine T-PROBE-Skripte; T-PROBE nur über den Beleg. ")
    zeilen += ["", probe + "Wochenende und Mittwochs-Rollover mit offener Position sind im Trockenlauf belegt; Probe-Positionen auf Demo "
               "halten nie über Nacht. Das Zertifikat gilt, solange der mechanik_hash gleich bleibt – jede Änderung am Geldpfad verlangt eine "
               "neue Messung.", "", EINORDNUNG, ""]
    return "\n".join(zeilen)
