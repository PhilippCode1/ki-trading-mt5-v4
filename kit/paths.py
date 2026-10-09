"""Laufzeitablage des Bots: <Benutzerprofil>\\KI-Trading-Bot\\<modus>\\ (nie im Repo), je Modus getrennt.

- Warum nicht %LOCALAPPDATA%: Prozesse paketierter Windows-Apps (z. B. der Claude-Desktop-App und alles, was sie startet)
  schreiben dorthin nur scheinbar – Windows leitet es in einen privaten Paket-Cache um. Die Konsole des Betreibers sähe andere
  Dateien als der Bot: STOP-Datei, `kit stop`, `kit status`, PIN und Entsperren gingen ins Leere. Das Benutzerprofil selbst wird
  nicht umgeleitet (geprüft 05.10.2026). Altbestand aus der umgeleiteten Ablage holt `kit umziehen` herüber; bis dahin
  verweigert kit.umzug.pruefen() jeden Start (sonst begänne die neue Ablage ohne Sperren, Anker und PIN).
- Der Ordner kommt unter Windows aus der Shell-API (SHGetKnownFolderPath), nicht aus Umgebungsvariablen: eine umgebogene
  Ablage wäre ein Weg, dauerhafte Sperren, Anker und Journale zu umgehen.
- Tests dürfen den echten Zustand nie berühren: nur unter pytest gilt KIT_HOME (kit_tests/conftest.py setzt es auf einen
  temporären Ordner); ohne KIT_HOME bricht kit_home() unter pytest ab. Außerhalb von pytest ist KIT_HOME verboten.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

MODI = ("sim", "trocken", "backtest", "probe", "demo", "live")
ORDNER = "KI-Trading-Bot"
PROFIL = "{5E6C858F-0E22-4760-9AFE-EA3317B67173}"          # FOLDERID_Profile
LOKALE_DATEN = "{F1B32785-6FBA-4FCF-9D55-7B8E7F157091}"    # FOLDERID_LocalAppData


class AblageFehler(RuntimeError):
    """Unzulässiger Zugriff auf die Laufzeitablage."""


def _unter_pytest() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and "pytest" in sys.modules


def _bekannter_ordner(kennung: str) -> Path:
    import ctypes
    import uuid
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    guid = GUID.from_buffer_copy(uuid.UUID(kennung).bytes_le)
    zeiger = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(zeiger)) != 0:
        raise AblageFehler("Bekannter Windows-Ordner nicht ermittelbar.")
    try:
        return Path(zeiger.value or "")
    finally:
        ctypes.windll.ole32.CoTaskMemFree(zeiger)


def benutzerprofil() -> Path:
    return _bekannter_ordner(PROFIL) if os.name == "nt" else Path.home()


def lokale_anwendungsdaten() -> Path:
    return _bekannter_ordner(LOKALE_DATEN) if os.name == "nt" else Path.home() / ".local" / "share"


def alte_ablage() -> Path:
    """Frühere Ablage (bis F-03b): %LOCALAPPDATA%\\kit – aus einer paketierten App gesehen der umgeleitete Paket-Cache."""
    return lokale_anwendungsdaten() / "kit"


def kit_home() -> Path:
    eigen = os.environ.get("KIT_HOME")
    if _unter_pytest():                                 # nur ein echter pytest-Lauf (Variable allein genügt nicht)
        if not eigen:
            raise AblageFehler("Unter pytest ist die echte Laufzeitablage gesperrt – KIT_HOME setzen.")
        return Path(eigen)
    if eigen and not _unter_pytest():
        raise AblageFehler("KIT_HOME ist nur in Tests erlaubt – die Laufzeitablage ist fest, damit Sperren nicht über eine "
                           "andere Ablage umgangen werden.")
    return benutzerprofil() / ORDNER


def ablage(modus: str) -> Path:
    if modus not in MODI:
        raise AblageFehler(f"Unbekannter Modus {modus!r}; erlaubt: {', '.join(MODI)}")
    return kit_home() / modus
