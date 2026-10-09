# Installation auf dem Windows-VPS

Schritt-für-Schritt-Anleitung für den Windows-VPS: Entwicklungsplatz (Benutzer `kitdev` mit Claude Code) und, optional, Demo-Bot (Benutzer `kitbot`, Umzug vom Laptop). Die Skripte liegen in [`deploy/windows-vps/`](../deploy/windows-vps/README.md). Zielbild und Begründungen: [ARCHITEKTUR.md](ARCHITEKTUR.md) §6, [SICHERHEIT.md](SICHERHEIT.md), Ideenliste: [VPS_IDEEN.md](VPS_IDEEN.md).

> **Projekt ruht (seit 09.10.2026, Lauf F-05e).** Entscheidung ENDE: kein Bot, kein Demo-Live, keine Forschung ohne neue Zielzeile. Der VPS ist vorerst nur Entwicklungsplatz. Es gilt der Weg **nur Entwicklung**: §0a, §1–§3 (`30_software.ps1 -OhneMt5`, ohne Autologon), §6 und §7a. **Nicht** ausführen: §4, §4a, §4b, §5, MT5 und Autologon. Die Aufgabe aus `50_aufgaben.ps1` startet den Bot bei jeder Anmeldung von `kitbot` im Modus `probe` und sendet dann Demo-Orders. Tor T ist bestanden und zertifiziert (`berichte/tor_t/2026-10-09.md`); das Zertifikat gilt, solange der `mechanik_hash` `4fab5281…` unverändert bleibt.

**Grundregeln**
- Passwörter, Tokens und Kontonummern gibst nur du ein: Windows, Autologon, MT5, GitHub, Claude, Tailscale. Kein Skript speichert sie.
- Der Bot handelt nur auf DEMO. Live ist nicht vorgesehen (kein belegter Vorteil). Falls doch, dann nur auf einem eigenen Rechner bzw. Benutzer ohne Agent, und schalten kannst nur du.
- Jedes Skript zeigt mit `-WhatIf` vorher an, was es tun würde.

## 0. Zielbild

```
Windows-VPS (Server 2022/2025)
├── Benutzer kitbot  (Autologon, Desktop-Sitzung) – nur bei Bot-Betrieb
│   ├── MT5-Demo-Terminal  C:\KI-Trading\mt5-demo\terminal64.exe /portable
│   ├── Bot  %USERPROFILE%\KI-Trading-Bot\app\<tag>  (gestartet von Aufgabe "KI-Trading Bot" → bot_dienst.ps1)
│   ├── Bot-Ablage  %SystemDrive%\Users\kitbot\KI-Trading-Bot  (Journal, Zustand, Sperren, PIN, Schlüssel – nur kitbot)
│   └── Aufgaben: Sicherung (täglich) → C:\KI-Trading\sicherung, Status (15 min) → C:\KI-Trading\austausch
├── Benutzer kitdev  (Claude Code, Entwicklung, Tests; liest nur C:\KI-Trading\austausch)
│   ├── Repo  %SystemDrive%\Users\kitdev\ki-trading  (Claude-Sitzungen nur hier)
│   ├── Forschungsablage  %SystemDrive%\Users\kitdev\KI-Trading-Bot\marktdaten  (Kerzenbestand, nur für neue Forschung)
│   └── Sperrliste  %LOCALAPPDATA%\kit\sperrliste.txt von kitdev  (legt nur der Betreiber an)
└── Administrator  (nur Einrichtung und Wartung)
Fernzugriff: nur über Tailscale (RDP aus dem Tailnet). Optional daneben: Linux-Begleit-VPS für Container-Dienste.
```

Solange das Projekt ruht, gibt es nur `kitdev` und den Administrator. `kitbot` darf angelegt sein (`20_benutzer.ps1`), bleibt aber ohne Autologon, ohne MT5 und ohne Aufgaben.

## 0a. Reihenfolge unter ENDE (nur du)

