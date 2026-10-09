# Windows-VPS einrichten – Skripte in Reihenfolge

Ausführliche Anleitung mit Begründungen: [`docs/INSTALLATION_VPS.md`](../../docs/INSTALLATION_VPS.md). Betrieb: [`docs/BETRIEB.md`](../../docs/BETRIEB.md).

> **Stand 09.10.2026: Projekt ruht (Entscheidung ENDE, Lauf F-05e).** Für den Entwicklungsplatz nur die Schritte 0, 1, 2 (ohne Autologon), 3 mit `-OhneMt5` und 6. Schritte 4 und 5, Autologon und MT5 erst bei einer Wiederaufnahme des Bots. Reihenfolge inklusive Laptop-Abschluss: [`docs/INSTALLATION_VPS.md`](../../docs/INSTALLATION_VPS.md) §0a.

Alle Skripte sind Windows PowerShell 5.1, nur ASCII und mehrfach ausführbar. Mit `-WhatIf` zeigen sie nur an, was sie tun würden. Sie speichern **keine** Passwörter, Tokens oder Kontonummern. Passwörter gibst nur du interaktiv ein (Windows-Benutzer, Autologon, MT5-Anmeldung, GitHub, Claude, Tailscale).

Aufruf: `powershell -ExecutionPolicy Bypass -File .\<skript>.ps1`. Vorher `vps.config.example.psd1` nach `vps.config.psd1` kopieren und anpassen; `vps.config.psd1` wird nicht committet.

| # | Skript | Als | Was |
|---|---|---|---|
| 0 | `00_vorpruefung.ps1` | beliebig | Nur lesen: Windows, RAM/CPU/Platz, Virtualisierung (Docker/WSL2), Zeitdienst, Ports, Werkzeuge |
| 1 | `10_system.ps1` | Administrator | Kein Standby, NTP, Windows-Update ohne Zwangsneustart, Firewall, lange Pfade; `-RdpNurTailscale` erst nach `tailscale up` |
| 2 | `20_benutzer.ps1` | Administrator | Benutzer `kitbot` (Bot, Autologon) und `kitdev` (Agent); Ordner `C:\KI-Trading\{mt5-demo,sicherung,austausch}` mit getrennten Rechten |
| – | Sysinternals Autologon | Betreiber | `kitbot` dauerhaft anmelden (MT5 braucht eine Desktop-Sitzung) |
| 3 | `30_software.ps1` | Administrator | Git, GitHub CLI, Python 3.11/3.12, Tailscale, optional Docker; MT5-Installer (Ordner `C:\KI-Trading\mt5-demo`), nicht mit `-OhneMt5` (nur Entwicklung) |
| 4 | `40_bot.ps1 -Tag <tag>` | `kitbot` | Repo (nur lesen), `.venv-bot` hash-gesperrt, `kit pruefen`, `kit installieren`; `-Uebernahme <Ordner>` holt den Laptop-Bestand |
| – | MT5 + kit | `kitbot` | Im Terminal mit DEMO anmelden, Algo Trading an; `kit konto-registrieren`, `kit rauchtest`, `kit pin-setzen` |
| 5 | `50_aufgaben.ps1` | Administrator | Aufgaben „KI-Trading Bot“ (bei Anmeldung), „Sicherung“ (täglich), „Status“ (alle 15 min) – ohne gespeichertes Passwort. **Achtung:** Die Bot-Aufgabe startet `bot_dienst.ps1` im Modus `probe` und sendet bei jeder Anmeldung von `kitbot` Demo-Orders; solange das Projekt ruht, nicht ausführen |
| 6 | `60_agent.ps1` | `kitdev` | Claude Code, Entwicklungs-Checkout (Remote `private`), `.venv-311`/`.venv-312`/`.venv-forschung`, Hooks, `tools\dev.ps1 alles`; danach Betreiber: Git- und `gh`-Anmeldung, Sperrliste (INSTALLATION_VPS §6) |
| – | `90_status.ps1` | beliebig | Gesundheitsblick: Aufgaben, Prozesse, Status-Export, Platz, Zeit, Sicherung |

Hilfsskripte, die die Aufgaben aufrufen: `bot_dienst.ps1` (Autostart mit Neustart-Pause), `sicherung.ps1`, `status_export.ps1`. Gemeinsame Funktionen: `_gemeinsam.ps1`.
