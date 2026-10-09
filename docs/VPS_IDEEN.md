# Ideen für den Windows-VPS – bewertet und priorisiert

> **Eingeschränkt durch ENDE (09.10.2026): Das Projekt ruht; der Bot wird nicht weiterbetrieben** (T-DAUER beendet der Betreiber, [INSTALLATION_VPS.md](INSTALLATION_VPS.md) §0a). Für den Entwicklungsplatz (`kitdev`) zählen jetzt nur die Punkte, die [INSTALLATION_VPS.md](INSTALLATION_VPS.md) §1–§3 (mit `30_software.ps1 -OhneMt5`, ohne Autologon) und §6 umsetzen: Plattform und Zugang, Systemeinstellungen aus `10_system.ps1`, §6 Entwicklung und Agent, §8 Sicherheit. Alles zum Bot-Betrieb (Autologon, MT5, Aufgaben, Herzschlag, Status-Export, Sicherung der Bot-Ablage, restic, Zusatzdienste) erst bei einer Wiederaufnahme des Bots.

Stand 06.10.2026. **Muss** = vor dem Dauerbetrieb, **Soll** = in den ersten Wochen, **Kann** = sobald es sich lohnt. „Umgesetzt“ heißt: im Repo vorbereitet (Skript oder Doku) – eingerichtet wird es auf dem VPS durch dich mit `deploy/windows-vps/`.

Leitlinie: **Der Geldpfad bleibt klein und lokal** (Bot + MT5-Terminal + Dateien auf einem Windows-Rechner). Alles Weitere sitzt *daneben*, sieht nur redigierte Exporte und kann ausfallen, ohne dass der Bot falsch handelt.

## 1. Plattform und Zugang

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Windows Server 2022/2025, 4 vCPU, 8–16 GB RAM, ≥ 80 GB SSD**, Rechenzentrum in Europa (London, Frankfurt oder Amsterdam, nah an den MT5-Servern der meisten EU-Broker) | MT5 und das `MetaTrader5`-Python-Paket laufen nur unter Windows; kurze Wege zum Handelsserver | Anforderungen in `docs/INSTALLATION_VPS.md` |
| Muss | **Getrennte Windows-Benutzer** `kitbot` (Bot und MT5), `kitdev` (Claude Code), Administrator nur zur Einrichtung | Echte Trennung über NTFS-Rechte statt nur Regeln: der Agent kann die Bot-Ablage technisch nicht lesen oder ändern | `20_benutzer.ps1` |
| Muss | **Autologon für `kitbot`** (Sysinternals Autologon, Passwort verschlüsselt als LSA-Secret) | MT5 ist eine GUI-Anwendung und braucht eine angemeldete Desktop-Sitzung, auch nach einem Neustart | Anleitung |
| Muss | **Tailscale (WireGuard)** und RDP nur aus dem Tailnet, Port 3389 zusätzlich in der Anbieter-Firewall zu | Kein offenes RDP im Internet (häufigster Einbruchsweg bei Windows-VPS) | `30_software.ps1`, `10_system.ps1 -RdpNurTailscale` |
| Muss | **Zwei-Faktor** beim VPS-Anbieter, bei GitHub, Tailscale, Anthropic und dem Broker | Konto-Übernahme ist schlimmer als jeder Serverfehler | Betreiber |
| Soll | **Live später auf einem eigenen VPS** (oder mindestens eigener Benutzer `kitlive` ohne Agent) | Plan §6.2: Live technisch getrennt, nie eine Agentensitzung neben Live | Doku `SICHERHEIT.md` |
| Kann | Anbieter-Snapshots vor jedem größeren Update | Schneller Rückweg bei kaputtem Update | Betreiber |

## 2. Betrieb und Stabilität

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Aufgabenplanung statt Dienst**: Bot startet bei Anmeldung von `kitbot`, Hülle mit Neustart-Pause (1 → 15 min, höchstens 10 Neustarts in 6 h) | Übersteht Abstürze und Neustarts ohne gespeichertes Passwort; nach jedem Start gleicht der Bot zuerst mit dem Broker ab | `50_aufgaben.ps1`, `bot_dienst.ps1` |
| Muss | **Windows Update ohne Zwangsneustart**, Installation und Neustart im Wartungsfenster Samstag früh (Markt zu) | Kein Neustart mitten in einer offenen Position | `10_system.ps1`, `BETRIEB.md`; ohne Bot installierst du die Updates wöchentlich selbst |
| Muss | **Zeit über NTP** (w32time mit festen Quellen) | Der Bot misst den Serverversatz selbst, braucht aber eine stabile PC-Uhr für Fristen und Journale | `10_system.ps1` |
| Muss | **Energie: nie Standby/Ruhezustand** | Selbsterklärend – auf dem Laptop war das ein Risiko | `10_system.ps1` |
| Soll | **Portables MT5-Terminal** in `C:\KI-Trading\mt5-demo` mit `/portable` und `terminal.pfad` in `config/kit_demo.toml` | Der Bot prüft dann zusätzlich den Terminalpfad; Live-Terminal kann nie versehentlich verbunden sein | `40_bot.ps1`, `KONFIGURATION.md` |
| Soll | MT5-Option „Algo-Trading bei Kontowechsel deaktivieren“ an, „Max. Balken: Unbegrenzt“ | Schutz bei Kontowechsel; vollständige Historie | Anleitung |
| Kann | Zweites Demokonto/zweites Terminal für Forschung (Datenabzug) getrennt vom Messbetrieb | Datenabzüge stören die Technik-Messung nicht | Idee |

