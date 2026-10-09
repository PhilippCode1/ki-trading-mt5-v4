# Betrieb

> **Stand 09.10.2026: Projekt ruht (Entscheidung ENDE).** Der Bot wird nicht weiterbetrieben: T-DAUER beendet der Betreiber nach F-05e auf dem Laptop (INSTALLATION_VPS.md §0a), danach läuft kein Bot, weder dort noch auf dem VPS. Dieses Dokument gilt erst wieder bei einer Wiederaufnahme des Bots. Für den Entwicklungsplatz auf dem VPS (`kitdev`) gelten nur [INSTALLATION_VPS.md](INSTALLATION_VPS.md) §0a und §6; den Abschluss auf dem Laptop (Bot stoppen, Offline-Sicherung) beschreibt §0a.

Täglicher Betrieb des Demo-Bots auf dem Windows-VPS. Notfälle (Kill-Stufen, Entsperren, Algo-Trading-Knopf): [`bot/NOTFALL.md`](bot/NOTFALL.md). Einrichtung: [INSTALLATION_VPS.md](INSTALLATION_VPS.md).

Alle `kit`-Befehle laufen als Bot-Benutzer `kitbot` im Ordner `%USERPROFILE%\ki-trading` mit `.\.venv-bot\Scripts\python.exe -m kit …`.

## 1. Täglicher Blick (2 Minuten)

1. Herzschlag-Dienst (healthchecks.io bzw. Uptime Kuma): grün?
2. Optional per RDP über Tailscale ein Gesundheitsblick: `powershell -File deploy\windows-vps\90_status.ps1`
3. `kit status`: prüfen auf `laeuft_vermutlich: true`, keine unerwarteten `sperren`/`symbol_sperren`, `stop_datei: 0`, und die letzten Meldungen.
4. Wöchentlich `kit tor-t --stand`: Defekte müssen 0 bleiben. Tor T ist seit 09.10.2026 bestanden (Zertifikat [`berichte/tor_t/2026-10-09.md`](../berichte/tor_t/2026-10-09.md), 378 Sendungen, 100 % fehlerfrei, `mechanik_hash` `4fab5281…`).

## 2. Starten und Stoppen

| Was | Wie |
|---|---|
| Bot läuft automatisch | Aufgabe „KI-Trading Bot“ bei Anmeldung von `kitbot` (Autologon) → `bot_dienst.ps1` |
| Geordnet beenden | `kit stop --beenden` (Positionen behalten Server-SL/TP; die Hülle startet nach Exit 0 nicht neu) |
| Wieder starten | als `kitbot` ab- und anmelden **oder** in der Aufgabenplanung „KI-Trading Bot“ ausführen |
| Sofort keine Einstiege | `kit stop --k1` (vorübergehend) bzw. `--k2` (dauerhaft, PIN zum Aufheben) |
| Alles flach | `kit stop --k3` (alle eigenen Positionen schließen ≤ 60 s + K2) |
| Ohne Konsole | Datei `%USERPROFILE%\KI-Trading-Bot\probe\STOP` mit Inhalt `K1`/`K2`/`K3` anlegen; oder im MT5 den Knopf **Algo Trading** aus |

## 3. Neue Version einspielen

1. Der Agent liefert einen Tag (`lauf/<ID>`) im privaten Repo bzw. im eigenen Fork (nie aus dem Spiegel, der hat keine Tags); HANDOFF nennt ihn und den erwarteten `mechanik_hash`. Auf dem VPS immer einen `lauf/<ID>`-Tag installieren, für die zertifizierte Mechanik z. B. `lauf/F-05d`.
2. Als `kitbot`, falls `aktiver_tag.txt` noch nicht auf dem neuen Tag steht:
```bash
.\.venv-bot\Scripts\python.exe -m kit stop --beenden
```
```bash
powershell -ExecutionPolicy Bypass -File deploy\windows-vps\40_bot.ps1 -Tag lauf/<ID>
```
3. Neu anmelden oder die Aufgabe „KI-Trading Bot“ starten.
4. `kit status` prüfen: der neue START steht im Journal mit dem erwarteten `mechanik_hash`.

Bleibt der `mechanik_hash` gleich (`4fab5281…`), gilt das Tor-T-Zertifikat weiter. Ein neuer Hash (Änderung an den Geldpfad-Dateien) braucht eine neue Tor-T-Messung und ein neues Zertifikat (bewusste Entscheidung).

## 4. Updates und Neustarts (Wartungsfenster Samstag früh)

Der Markt ist samstags geschlossen. Nur dann:
1. Windows Update installieren und neu starten. Automatische Neustarts sind abgeschaltet, Updates werden nur geladen.
2. MT5-Updates einspielen: Das Terminal fragt selbst danach. Bestätigen und das Terminal neu starten.
3. Prüfen, dass Autologon, Aufgaben und Bot nach dem Neustart laufen (`90_status.ps1`). Am Wochenende meldet der Bot „Serverversatz nicht messbar“, weil keine Kurse laufen. Die Hülle versucht es alle 15 min, und mit Marktöffnung (Sonntagabend) läuft er wieder.