**Laptop** (eigene PowerShell im Repo-Ordner):
1. T-DAUER beenden, und zwar außerhalb des Probe-Fensters (Freitag, 09.10., nach 20:05 oder am Wochenende). `--beenden` lässt eine offene Probe-Position mit Server-SL/TP stehen; nach dem Fenster ist keine offen. Danach MT5 schließen.
```bash
.venv-311\Scripts\python.exe -m kit stop --beenden --modus probe
```
2. Abschlusssicherung auf ein Offline-Medium (nie Cloud oder Mail). Die ZIP enthält HMAC-Schlüssel und PIN-Hash.
```bash
.venv-311\Scripts\python.exe -m kit sichern --ziel <Offline-Ordner> --mit-schluessel
```
3. Zusätzlich offline kopieren, beides steckt nicht in `kit sichern`:
   - `%USERPROFILE%\KI-Trading-Bot\marktdaten\entwicklung.sqlite` (Kerzenbestand; ein Neuabzug ist nicht garantiert bitgleich)
   - `%LOCALAPPDATA%\kit\sperrliste.txt` (für `publish.py --oeffentlich` und den Commit-Scan; liegt sonst nirgends)
4. Ab jetzt auf dem Laptop nicht mehr committen (ein Arbeitsplatz). Die Tags `rel/F-03b-1`/`-2` liegen seit F-05e auch im privaten Repo; auf dem VPS installierst du trotzdem immer einen `lauf/<ID>`-Tag (§4b).

**VPS:**
5. §1–§3 als Administrator: `30_software.ps1 -OhneMt5`, **kein Autologon**, `tailscale up`, RDP über die Tailscale-Adresse testen, dann `10_system.ps1 -RdpNurTailscale` und Port 3389 beim Anbieter schließen.
6. §6 als `kitdev` (`60_agent.ps1`, Anmeldungen, Sperrliste, erste Sitzung), dann §7a.
7. Nicht ausführen, solange das Projekt ruht: §4, §4a, §4b, §5 (`40_bot.ps1`, `50_aufgaben.ps1`), MT5, Autologon.

## 1. VPS auswählen

| Eigenschaft | Empfehlung | Warum |
|---|---|---|
| System | Windows Server 2022 oder 2025, Desktop-Erfahrung | MT5 und das Python-Paket `MetaTrader5` laufen nur unter Windows und brauchen einen Desktop |
| Leistung | 4 vCPU, 8–16 GB RAM, ≥ 80 GB SSD | MT5 + Bot + Claude Code + Tests gleichzeitig |
| Standort | Europa, nah am Handelsserver des Brokers (London, Frankfurt oder Amsterdam) | kurze Antwortzeiten bei `order_send` |
| Virtualisierung | verschachtelte Virtualisierung nur nötig, wenn Docker/WSL2 auf demselben VPS laufen soll | sonst Zusatzdienste auf einen Linux-Begleiter auslagern |
| Extras | Snapshots/Backups beim Anbieter, eigene Anbieter-Firewall, 2FA am Kundenkonto | schneller Rückweg, kein offenes RDP |

## 2. Erste Anmeldung (Administrator)

1. Per RDP als Administrator anmelden (Zugangsdaten vom Anbieter) und das Administrator-Passwort sofort ändern.
2. Windows Update vollständig durchlaufen lassen und neu starten.
3. Skripte auf den VPS bringen. Am einfachsten: In der RDP-Verbindung das Laufwerk des Laptops freigeben (*Lokale Ressourcen → Laufwerke*). Dann den Ordner `deploy\windows-vps` nach `C:\KI-Trading-Setup` kopieren.
4. In einer **Administrator-PowerShell**:
```bash
cd C:\KI-Trading-Setup
```
```bash
Copy-Item vps.config.example.psd1 vps.config.psd1
```
```bash
notepad vps.config.psd1
```
Prüfen bzw. anpassen: Benutzernamen, Repo-URL, Wartungszeiten. Danach die Vorprüfung:
```bash
powershell -ExecutionPolicy Bypass -File .\00_vorpruefung.ps1
```

## 3. System, Benutzer, Software (Administrator)

