"""Nur anhängendes Journal: eine JSON-Zeile je Satz, flush + fsync vor jeder Sendung, Hashkette, Tagesdatei (UTC).

- Kontokennungen sind verboten: jeder Schlüssel, der einen der Wortstämme login/passw/server/konto/account/investor/
  email/company enthält oder genau "name" heißt, wirft (Schema-Sperre).
- Dateien laufen nie rückwärts: springt die Uhr über eine Tagesgrenze zurück, wird in die jüngste Datei weitergeschrieben.
- Eine beim Schreiben abgerissene letzte Zeile (Stromausfall, voller Datenträger) wurde vor keiner Sendung bestätigt; sie wird
  beim Öffnen verworfen und als Vorfall JOURNAL_REST_VERWORFEN festgehalten. Jede andere Beschädigung wirft.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

VERBOTENE_STAEMME = ("login", "passw", "server", "konto", "account", "investor", "email", "company")
GENESIS = "0" * 64


class JournalFehler(RuntimeError):
    """Journal unlesbar oder Hashkette gebrochen."""


def _pruefe_schluessel(wert: object, pfad: str = "") -> None:
    if isinstance(wert, dict):
        for k, v in wert.items():
            norm = re.sub(r"[_\-. ]", "", str(k).lower())
            if norm == "name" or any(stamm in norm for stamm in VERBOTENE_STAEMME):
                raise ValueError(f"Journal: verbotener Schlüssel {pfad}{k} (Kontokennung)")
            _pruefe_schluessel(v, f"{pfad}{k}.")
    elif isinstance(wert, (list, tuple)):
        for v in wert:
            _pruefe_schluessel(v, pfad)


def _hash(satz: dict) -> str:
    return hashlib.sha256(json.dumps(satz, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, ordner: Path, uhr: Callable[[], float] = time.time, *, fsync: bool = True) -> None:
        self.ordner = Path(ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.uhr = uhr
        self.fsync = fsync                 # nur Backtest/T-SIM ohne echtes Geld dürfen auf fsync verzichten
        verworfen = self._rest_reparieren()
        saetze = self.lesen()
        self._seq = saetze[-1]["seq"] if saetze else 0
        self._kopf = saetze[-1]["h"] if saetze else GENESIS
        dateien = sorted(self.ordner.glob("*.jsonl"))
        self._letzte_datei = dateien[-1].name if dateien else ""
        if verworfen:
            self.schreiben("VORFALL", "JOURNAL_REST_VERWORFEN", "Abgerissene letzte Journalzeile verworfen (nie bestätigt).",
                           bytes_verworfen=verworfen)

    def _rest_reparieren(self) -> int:
        dateien = sorted(self.ordner.glob("*.jsonl"))
        if not dateien:
            return 0
        datei = dateien[-1]
        roh = datei.read_bytes()
        if not roh or roh.endswith(b"\n"):
            return 0
        schnitt = roh.rfind(b"\n") + 1
        try:
            json.loads(roh[schnitt:].decode("utf-8"))
            return 0                       # vollständige Zeile ohne Zeilenende: behalten
        except ValueError:
            with open(datei, "r+b") as fh:
                fh.truncate(schnitt)
                fh.flush()
                os.fsync(fh.fileno())
            return len(roh) - schnitt

    def _datei(self, t: float) -> Path:
        name = f"{datetime.fromtimestamp(t, UTC):%Y-%m-%d}.jsonl"
        return self.ordner / max(name, self._letzte_datei)

    def schreiben(self, art: str, code: str, text: str, **daten: object) -> dict:
        _pruefe_schluessel(daten)
        t = self.uhr()
        satz = {"seq": self._seq + 1, "t": round(t, 6), "art": art, "code": code, "text": text, "daten": daten, "prev": self._kopf}
        satz = json.loads(json.dumps(satz, ensure_ascii=False, default=str))   # Decimal -> str, Form wie beim Lesen
        satz["h"] = _hash(satz)
        zeile = json.dumps(satz, ensure_ascii=False, sort_keys=True) + "\n"
        datei = self._datei(t)
        with open(datei, "a", encoding="utf-8") as fh:
            fh.write(zeile)
            fh.flush()
            if self.fsync:
                os.fsync(fh.fileno())
        self._seq, self._kopf, self._letzte_datei = satz["seq"], satz["h"], datei.name
        return satz

    def lesen(self) -> list[dict]:
        return lesen(self.ordner)

    def hat_eintraege(self) -> bool:
        return any(self.ordner.glob("*.jsonl"))


def lesen(ordner: Path, *, nur_lesen: bool = False) -> list[dict]:
    """Alle Sätze mit Prüfung der Hashkette. nur_lesen=True (Status, Tor T neben dem laufenden Bot): eine noch nicht
    abgeschlossene letzte Zeile wird übergangen statt repariert – diese Funktion schreibt nie."""
    saetze: list[dict] = []
    vorher = GENESIS
    dateien = sorted(Path(ordner).glob("*.jsonl"))
    for datei in dateien:
        roh = datei.read_text(encoding="utf-8")
        zeilen = roh.split("\n")
        if nur_lesen and datei == dateien[-1] and zeilen and zeilen[-1].strip():
            zeilen = zeilen[:-1]                   # letzte Zeile wird gerade geschrieben
        for nr, zeile in enumerate(zeilen, 1):
            if not zeile.strip():
                continue
            try:
                satz = json.loads(zeile)
            except ValueError as exc:
                raise JournalFehler(f"{datei.name}:{nr} unlesbar") from exc
            h = satz.pop("h", None)
            if satz.get("prev") != vorher or _hash(satz) != h:
                raise JournalFehler(f"{datei.name}:{nr} Hashkette gebrochen")
            satz["h"] = h
            vorher = h
            saetze.append(satz)
    return saetze
