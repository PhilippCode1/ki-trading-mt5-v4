# Entscheidungen des Betreibers (Plan F-1)

Maßgeblich für alle Läufe ab F-00. Änderungen trägt **nur der Betreiber** ein (neue Zeile im Abschnitt „Änderungen“ mit Datum); jede Änderung an Strategie-, Tor- oder Risikowerten nach einer Datensicht zählt als neuer Versuch.

## Verbindliche Entscheidungen (04.10.2026)

| # | Thema | Entscheidung |
|---|---|---|
| D1 | Richtung | Schlanker Fast-Track; Konzeptphase per Tags `konzept-c11-gruen` / `konzept-c12-wip` eingefroren |
| D2 | GitHub | Nach jedem Lauf säubern → privat pushen (volle Historie) → bereinigten öffentlichen Spiegel `PhilippCode1/ki-trading-mt5-v4` aktualisieren |
| D3 | Trefferquote | ≥ 85 % Gewinntrades im Trade-Test (≥ 200 Trades außerhalb der Anpassung + einmaliger Holdout) → Demo-Live, danach keine Prompts mehr · ≥ 95 % im Demo-Live (≥ 100 Trades, ≥ 3 Monate) → Echtgeld-Freigabe möglich (nur Betreiber) · rollierend ≤ 50 % (letzte 50, ab 20 Trades) → Stopp, eigene Positionen schließen, Aufheben nur Betreiber |
| D4 | Parallel-Schutz | Erwartungswert/Trade nach Kosten > 0 (95-%-Untergrenze), Gewinnfaktor ≥ 1,2, Pflicht-SL und Pflicht-TP auf dem Server, Stop ≤ 3× Ziel (geplant und realisiert), kein Martingale/Grid/Nachkaufen, Tagesverlust-Stopp 3 %, Trefferquote über der Zufallsbasis mit identischer Ausstiegslogik |
| D5 | Risikowerte (versiegelt) | Hebelband 5–15 (Strategiebuch-Korridor 5,25–14,25 mit Prüfpunkten), LOSS_LOCK bei 25 % Verlust |
| D6 | Freigaben | Solo-Betreiber; eigene SL/TP-Ausführungen = normaler Ausstieg |
| D7 | Demo | Vorhandenes MT5 + Demokonto; der Agent darf den Bot auf DEMO starten/stoppen und fragt nur bei nötigen Einstellungen |
| D8 | Projektgrenze | Systeme außerhalb dieses Projekts gehören weder in den Bot noch in den Spiegel; Betreiberaufgaben dazu: privat |
| D9 | Technik-QA | Tor T (≥ 95 % technisch fehlerfrei, Null-Toleranz) ist Sicherheitsvoraussetzung |

## Plan-Vorgaben (gelten, bis der Betreiber sie ändert)

| Nr | Vorgabe | Wert | Bestätigung |
|---|---|---|---|
| V1 | Stop-zu-Ziel-Verhältnis höchstens | 3 (geplant und realisiert) | gilt mit D4 |
| V2 | Zusatzkriterien 85-%-Tor (DSR ≥ 0,95, ≥ 3/4 Teilperioden positiv, Gewinnfaktor bei Kosten ×1,5 > 1,0) | nur berichten, bis bestätigt | `ZUSATZKRITERIEN-OK` im Prompt F-04 |
| V3 | Zusatzkriterien 95-%-Tor (Signaltreue ≥ 95 %, Ist-Kosten ≤ 1,25× Modell) | nur berichten, bis bestätigt | `ZUSATZKRITERIEN-95-OK` im Prompt F-07 |
| V4 | Probe-Positionen von der Band-Untergrenze ausgenommen | ja (05.10.2026, siehe Änderungen) | entschieden |
| V5 | Höchstens eine offene Strategieposition | ja | gilt (einfachste Umsetzung des Bands) |
| V6 | Entwicklungsperiode / Holdout | 01.01.2010 (oder frühester Balken) – 30.06.2021 / 01.07.2021 – 30.06.2026 | gilt |
| V7 | Symbole | 7 FX-Paare aus `registers/symbols.json` (EURUSD, USDJPY, GBPUSD, CHFJPY, CADJPY, AUDUSD, NZDUSD); Aktienindizes nach BQ-06a ausgeschlossen | gilt |
| V8 | Demokonto | Hedging, EUR, Guthaben ≈ geplantes Echtgeld, Hebel ≥ 1:30, möglichst unbefristet | Angaben im Prompt F-02 |
| V9 | Forschungsrunden ohne Kandidat | höchstens 3, dann entscheidet der Betreiber | gilt; nach drei Runden am 09.10.2026 entschieden: **A** (siehe Änderungen) |
| V10 | Laufzeit-Python Bot | 3.11 (MetaTrader5-Wheel 5.0.6090 cp311 erprobt) | gilt |