Ohne Bot (Projekt ruht) gibt es kein Wartungsfenster. `10_system.ps1` lädt Updates nur herunter; installiere sie deshalb wöchentlich selbst (Einstellungen → Windows Update → Installieren, danach Neustart).

## 5. Sicherung und Wiederherstellung

| Ebene | Wie | Wann |
|---|---|---|
| Lokal | Aufgabe „KI-Trading Sicherung“: `kit sichern` ohne Schlüssel → `C:\KI-Trading\sicherung`, 30 Tage | täglich 23:30 |
| Außer Haus | [restic](https://restic.net) als `kitbot`, Ziel z. B. Backblaze B2 oder Hetzner Storage Box, verschlüsselt. Das restic-Passwort kennt nur der Betreiber (Passwortmanager). | täglich nach der lokalen Sicherung |
| Schlüssel | `kit sichern --ziel <USB/Offline> --mit-schluessel` (nur Betreiber, interaktiv) | einmalig, nach PIN-/Kontowechsel und vor dem Abschalten eines Bot-Rechners |
| Sperrliste | `%LOCALAPPDATA%\kit\sperrliste.txt` des Agent-Benutzers als Kopie offline (USB), nie Cloud, Mail oder Repo. Sie liegt in keiner Sicherung und wird für den Commit-Scan und `publish.py --oeffentlich` gebraucht. | nach jeder Änderung |
| Kerzenbestand | `%USERPROFILE%\KI-Trading-Bot\marktdaten\entwicklung.sqlite` als Kopie offline (USB). Er steckt nicht in `kit sichern`, und ein Neuabzug ist nicht garantiert bitgleich (die Datensicht F-04 bis F-05b hängt an den SHA-256 der Abzüge). | nach jedem neuen Abzug |
| Code | GitHub privat; monatlich `git bundle create ki-trading.bundle --all` offline | monatlich |

restic einrichten (Betreiber, einmalig; Beispiel Backblaze B2):
```bash
restic -r b2:<bucket>:ki-trading init
```
Danach eine zusätzliche Aufgabe nach dem Muster in `50_aufgaben.ps1`, die `restic backup C:\KI-Trading\sicherung` ausführt. Zugangsdaten für B2 legst du als Umgebungsvariablen des Benutzers `kitbot` an. Sie gehören nie ins Repo.

**Wiederherstellen** (neuer Rechner oder Datenverlust): Den Bot stoppen. Dann im Repo-Ordner als `kitbot`:
```bash
.\.venv-bot\Scripts\python.exe -m kit wiederherstellen --aus <kit-sicherung-….zip>
```
Danach gilt:
- Der Befehl überschreibt nie.
- Hat die Ablage schon eigene Daten, übernimmt er nur die Sperren.
- Fehlte der Schlüssel in der Sicherung, das Konto neu registrieren: `kit konto-registrieren`.

Probe alle 3 Monate: [WARTUNG.md](WARTUNG.md) §3.

## 6. Überwachung

| Signal | Quelle | Reaktion |
|---|---|---|
| Herzschlag bleibt aus | Status-Aufgabe pingt nur, wenn der Bot-Prozess läuft **und** das Journal „läuft“ meldet | RDP → `90_status.ps1`, `dienst.log`, `MELDUNGEN.txt` |
| `ALARM` in `MELDUNGEN.txt` | Bot | Ursache lesen, bei Sperre: Ursachenakte, erst dann mit PIN entsperren |
| Sperre `NULLTOLERANZ`, `STOP_OUT`, `NICHT_DEMO` | Bot | nicht einfach entsperren – Journal prüfen (Agent kann `kit status`/Export auswerten) |
| `TECHNIK_PAUSE` | ≥ 3 Ablehnungen in 20 Sendungen | hebt sich nach 30 min selbst auf; Häufung → Ursache suchen |
| `dienst.log`: „mehr als 10 Fehler-Neustarts“ | Hülle | Programmfehler; `konsole.log` an den Agenten |

## 7. Was der Agent darf

- **Er darf:** Code ändern, testen und veröffentlichen, `kit status`, `tor-t`, `trockenlauf`, Exporte und den Austauschordner lesen, (nur auf einem Einzelrechner wie dem Laptop) mit Freigabe im Laufprompt Demo-Probeläufe beaufsichtigen.
- **Er darf nie:** entsperren, eine PIN setzen, Live schalten, sich anmelden, Zugangsdaten eingeben, Geld bewegen, `kit sichern`, Dateien der Bot-Ablage lesen oder ändern.

Auf dem VPS setzt das zusätzlich die Benutzertrennung `kitdev`/`kitbot` durch. Dort gilt:
- `kit status` und `kit tor-t` zeigen unter `kitdev` nur die eigene, leere Ablage von `kitdev`, keinen Bot-Stand.
- Den Bot-Stand liest der Agent nur aus `C:\KI-Trading\austausch` (`status_<modus>.txt`, `tor_t_<modus>.txt`). Solange das Projekt ruht, läuft dort kein Bot, es gibt also keinen Stand.
- Demo-Probeläufe auf dem VPS (Sitzung von `kitbot`) beaufsichtigt nur der Betreiber.
