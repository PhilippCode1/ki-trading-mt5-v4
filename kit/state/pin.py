"""PIN des Betreibers (Plan F-1 §6.3): nur als scrypt-Hash unter %LOCALAPPDATA%\\kit\\freigaben\\pin.json, nie im Chat oder Repo.

Setzen und Prüfen nur interaktiv in der Konsole des Betreibers (CLI erzwingt ein Terminal; der Agent ist zusätzlich per Hook
gesperrt). Eine bestehende PIN ändert nur, wer sie kennt. Fehlversuche verzögern.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from pathlib import Path

N, R, P = 2**16, 8, 1
SPEICHER = 2**27                                   # scrypt mit N = 2^16 braucht 64 MiB
MIN_LAENGE = 10
MAX_FEHLER = 5
SPERRE_S = 3600.0


class PinFehler(RuntimeError):
    """PIN fehlt, ist falsch oder zu kurz."""


def _datei(freigaben: Path) -> Path:
    return Path(freigaben) / "pin.json"


def _hash(pin: str, salz: bytes, n: int = N, r: int = R, p: int = P) -> bytes:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salz, n=n, r=r, p=p, dklen=32, maxmem=SPEICHER)


def _fehler_datei(freigaben: Path) -> Path:
    return Path(freigaben) / "pin_fehler.json"


def _fehler_lesen(freigaben: Path) -> dict:
    try:
        return json.loads(_fehler_datei(freigaben).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"anzahl": 0, "letzter": 0.0}


def gesetzt(freigaben: Path) -> bool:
    return _datei(freigaben).exists()


def pruefen(freigaben: Path, pin: str, *, uhr: Callable[[], float] = time.time) -> None:
    """Fehlversuche werden dauerhaft gezählt: nach 5 falschen PINs 1 Stunde gesperrt (gegen Durchprobieren)."""
    datei = _datei(freigaben)
    if not datei.exists():
        raise PinFehler("Keine PIN gesetzt – zuerst `kit pin-setzen` in der eigenen Konsole.")
    fehler = _fehler_lesen(freigaben)
    if fehler["anzahl"] >= MAX_FEHLER and uhr() - fehler["letzter"] < SPERRE_S:
        raise PinFehler("Zu viele falsche PINs – Eingabe für 1 Stunde gesperrt.")
    try:
        d = json.loads(datei.read_text(encoding="utf-8"))
        soll = bytes.fromhex(d["hash"])
        ist = _hash(pin, bytes.fromhex(d["salz"]), d["n"], d["r"], d["p"])
    except (OSError, ValueError, KeyError) as exc:
        raise PinFehler("PIN-Datei unlesbar – Entsperren unmöglich (fail-closed).") from exc
    if not hmac.compare_digest(soll, ist):
        anzahl = fehler["anzahl"] + 1 if uhr() - fehler["letzter"] < SPERRE_S else 1
        _fehler_datei(freigaben).write_text(json.dumps({"anzahl": anzahl, "letzter": uhr()}), encoding="utf-8")
        time.sleep(2.0)
        raise PinFehler("PIN falsch.")
    _fehler_datei(freigaben).unlink(missing_ok=True)


def setzen(freigaben: Path, neu: str, *, alt: str | None = None) -> None:
    if len(neu) < MIN_LAENGE:
        raise PinFehler(f"PIN zu kurz (mindestens {MIN_LAENGE} Zeichen).")
    if gesetzt(freigaben):
        if alt is None:
            raise PinFehler("Es gibt schon eine PIN – zum Ändern die alte PIN angeben.")
        pruefen(freigaben, alt)
    salz = secrets.token_bytes(16)
    datei = _datei(freigaben)
    datei.parent.mkdir(parents=True, exist_ok=True)
    tmp = datei.with_suffix(".tmp")
    tmp.write_text(json.dumps({"salz": salz.hex(), "hash": _hash(neu, salz).hex(), "n": N, "r": R, "p": P}), encoding="utf-8")
    tmp.replace(datei)