## Änderungen

| Datum | Nr | neu | Grund |
|---|---|---|---|
| 05.10.2026 | Delegation | Der Betreiber hat dem Agenten alle offenen Plan-Entscheidungen nach dessen Empfehlung übertragen („entscheide du für mich alles“). Ausgenommen bleiben die harten Grenzen aus `CLAUDE.md` (Live, Entsperren, PIN, Wächter, Zugangsdaten, Geld) | Anweisung des Betreibers im Chat |
| 05.10.2026 | V4 | **ja**: Probe-Positionen (nur `volume_min`, Namensraum PROBE, reine Technik-Messung) sind von der Band-**Untergrenze** ausgenommen – nicht von Obergrenze, Demo-Wächter, Pflicht-SL/TP, Tagesbudget | Agent nach Delegation: mit `volume_min` ist Buchhebel ≥ 5,25 unerreichbar; ohne Ausnahme gäbe es keine Technik-Messung (Tor T) |
| 05.10.2026 | V2/V3 | bleiben „nur berichten“ | Agent nach Delegation: Plan-Vorgabe beibehalten, keine zusätzliche Datensicht nötig |
| 05.10.2026 | Terminal | Das vorhandene MT5-Terminal des Laptops wird verwendet (kein eigenes portables Demo-Terminal). Schutz: DEMO-Prüfung vor jeder Sendung und Gegenprobe danach, HMAC-Allowlist, Hedging-Pflicht, Algo-Trading-Prüfung, ein schreibender Bot je Windows-Benutzer; ist `terminal.pfad` gesetzt, wird zusätzlich der verbundene Terminalpfad geprüft | Betreiber in D7 („verwende diese gerne“); Agent nach Delegation |
| 05.10.2026 | PREREG F-04 | **ja** für `docs/bot/prereg/F04_ENTWURF.md`, SHA-256 `621351dc9f16916806f19423a3067391350dd013bcb7f983216826c504c9250a` (12 gezählte Versuche Ziel/Stop + 1 Referenz). Zusatzkriterien des 85-%-Tors bleiben „nur berichten“ (V2) | Agent nach Delegation. Die Tabelle wurde vor jeder Datensicht festgelegt; die Daten wurden bisher nur gezählt, nie ausgewertet |
| 05.10.2026 | Ablage | Laufzeitablage von `%LOCALAPPDATA%\kit` nach `%USERPROFILE%\KI-Trading-Bot`; Altbestand per `kit umziehen` kopiert, nichts gelöscht | Windows leitet `%LOCALAPPDATA%`-Schreibzugriffe aus paketierten Apps (Claude-Desktop) in einen Paket-Cache um. STOP-Datei, `kit stop`, Status und PIN aus der Konsole des Betreibers hätten den Bot sonst nicht erreicht. Agent nach Delegation |
| 06.10.2026 | Betrieb | **Windows-VPS** statt Laptop. Getrennte Windows-Benutzer `kitbot` (Bot + MT5-Demo, Autologon) und `kitdev` (Claude Code); portables Demo-Terminal `C:\KI-Trading\mt5-demo`, Pfad rechnerspezifisch in `lokal.toml`; Autostart über Aufgabenplanung ohne gespeichertes Passwort; RDP nur über Tailscale; tägliche Sicherung + Herzschlag. Zusatzdienste (Monitoring, Agentendienste) außerhalb des Geldpfads, bevorzugt auf einem Linux-Begleiter | Betreiber: „klarer Schnitt … auf einem Windows-VPS neu und sauber aufsetzen“; Ausgestaltung durch den Agenten nach Delegation (`docs/INSTALLATION_VPS.md`) |
| 06.10.2026 | Repo | **Neuordnung**: Konzeptphase (838 Dateien) aus dem Arbeitsbaum entfernt (vollständig in den Tags `konzept-c11-gruen`/`konzept-c12-wip`); eingefrorene Referenz geschlossen nach `referenz/` (nur Orakel für Tests); vollständige Doku unter `docs/`; öffentlicher Spiegel ohne Betriebsdetails | Betreiber: vollständiger Clean-up; Agent nach Delegation |
| 06.10.2026 | D8 (Wortlaut) | neutral formuliert, Inhalt unverändert; Einzelheiten nur in `docs/bot/privat/` | Agent nach Delegation: Der Betreiber will das Projekt öffentlich weitergeben (Lauf F-03g) |
| 08.10.2026 | Kosten F-04 (Auslegung Prereg §1) | Hauptprofil = Kommission laut erstem Demo-Trade (**0** je Lot und Seite); **Gegenprobe 3,25** (Startwert cost_truth) als eigener Lauf je Variante; Spread je Kerze aus den Daten; Swap aus den Startwerten des Kostenregisters (der Rauchtest hat keine Swaps erfasst), Dreifachtag Mittwoch; „Kosten × 1,5“ auf das Hauptprofil (Spread, Swap-Belastungen). Die Größe rechnet der Takt wie im Betrieb mit 3,25 (`config/kit_demo.toml`) | Laufprompt F-04 („Kommission laut erstem Demo-Trade (0) mit Gegenprobe Startwert cost_truth“); vor der Datensicht im Versuchsprotokoll (`kosten_auslegung`) festgehalten |
| 08.10.2026 | Zeitbasis der Kerzen | Die Abzüge (F-02) stehen in **Serverzeit**; der Server folgt der New-Yorker Sommerzeit (UTC+3/UTC+2). Die Forschung rechnet beim Lesen mit dem festen Versatz +3 h aus `config/trade_test.toml` um; im Winter liegt das Handelsfenster dadurch 1 h später. Künftige Abzüge bleiben in Serverzeit (`ziehen` verweigert ein Terminal mit gemessenem Versatz) | Agent nach Delegation: Befund bei der ersten Datensicht (nur Zeitstempel, vor jeder Ergebnissicht), Werkzeugänderung W1 im Versuchsprotokoll |
| 09.10.2026 | PREREG F-05b | **ja** für `docs/bot/prereg/F05B_ENTWURF.md`, SHA-256 `b1ec2a2ee252f51de86963057ef553e4727e7b10bf96828c30a56498acbd08e9` (Runde 3, die letzte nach V9: Richtungsmodell auf handelbaren Zeitpunkten, je Richtung ein Modell zu denselben Abständen, 4 gezählte Versuche, Familie F05B-RICHTUNG) | Agent nach Delegation, nach F-05 (kein Kandidat: der Filter fand Marktphasen, aber keine Richtung) und vor jeder Datensicht der Runde 3; der Betreiber kann im Prompt F-05b „nein“ setzen und sofort nach V9 entscheiden |
| 08.10.2026 | PREREG F-05 | **ja** für `docs/bot/prereg/F05_ENTWURF.md`, SHA-256 `88bdd6cc9398320b2e9619544f35c81caa82dfd344df78a55bc8ae1e0d983ffb` (Meta-Filter, Basis S-REV-01-k2.0-z0.75-r3 und S-REV-02-L40-z0.5, 2 Modelle → 4 gezählte Versuche, Familie F05-META) | Agent nach Delegation, nach F-04 und vor jeder Datensicht der Runde 2; der Betreiber kann im Prompt F-05 „nein“ setzen |
| 09.10.2026 | V9 | **A – Pause der Strategieforschung.** Keine weitere Forschungsrunde; der Holdout bleibt ungezogen. T-DAUER läuft weiter bis zu den Mindestzahlen von Tor T, danach Tor-T-Auswertung und Zertifikat (Lauf F-05d). Danach entscheidet der Betreiber erneut: B, C oder Ende | Betreiber im Laufprompt F-05c (Antwort „A“ im Chat), Grundlage `docs/bot/ENTSCHEIDUNG_V9.md` nach drei Runden ohne Kandidat |
| 09.10.2026 | Tor T / NACH-TOR-T | **Tor T bestanden** (378 Sendungen, 100 % fehlerfrei, 0 Defekte), Zertifikat `berichte/tor_t/2026-10-09.md`. Die Zeile NACH-TOR-T im Prompt F-05d war leer = **offen**: keine Vorregistrierung, nur Entscheidungsvorlage `docs/bot/ENTSCHEIDUNG_NACH_T.md` (Empfehlung des Agenten: Ende) | Lauf F-05d nach Regel des Prompts („nicht ausgefüllt = offen“) |
| 09.10.2026 | NACH-TOR-T | **ENDE – das Projekt ruht.** Keine Forschung, kein Demo-Live, kein Bot-Betrieb, keine Geldpfad-Änderung; T-DAUER beendet der Betreiber. Zertifikat, Code, Berichte und Versuchsprotokoll bleiben erhalten, der Holdout ist ungezogen. **Weiterarbeit auf dem Windows-VPS** (Benutzer `kitdev`, Weg „nur Entwicklung“ in `docs/INSTALLATION_VPS.md`); Wiederaufnahme nur mit Zielzeile im Laufprompt (Vorlage F-05f in `docs/bot/PROMPTS.md`). Veröffentlichung weiter privat und über den bestehenden öffentlichen Spiegel; Sichtbarkeit und Einstellungen der Repos unverändert | Betreiber im Chat zu Lauf F-05e („Ende. Für VPS vorbereiten … öffentlich pushen“) |