```bash
powershell -ExecutionPolicy Bypass -File .\10_system.ps1
```
`10_system.ps1` lässt Windows-Updates nur herunterladen. Ohne Bot gibt es kein Wartungsfenster ([BETRIEB.md](BETRIEB.md) §4): Installiere die Updates deshalb wöchentlich selbst (*Einstellungen → Windows Update*, danach Neustart).
```bash
powershell -ExecutionPolicy Bypass -File .\20_benutzer.ps1
```
Das Skript fragt die Passwörter für `kitbot` und `kitdev` ab; nur du kennst sie. Es legt außerdem die Konfiguration zentral unter `C:\KI-Trading\vps.config.psd1` ab. Diese Datei gilt für alle späteren Skripte und Aufgaben; spätere Änderungen also dort.

**Nur bei Bot-Betrieb** (nicht, solange das Projekt ruht): **Autologon** für `kitbot` einrichten: [Sysinternals Autologon](https://learn.microsoft.com/sysinternals/downloads/autologon) laden, starten, Benutzer `kitbot` und Passwort eintragen, *Enable*. Autologon legt das Passwort verschlüsselt ab.

Software (Git, GitHub CLI, Python 3.11/3.12, Tailscale). Solange das Projekt ruht, ohne MT5:
```bash
powershell -ExecutionPolicy Bypass -File .\30_software.ps1 -OhneMt5
```
Bei Bot-Betrieb ohne `-OhneMt5`; nur dann im MT5-Installer unter *Einstellungen* den Ordner `C:\KI-Trading\mt5-demo` wählen und **nicht** anmelden. Danach Tailscale verbinden (öffnet die Anmeldung im Browser):
```bash
tailscale up
```
Erst wenn du dich über die Tailscale-Adresse des VPS per RDP anmelden kannst, RDP auf das Tailnet beschränken und beim Anbieter Port 3389 schließen:
```bash
powershell -ExecutionPolicy Bypass -File .\10_system.ps1 -RdpNurTailscale
```

## 4. Bot einrichten (als `kitbot`, nur bei Wiederaufnahme des Bots)

Nicht, solange das Projekt ruht. Voraussetzung: §3 mit Autologon und ohne `-OhneMt5`.

Abmelden und als `kitbot` anmelden (bzw. Neustart → Autologon). Die Skripte liegen nach dem ersten Klonen im Repo. Für den ersten Lauf nimmst du sie noch aus `C:\KI-Trading-Setup`:
```bash
powershell -ExecutionPolicy Bypass -File C:\KI-Trading-Setup\40_bot.ps1
```
Git fragt dabei nach der GitHub-Anmeldung. Empfohlen ist ein **Fine-grained Personal Access Token mit nur Lesezugriff auf das private Repo**: Der Bot-Benutzer soll nichts pushen können.

MT5 portabel starten, mit dem **Demokonto** anmelden, *Algo Trading* einschalten. Unter *Extras → Optionen → Charts* „Max. Balken im Chart“ auf *Unbegrenzt* stellen. Unter *Expert Advisors* „Algo-Trading bei Kontowechsel deaktivieren“ angehakt lassen.
```bash
& 'C:\KI-Trading\mt5-demo\terminal64.exe' /portable
```

### 4a. Bestand vom Laptop (nur bei Wiederaufnahme des Bots)

**Solange das Projekt ruht:** Die Abschlusssicherung aus §0a bleibt offline und wird **nicht** auf dem VPS wiederhergestellt.

Bei Wiederaufnahme bringt die Sicherung Tor-T-Journal, Anker, Sperren, PIN und Demo-Allowlist mit. Die ZIP enthält den HMAC-Schlüssel und den PIN-Hash. Übertrage sie nur über die RDP-Laufwerksfreigabe oder `tailscale file cp`, nie per Mail oder Cloud-Ordner. **Auf dem VPS** als `kitbot` im Repo-Ordner `%SystemDrive%\Users\kitbot\ki-trading`:
```bash
.\.venv-bot\Scripts\python.exe -m kit wiederherstellen --aus $env:SystemDrive\Users\kitbot\Desktop\kit-sicherung-<zeit>.zip
```
Danach die ZIP vom Desktop löschen; sie bleibt offline erhalten. Den Kerzenbestand braucht der Bot nicht; er gehört zu `kitdev` (§6).

**Tor T** ist seit 09.10.2026 bestanden und zertifiziert (`berichte/tor_t/2026-10-09.md`: 378 Sendungen, 100 % fehlerfrei, 0 Defekte, `mechanik_hash` `4fab5281…` mit Python 3.11, Commit `62e782f`). Das Zertifikat gilt auch für den Bot auf dem VPS, solange dort Python 3.11 läuft und ein Tag mit demselben `mechanik_hash` installiert wird. Jede Änderung an den Geldpfad-Dateien braucht eine neue Tor-T-Messung.

### 4b. Prüfen, registrieren, installieren

`40_bot.ps1` hat `%USERPROFILE%\KI-Trading-Bot\lokal.toml` mit dem Terminalpfad `C:\KI-Trading\mt5-demo\terminal64.exe` angelegt. Dort dürfen nur `[terminal] pfad` und `[symbol_namen]` stehen. Broker-Suffixe wie `EURUSD.a` trägst du ebenfalls dort ein, nicht im Repo.

```bash
.\.venv-bot\Scripts\python.exe -m kit pruefen
```
```bash
.\.venv-bot\Scripts\python.exe -m kit rauchtest
```
Nur wenn die Sicherung **ohne** Schlüssel kam oder ein neues Demokonto benutzt wird:
```bash
.\.venv-bot\Scripts\python.exe -m kit konto-registrieren
```
Falls noch keine PIN gesetzt ist (nur du, interaktiv):
```bash
.\.venv-bot\Scripts\python.exe -m kit pin-setzen
```
Installieren: immer ein `lauf/<ID>`-Tag laut `HANDOFF.md`, für die zertifizierte Mechanik z. B. `lauf/F-05d` (`mechanik_hash` `4fab5281…`). Die `rel/…`-Tags gab es bis F-05e nur auf dem Laptop; sie bleiben Beleg, installiert wird `lauf/<ID>`. Der öffentliche Spiegel ist eine einzelne Momentaufnahme ohne Tags und wird bei jedem Lauf ersetzt. Ihn nie als `RepoUrl` eintragen. Wer ohne das private Repo betreibt, nutzt einen eigenen Fork: `RepoUrl` in `C:\KI-Trading\vps.config.psd1` auf den Fork setzen, dort `lauf/<ID>` taggen und pushen (`docs/ENTWICKLUNG.md` §3), dann diesen Tag installieren.
```bash
powershell -ExecutionPolicy Bypass -File .\deploy\windows-vps\40_bot.ps1 -Tag lauf/F-05d
```

## 5. Autostart (Administrator, nur bei Bot-Betrieb)

**Nur bei Bot-Betrieb, nicht solange das Projekt ruht.** Die Aufgabe „KI-Trading Bot“ startet `bot_dienst.ps1` standardmäßig im Modus `probe` und sendet dann bei jeder Anmeldung von `kitbot` Demo-Orders.
```bash
powershell -ExecutionPolicy Bypass -File $env:SystemDrive\Users\kitbot\ki-trading\deploy\windows-vps\50_aufgaben.ps1
```
Test: VPS neu starten. Nach etwa 3 Minuten sollten MT5 und der Bot laufen.
```bash
powershell -ExecutionPolicy Bypass -File $env:SystemDrive\Users\kitbot\ki-trading\deploy\windows-vps\90_status.ps1
```
Optional einen Herzschlag einrichten: Bei healthchecks.io einen Check mit 15 min Periode und 15 min Gnadenzeit anlegen. Seine Ping-URL als einzige Zeile in `%SystemDrive%\Users\kitbot\KI-Trading-Bot\herzschlag_url.txt` speichern. Bleibt der Ping aus, mailt der Dienst dir.

## 6. Entwicklungsplatz (als `kitdev`)

```bash
powershell -ExecutionPolicy Bypass -File C:\KI-Trading-Setup\60_agent.ps1
```
Das Skript installiert Claude Code, klont das private Repo nach `%USERPROFILE%\ki-trading` (Remote `private`), setzt Hooks und Agent-Identität und legt `.venv-311`, `.venv-312` und `.venv-forschung` an. Fehlt `.venv-forschung`, im Repo-Ordner `powershell -ExecutionPolicy Bypass -File tools\dev.ps1 forschung` ausführen.

**Anmeldungen (nur du, interaktiv, als `kitdev`):**
- Git: beim Klonen im Credential-Manager-Fenster. Fine-grained-Token **nur** für das private Repo und den öffentlichen Spiegel: *Contents: Read and write*, *Workflows: Read and write* (der Spiegel enthält `.github/workflows/ci.yml`, ohne dieses Recht lehnt GitHub den Push ab), *Metadata: Read*, **kein** *Administration*. So kann niemand per Token Sichtbarkeit oder Einstellungen der Repos ändern.
- GitHub CLI (installiert `30_software.ps1`; meldet es nur eine Warnung, das MSI von cli.github.com von Hand installieren): `gh auth login` → *Paste an authentication token* mit **demselben** Fine-grained-Token, **keine** Browser-Anmeldung (die gäbe gh Rechte auf alle Repos, auch für Sichtbarkeit). Prüfen mit `gh auth status` (Token beginnt mit `github_pat_`).
- Sperrliste: vom Offline-Medium nach `%LOCALAPPDATA%\kit\sperrliste.txt` von `kitdev` kopieren (RDP-Laufwerksfreigabe oder `tailscale file cp`), nie ins Repo, nie in die Cloud. Ohne sie bricht `publish.py lauf --oeffentlich` vor dem Commit ab, und der Commit-Scan erkennt private Begriffe nicht. Der Agent darf sie weder lesen noch schreiben.
- Claude: `claude` starten, im Browser anmelden, den Repo-Ordner als vertrauenswürdig bestätigen.

**Kerzenbestand** (nur für neue Forschung, Option C): `entwicklung.sqlite` vom Offline-Medium in die Ablage von **`kitdev`** kopieren, nie zu `kitbot`, nie ins Repo. `kit forschung` läuft als `kitdev`, und die Ablage gilt je Windows-Benutzer. Als `kitdev` in einer eigenen PowerShell (nicht in Claude) den Ordner anlegen und die Datei hineinkopieren:
```bash
New-Item -ItemType Directory -Force $env:USERPROFILE\KI-Trading-Bot\marktdaten
```
Ein Neuabzug ist nicht garantiert bitgleich; die Runden F-04 bis F-05b lassen sich nur mit dem Original nachrechnen.

**Erste Sitzung** – immer im Repo-Ordner, sonst greift der Wächter-Hook nicht:
```bash
cd $env:USERPROFILE\ki-trading; claude
```
Startprüfung: `echo KIT_WAECHTER_PROBE` wird verweigert, `git status` sauber, HEAD = `private/main`, `tools\dev.ps1 alles` grün inklusive Forschungstests, `.venv-311\Scripts\python.exe -m kit forschung pruefen` = VERIFIZIERT, `gh auth status` angemeldet. Erst dann den Prompt aus `NEXT_PROMPT.md` einfügen (Lauf F-05f, Vorlage in `docs/bot/PROMPTS.md`).

**Hinweis:** `kit status` und `kit tor-t` lesen unter `kitdev` nur dessen eigene, leere Ablage. Einen Bot-Stand gibt es nur in `C:\KI-Trading\austausch` (solange das Projekt ruht: kein Bot).

**Nie auf dem VPS:** Claude Code unter `kitbot` oder Administrator; `kitdev` als Administrator oder mit Autologon; unter `kitdev` ein MT5-Terminal, eine Broker-Anmeldung oder `.venv-bot`; Zugangsdaten in `vps.config.psd1`, im Repo oder im Prompt; Live.

## 7. Abnahme

### 7a. Abnahme Entwicklungsplatz

- [ ] `00_vorpruefung.ps1` ohne FEHLER; RDP nur über Tailscale, Port 3389 beim Anbieter zu, 2FA bei Anbieter, GitHub, Tailscale und Claude
- [ ] Kein Autologon, keine Aufgaben „KI-Trading …“, kein MT5
- [ ] Als `kitdev` im Repo-Ordner: `echo KIT_WAECHTER_PROBE` wird verweigert
- [ ] `git status` sauber, HEAD = `private/main`, `git config core.hooksPath` = `.githooks`
- [ ] `tools\dev.ps1 alles` grün inklusive Forschungstests; `kit forschung pruefen` = VERIFIZIERT
- [ ] `gh auth status` angemeldet; `.venv-312\Scripts\python.exe -B tools\publish.py pruefen --oeffentlich` ohne Befund (Sperrliste vorhanden)
- [ ] Windows-Updates installiert (wöchentlich selbst)
- [ ] Laptop: T-DAUER beendet, Sicherung, Kerzenbestand und Sperrliste offline, dort kein Commit mehr

### 7b. Abnahme Bot (nur bei Wiederaufnahme)

- [ ] `00_vorpruefung.ps1` ohne FEHLER, `90_status.ps1`: Aufgaben „Bereit/Wird ausgeführt“, MT5 und Bot laufen
- [ ] `kit status`: `laeuft_vermutlich: true`, keine unerwarteten Sperren, `umzug_offen: 0`
- [ ] `kit tor-t --stand`: 0 Defekte, `mechanik_hash` `4fab5281…` (sonst gilt das Zertifikat nicht, neue Messung nötig)
- [ ] Neustart-Test bestanden (Bot kommt allein wieder)
- [ ] RDP nur über Tailscale, Port 3389 beim Anbieter zu, 2FA überall
- [ ] Sicherung im Ordner `C:\KI-Trading\sicherung` vorhanden; Kopie außer Haus eingerichtet ([BETRIEB.md](BETRIEB.md) §5)
- [ ] Laptop-Bot bleibt gestoppt (zwei Bots auf demselben Demokonto stören sich gegenseitig, der Abgleich meldet dann fremde Positionen)

## 8. Häufige Probleme

| Meldung | Ursache | Lösung |
|---|---|---|
| `Agent-Wächter schützt die Laufzeitablage nicht` bei `installieren` | Bot-Checkout auf einem Stand vor `lauf/F-04` (Wächter-Patch fehlt) | `40_bot.ps1` erneut (holt den aktuellen Stand), Tag ab `lauf/F-04` installieren, z. B. `lauf/F-05d` |
| `ABBRUCH (1): Öffentlicher Spiegel ohne Sperrliste …` | Sperrliste fehlt bei `kitdev` | du kopierst sie nach `%LOCALAPPDATA%\kit\sperrliste.txt` (§6); der Abbruch kommt vor dem Commit, danach `publish.py lauf` erneut |
| `Spiegel: … nicht erreichbar … – Spiegel übersprungen` (Exit 3) nach dem privaten Push | GitHub CLI fehlt oder ist nicht angemeldet | `gh auth login` (fehlt `gh`: `30_software.ps1` als Administrator erneut oder MSI von cli.github.com); privat ist schon veröffentlicht, `lauf` nicht wiederholen, sondern `.venv-312\Scripts\python.exe -B tools\publish.py oeffentlich --lauf <ID>` |
| `MT5 nicht nutzbar: … Authorization` | Terminal nicht angemeldet | im Terminal mit dem Demokonto anmelden |
| `Probe nicht erlaubt: Algo Trading aus` | Knopf „Algo Trading“ aus oder Python-API in den Optionen gesperrt | Knopf an; *Extras → Optionen → Expert Advisors* prüfen |
| `Serverversatz nicht messbar` | Markt geschlossen (Wochenende) oder Kursstrom steht | abwarten; `bot_dienst.ps1` versucht es alle 15 min |
| Bot startet nach Neustart nicht | Autologon fehlt oder Aufgabe deaktiviert | Autologon prüfen; `90_status.ps1`; `%SystemDrive%\Users\kitbot\KI-Trading-Bot\dienst.log` lesen |
| `Altbestand … erst kit umziehen` | alte Ablage mit Daten gefunden | `kit umziehen` (siehe NOTFALL.md) |
| Tor-T `mechanik_hash` anders als erwartet | anderer Tag installiert oder Geldpfad geändert | `lauf/<ID>` mit `4fab5281…` installieren (z. B. `lauf/F-05d`); ein neuer Hash braucht eine neue Tor-T-Messung |
