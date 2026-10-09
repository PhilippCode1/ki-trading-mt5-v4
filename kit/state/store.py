"""Zustand des Bots (atomar), Ein-Schreiber-Sperre (Betriebssystem-Lock), Kill-Stufe (STOP-Datei), Kontoabdruck (HMAC).

Fail-closed: unlesbarer Zustand → Sperre; fehlender Zustand, obwohl ein Journal existiert → Sperre (Zurücksetzen durch Löschen
ist damit kein Weg aus LOSS_LOCK oder 50-%-Sperre).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

STUFEN = {"K1": 1, "K2": 2, "K3": 3}


class ZustandFehler(RuntimeError):
    """Zustand fehlt oder ist unlesbar – Handel gesperrt."""


class SchreiberAktiv(RuntimeError):
    """Ein anderer Prozess hält die Schreibsperre."""


class StateStore:
    def __init__(self, ordner: Path) -> None:
        self.ordner = Path(ordner)
        self.ordner.mkdir(parents=True, exist_ok=True)
        self.datei = self.ordner / "zustand.json"

    def laden(self, journal_vorhanden: bool) -> dict:
        if not self.datei.exists():
            if journal_vorhanden:
                raise ZustandFehler("ZUSTAND_FEHLT: Journal vorhanden, Zustand fehlt – Sperre (Betreiber prüfen).")
            return {}
        try:
            daten = json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ZustandFehler("ZUSTAND_UNLESBAR – Sperre (Betreiber prüfen).") from exc
        if not isinstance(daten, dict):
            raise ZustandFehler("ZUSTAND_UNLESBAR – Sperre (Betreiber prüfen).")
        return daten

    def speichern(self, zustand: dict) -> None:
        tmp = self.datei.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(zustand, fh, ensure_ascii=False, sort_keys=True, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        for _ in range(40):                     # Windows: ein Leser (Statusseite, Virenscanner) blockiert kurz das Ersetzen
            try:
                os.replace(tmp, self.datei)
                return
            except PermissionError:
                time.sleep(0.05)
        raise ZustandFehler("ZUSTAND_NICHT_GESPEICHERT: Datei dauerhaft blockiert – Sperre (fail-closed).")


class Schreibsperre:
    """Exklusive Sperre über eine Datei; das Betriebssystem gibt sie bei Prozessende frei (kein veralteter Lock)."""

    def __init__(self, ordner: Path) -> None:
        self.pfad = Path(ordner) / "LOCK"
        self._fh = None

    def __enter__(self) -> Schreibsperre:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.pfad, "a+b")  # noqa: SIM115 - bleibt bis __exit__ offen
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise SchreiberAktiv(f"Schreibsperre {self.pfad} ist belegt – läuft schon ein Bot?") from exc
        self._fh = fh
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None


def stop_stufe(ordner: Path) -> int:
    """0 = kein Kill; sonst die höchste in der STOP-Datei genannte Stufe K1/K2/K3. Kodierung egal (UTF-8 mit/ohne BOM,
    UTF-16 wie von PowerShell 5.1 geschrieben). Existiert die Datei, ist aber unlesbar oder ohne Stufe → K1 (fail-closed)."""
    pfad = Path(ordner) / "STOP"
    if not pfad.exists():
        return 0
    try:
        roh = pfad.read_bytes()
    except OSError:
        return 1
    try:
        text = roh.decode("utf-16") if roh[:2] in (b"\xff\xfe", b"\xfe\xff") else roh.decode("utf-8-sig", errors="replace")
    except ValueError:
        text = roh.decode("latin-1")
    stufen = [STUFEN[m.upper()] for m in re.findall(r"(?i)K[123]", text)]
    return max(stufen) if stufen else 1


def stop_setzen(ordner: Path, stufe: int) -> None:
    pfad = Path(ordner) / "STOP"
    if stufe <= 0:
        pfad.unlink(missing_ok=True)
        return
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(f"K{min(stufe, 3)}\n", encoding="utf-8")
    os.replace(tmp, pfad)


def kontoabdruck(login: int, server: str, schluessel_ordner: Path) -> str:
    """HMAC-SHA256(lokaler Schlüssel, login|server)[:32]; der Schlüssel liegt nur lokal und nie im Repo."""
    ordner = Path(schluessel_ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    datei = ordner / "hmac.key"
    if not datei.exists():
        datei.write_bytes(secrets.token_bytes(32))
    schluessel = datei.read_bytes()
    return hmac.new(schluessel, f"{int(login)}|{server}".encode(), hashlib.sha256).hexdigest()[:32]
