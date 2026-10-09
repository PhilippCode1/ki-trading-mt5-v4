"""Meldungen an den Betreiber: Journal (immer, durch den Takt), Datei MELDUNGEN.txt in der Ablage, optional Windows-Benachrichtigung.

Die Benachrichtigung läuft als eigener PowerShell-Prozess ohne Shell; der Text geht nur über eine Umgebungsvariable (keine
Befehlseinschleusung). Scheitert sie, bleibt die Datei – der Takt läuft immer weiter.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
    "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
    "$x = $t.GetElementsByTagName('text');"
    "$x.Item(0).AppendChild($t.CreateTextNode('KI-Trading Bot')) > $null;"
    "$x.Item(1).AppendChild($t.CreateTextNode($env:KIT_MELDUNG)) > $null;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
    ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
)


class DateiMelder:
    def __init__(self, ablage: Path, *, windows: bool = False) -> None:
        self.datei = Path(ablage) / "MELDUNGEN.txt"
        self.windows = windows and os.name == "nt"

    def melden(self, stufe: str, text: str) -> None:
        zeile = f"{dt.datetime.now().astimezone():%Y-%m-%d %H:%M:%S} {stufe:8} {text}\n"
        try:
            self.datei.parent.mkdir(parents=True, exist_ok=True)
            with open(self.datei, "a", encoding="utf-8") as fh:
                fh.write(zeile)
        except OSError:
            pass
        if self.windows and stufe in ("WARNUNG", "ALARM"):
            try:
                subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", TOAST],
                                 env={**os.environ, "KIT_MELDUNG": f"{stufe}: {text}"[:250]},
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass


class ListenMelder:
    def __init__(self) -> None:
        self.meldungen: list[tuple[str, str]] = []

    def melden(self, stufe: str, text: str) -> None:
        self.meldungen.append((stufe, text))