## 3. Überwachung und Meldungen

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Herzschlag-Ping** alle 15 min an healthchecks.io (kostenlos) oder Uptime Kuma „Push“ – bleibt er aus, kommt eine Mail/Push | Du erfährst von einem stehenden Bot, ohne auf den VPS zu schauen | `status_export.ps1` (URL in `herzschlag_url.txt`) |
| Muss | **Status-Export** alle 15 min in `C:\KI-Trading\austausch` (redigiert) | Agent und Monitoring lesen nur dort, nie in der Bot-Ablage | `status_export.ps1` |
| Soll | **Meldungen aufs Handy**: kleiner Weiterleiter liest `MELDUNGEN.txt` und schickt WARNUNG/ALARM per ntfy oder Telegram | Windows-Benachrichtigungen sieht auf einem VPS niemand | Vorschlag (außerhalb der Mechanik, Token im Windows-Anmeldeinformationsspeicher) |
| Soll | **Tagesbericht** 22:30: Tor-T-Stand, Sperren, Positionen (redigiert) als Nachricht | Täglicher Blick ohne RDP | Vorschlag |
| Kann | Uptime Kuma oder Grafana + `windows_exporter` (CPU, RAM, Platz, Prozess läuft) | Dashboards und Verlauf | nur mit Docker oder Linux-Begleiter |
| Kann | Statusseite 127.0.0.1 (Plan F-07) über Tailscale Serve aufrufbar | Status im Browser, Kill-Knöpfe | Idee; F-07 (Demo-Live) findet vorerst nicht statt |

## 4. Sicherung und Wiederherstellung

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Tägliche Sicherung** (`kit sichern` ohne Schlüssel) mit 30 Tagen Aufbewahrung | Journale sind die Wahrheit des Bots (Sperren, Anker, Tor T) | `sicherung.ps1` |
| Muss | **Kopie außer Haus**, verschlüsselt: restic auf Backblaze B2 / Hetzner Storage Box / S3 | Ein Defekt oder eine Kündigung des VPS darf die Historie nicht kosten | Anleitung `BETRIEB.md` |
| Muss | **Schlüsselsicherung** einmalig und nach Änderungen: `kit sichern --mit-schluessel` (nur Betreiber) offline ablegen | HMAC-Schlüssel und Allowlist lassen sich nicht wiederherstellen | Betreiber |
| Soll | **Wiederherstellungsprobe** alle 3 Monate (Sicherung auf Testordner, `kit umziehen --von`) | Eine Sicherung ohne Probe ist eine Hoffnung | `WARTUNG.md` |
| Soll | Git als zweite Sicherung des Codes (privat + Spiegel) und `git bundle` monatlich | Unabhängig von GitHub | vorhanden / `WARTUNG.md` |

## 5. Daten und Datenbanken

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Beim Bewährten bleiben**: Journal als JSONL mit Hashkette, Zustand als JSON, Kerzen in SQLite | Kein Datenbankserver im Geldpfad – nichts, was ausfallen, falsch konfiguriert oder angegriffen werden kann | Bestand |
| Soll | **DuckDB + Parquet** für Forschung/Backtests (liest SQLite direkt) | Schnelle Auswertung großer Kerzenmengen ohne Server | nicht umgesetzt (F-04 bis F-05b kamen mit SQLite aus); bei neuer Forschung erneut prüfen |
| Kann | **PostgreSQL/TimescaleDB** als Auswertungs-Spiegel (Journale nachgelagert importiert), nur lesend für Dashboards | Wenn Grafana-Dashboards oder mehrere Rechner nötig werden | nur mit Docker/Linux |
| Kann | Tick-Daten-Archiv (komprimierte Parquet je Monat) | Bessere Kostenmodelle (Spread je Uhrzeit) | Idee |

## 6. Entwicklung und Agent

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Claude Code unter `kitdev`**, Sitzungen immer in der Repo-Wurzel `%USERPROFILE%\ki-trading` (Wächter-Hook aktiv); nie unter `kitbot` oder Administrator | Hook + Rechtetrennung = doppelte Sicherung | `60_agent.ps1`; Wächter-Patch erledigt (seit F-04 im Repo) |
| Muss | **Sperrliste und GitHub CLI für `kitdev`**: du kopierst die Sperrliste offline nach `%LOCALAPPDATA%\kit\sperrliste.txt` von `kitdev` (RDP-Laufwerk oder `tailscale file cp`, nie Repo oder Cloud; der Agent darf sie weder lesen noch schreiben) und meldest `gh auth login` mit demselben Token an (*Paste an authentication token*, keine Browser-Anmeldung). Git-Anmeldung mit fine-grained Token nur für das private Repo und den Spiegel (Contents und Workflows lesen/schreiben, Metadata lesen, keine Administration) | `publish.py` braucht beides für Commit-Scan und öffentlichen Spiegel | `30_software.ps1` (gh), `INSTALLATION_VPS.md` §6 |
| Muss | **Ablauf Code → Bot**: Agent pusht und taggt → `kitbot` holt per `40_bot.ps1 -Tag` → Aufgabe neu starten | Bot läuft nur aus geprüften, unveränderlichen Installationen | `BETRIEB.md` |
| Soll | GitHub: Secret Scanning, Push-Schutz, Tag-Schutz-Regeln für `lauf/*`, `rel/*` und `konzept-*` | Schützt Historie und verhindert Geheimnis-Leaks | Betreiber (GitHub-Einstellungen) |
| Soll | Fine-grained Token **nur Lesen** für den Bot-Checkout | Ein kompromittierter Bot-Benutzer kann nichts pushen | Anleitung |
| Kann | Selbst gehosteter GitHub-Runner unter einem eigenen Benutzer für Windows-Tests mit echtem `MetaTrader5`-Paket (ohne Handel) | Adapter-Tests auf echter Windows-Plattform | Idee |
| Kann | `uv` statt `pip` für schnellere, reproduzierbare Umgebungen | Schneller; Lockfiles bleiben hash-gesperrt | vorbereitet (Lockfiles sind uv-kompatibel) |

## 7. Container und Zusatzdienste

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | **Vor dem Kauf klären: verschachtelte Virtualisierung** (sonst kein WSL2/Docker Desktop auf dem VPS) | Viele Windows-VPS können das nicht | `00_vorpruefung.ps1` meldet es |
| Soll | **Linux-Begleiter statt Docker auf Windows**: kleiner Linux-VPS (2 vCPU, 4 GB) im selben Tailnet für alle Container (Monitoring, Datenbank, Agenten-Dienste) | Docker läuft dort nativ und stabil; der Windows-VPS bleibt schlank und nur für MT5/Bot | Empfehlung |
| Kann | Docker Desktop auf dem Windows-VPS (mit WSL2) | Alles auf einem Rechner – mehr Last und Angriffsfläche neben dem Geldpfad | `30_software.ps1 -Docker` |
| Kann | Reverse Proxy (Caddy) mit automatischem TLS nur im Tailnet | Weboberflächen sauber erreichbar, nie offen im Internet | Idee |

## 8. Sicherheit (zusätzlich)

| Prio | Idee | Nutzen | Status |
|---|---|---|---|
| Muss | Defender an, Firewall „eingehend blockieren“, keine Browser-Nutzung auf dem VPS außer für Anmeldungen | Kleine Angriffsfläche | `10_system.ps1` |
| Muss | Kein MT5-KI/MCP-Server (Ports 22345/22346), kein globales `MetaTrader5` in Python | Plan §3; `kit pruefen` meldet beides als FEHLER | `kit pruefen` |
| Soll | Kontosperrung nach Fehlversuchen (Lokale Sicherheitsrichtlinie), RDP mit NLA | Erschwert Passwort-Raten | Anleitung |
| Soll | Geheimnisse (Ping-URL, Push-Token) im Windows-Anmeldeinformationsspeicher bzw. DPAPI statt Klartext | Weniger Klartext auf der Platte | Vorschlag |
| Kann | BitLocker, falls der Anbieter ein virtuelles TPM bietet | Schutz bei Datenträger-Diebstahl beim Anbieter | Anbieter abhängig |

## 9. Was ausdrücklich **nicht** empfohlen wird

- Den Bot in Docker oder als Windows-Dienst in Sitzung 0 laufen lassen – MT5 braucht eine Desktop-Sitzung.
- Eine Datenbank oder Cloud-API in den Geldpfad hängen – jede zusätzliche Abhängigkeit ist eine Fehlerquelle beim Senden.
- Ein Sprachmodell Handelsentscheidungen treffen lassen – im Geldpfad entscheidet deterministischer Code (Plan §4).
- Andere Agenten- oder Automationsdienste mit Zugriff auf Bot-Ablage, Terminal oder Zugangsdaten auf demselben Benutzer betreiben.
