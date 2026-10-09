# Plan F-1: KI-Trading MT5 – vom Konzept zum laufenden Demo-Bot (Fast-Track)

Stand 04.10.2026 (Sonntag) · gilt für den v4-Ordner `KI_Trading_MT5_v4` · ersetzt die Konzeptregeln (P4-1/P5-1 bleiben als Archiv lesbar)

> **Stand 09.10.2026 (Lauf F-05e): Projekt ruht.** Abweichungen vom ursprünglichen Plan:
> - Umgesetzt bis F-03b: Bot komplett, erster Demo-Trade, T-PROBE, T-DAUER läuft.
> - Laufzeitablage `%USERPROFILE%\KI-Trading-Bot` statt `%LOCALAPPDATA%\kit`, weil paketierte Apps umgeleitet werden.
> - Betrieb künftig auf einem Windows-VPS ([`INSTALLATION_VPS.md`](INSTALLATION_VPS.md)).
> - Konzeptphase aus dem Arbeitsbaum entfernt, die Referenz liegt unter `referenz/`.
> - Der Zeitplan in §8 ist überholt: F-03b lief am 05.10.
> - F-04 (08.10.2026): Backtester und Trade-Test gebaut; Runde 1 ohne Kandidat (keine Variante besser als Zufall), Bericht `berichte/forschung/2026-10-08_entwicklung.md`. Die Kerzen der Entwicklungsdaten stehen in Serverzeit (Umrechnung beim Lesen).
> - F-05 (09.10.2026): KI-Meta-Filter (scikit-learn offline, im Bot nur JSON-Parameter mit Standardbibliothek); Runde 2 ohne Kandidat (Filter wählt Marktphasen, keine Richtung), Bericht `berichte/forschung/2026-10-09_runde2.md`. Runde 3 (F-05b, Richtungsmodell) vorregistriert; danach Entscheidung nach V9.
> - F-05b (09.10.2026): Richtungsmodell (Kauf gegen Verkauf zu denselben Abständen, nur handelbare Punkte); Runde 3 ohne Kandidat, Richtungsvorsprung praktisch null, Bericht `berichte/forschung/2026-10-09_runde3.md`. Drei Runden ohne Kandidat: Entscheidung des Betreibers nach V9 (`docs/bot/ENTSCHEIDUNG_V9.md`, Lauf F-05c).
> - F-05c (09.10.2026): Betreiber entscheidet nach V9 **A – Pause der Strategieforschung**. F-06 (Holdout) und F-07 (Demo-Live-Start) entfallen vorerst; T-DAUER läuft bis zu den Mindestzahlen von Tor T, danach Tor-T-Zertifikat (Lauf F-05d) und neue Entscheidung (B / C / Ende).
> - F-05d (09.10.2026): **Tor T bestanden** (378 Sendungen, 100 % fehlerfrei, 0 Defekte), Zertifikat `berichte/tor_t/2026-10-09.md` an `mechanik_hash` `4fab5281…` gebunden (`kit tor-t --stand --zertifikat`). Entscheidungsvorlage `docs/bot/ENTSCHEIDUNG_NACH_T.md` (Empfehlung: Ende); Lauf F-05e setzt die Entscheidung um.
> - F-05e (09.10.2026): Der Betreiber entscheidet **ENDE – das Projekt ruht.** F-06 (Holdout) und F-07 (Demo-Live) entfallen; T-DAUER beendet der Betreiber. Weiterentwicklung auf dem Windows-VPS (Benutzer `kitdev`, `docs/INSTALLATION_VPS.md` §0a/§6). Wiederaufnahme nur über die Vorlage F-05f in `docs/bot/PROMPTS.md` mit Zielzeile (B, C, Bot auf dem VPS, Technik oder anderes); Lauf-IDs im Hook-Format (`F-05f` …).
> - Aktuelle Doku: [`docs/README.md`](README.md).

## 1. Kontext – warum dieser Plan

- **Ist:** 12 Konzeptläufe (C-01…C-12) haben ein hochwertiges Referenzmodell erzeugt (~111.000 Zeilen, ~10.800 Tests, Register, Tore, Rechts-/Betriebsdoku) – aber **0 Zeilen Handelscode**, kein Demo-Trade. Ein Gesamtlauf dauert 5–8 h; C-12 hängt bei „Validator ERROR, 68 rote Tests“. Die eigene Wirtschaftsrechnung sagt „kein belegter Vorteil“.
- **Gefunden:** Dein älteres Repo `mt5-trading-ai` hat einen **echten MT5-Adapter**, der am 17./18.08.2026 auf Demo lief (Schwächen dokumentiert). v4 hat erstklassige **Strategie-/Statistik-Bausteine mit Orakeln** (BL-TFD1, Signale, DSR/PSR/Bootstrap/Wilson, Kausalitätstest). v3 hat Verlustleitern, MT5-Ausführungsregeln und Killer-Tests.
- **Ziel:** Diese Teile zu einem **schlanken, sicheren Bot** (`kit/`) zusammensetzen, auf deinem **Demokonto** betreiben, über klare **Freigabetore** zum **Demo-Live-Betrieb** führen (danach enden die Prompts) und eine spätere Echtgeld-Entscheidung vorbereiten, die **nur du** triffst. Nach **jedem** Lauf: säubern, prüfen, hochladen (privat + bereinigter öffentlicher Spiegel).

## 2. Deine Entscheidungen (04.10.2026, verbindlich)

| # | Thema | Entscheidung |
|---|---|---|
| D1 | Richtung | Schlanker Fast-Track; Konzeptphase per Tags eingefroren |
| D2 | GitHub | Nach jedem Lauf säubern → privat pushen (volle Historie) → bereinigten öffentlichen Spiegel `PhilippCode1/ki-trading-mt5-v4` aktualisieren |
| D3 | Trefferquote | **≥ 85 %** Gewinntrades im Trade-Test (echte MT5-Historie, ≥ 200 Trades außerhalb der Anpassung + einmaliger Holdout) → **Demo-Live**, danach keine Prompts mehr · **≥ 95 %** im Demo-Live (≥ 100 Trades, ≥ 3 Monate) → Echtgeld-Freigabe möglich (schaltest **nur du**) · rollierend **≤ 50 %** (letzte 50, ab 20 Trades) → sofort Stopp, eigene Positionen schließen, Aufheben nur durch dich |
| D4 | Parallel-Schutz | Zusätzlich: Erwartungswert je Trade nach Kosten > 0 (95-%-Untergrenze), Gewinnfaktor ≥ 1,2, Pflicht-SL **und** Pflicht-TP auf dem Server, Stop ≤ 3× Ziel (geplant **und** realisiert: Ø Verlust ≤ 3× Ø Gewinn), kein Martingale/Grid/Nachkaufen, Tagesverlust-Stopp 3 %, Trefferquote über der Zufallsbasis mit identischer Ausstiegslogik. Verhältnis und Schwellen ändert nur du (Eintrag in `ENTSCHEIDUNGEN.md`, zählt als neuer Versuch) |
| D5 | Risikowerte | Versiegelt bleiben: Hebelband 5–15 und Verlustsperre 25 % (LOSS_LOCK, nur du hebst auf) – Umsetzung §4 |
| D6 | Freigaben | Solo-Betreiber; eigene SL/TP-Ausführungen = normaler Ausstieg |
| D7 | Demo | Vorhandenes MT5 + Demokonto auf dem Laptop; der Agent darf den Bot **auf DEMO** selbst starten/stoppen und fragt nur, wenn du wirklich etwas einstellen musst |
| D8 | Projektgrenze | Systeme außerhalb dieses Projekts gehören weder in den Bot noch in den Spiegel; Betreiberaufgaben dazu: privat |
| D9 | Technik-QA | Zusätzlich muss die Mechanik technisch einwandfrei sein (Tor T) – Sicherheitsvoraussetzung |

**Ehrliche Einordnung (R = Stop-Abstand, vor Kosten):**
- Mit Ziel/Stop-Verhältnis 1:3 ergibt reiner Zufall ~75 % Treffer. 85 % entsprechen ≈ +0,13 R je Trade, 95 % ≈ +0,27 R – das erfordert einen echten Vorteil. Ohne die Parallel-Regeln wären 95 % per Trick (Mini-Ziel, Riesen-Stop) erreichbar und würden nach Kosten Geld verlieren (EURUSD ≈ −7,90 EUR je Lot und Trade).
- Feste Schwellen auf kleinen Stichproben: Eine Strategie mit **wahren** 85 % besteht Entwicklung (≥ 170/200) und Holdout (≥ 34/40) zusammen nur in **etwa 1 von 3 Fällen**, zuverlässig erst ab ≈ 90 % wahrer Quote. Das 95-%-Tor (≥ 95/100) schafft eine wahre 90-%-Strategie nur in ≈ 6 %, eine 93-%-Strategie in ≈ 29 % der Fälle.
- Das versiegelte Hebelband erzwingt bei offener Strategieposition ≥ 5,25×: Ein Stop von 0,5 % Kursabstand kostet 2,6 % (5,25×) bis 7,1 % (14,25×) des Kontos; mit Tagesstopp 3 % bleiben Stops ≤ ~0,55 % und Ziele ≥ ~0,18 %.
- **Wahrscheinlichster ehrlicher Ausgang:** Technik läuft einwandfrei; das 85-%-Tor nur mit echtem Vorteil; das 95-%-Tor sehr wahrscheinlich nicht. Keine Anlageberatung, keine Gewinnzusage.

## 3. Aufgaben nur für dich

| Frist | Aufgabe |
|---|---|
| laufend | Betreiberaufgaben außerhalb des Projekts: privat |
| vor F-02 (**Pflicht**) | MT5-KI/MCP-Server abschalten (Ports 22345/22346); `MetaTrader5` aus dem globalen Python 3.11 entfernen (oder den Agenten per Freigabezeile in F-02 beauftragen); im Navigator prüfen, dass kein Live-Konto mit gespeichertem Passwort im Terminal steht |
| in F-02 (Rückfrage) | Im **eigenen portablen Demo-Terminal** (legt der Agent an) mit dem Demokonto anmelden (bei „Invalid account“: Datei → Konto eröffnen → Demo – nur du), „Algo Trading“ an, Option „Algo-Trading bei Kontowechsel deaktivieren“ an lassen, „Max. Balken: Unbegrenzt“ |
| vor F-02 | Demokonto möglichst: Hedging, EUR, Guthaben ≈ geplantes Echtgeld, Hebel ≥ 1:30, unbefristet |
| ab F-03b | Während Demo-Messungen Windows-Standby aus |
| empfohlen | Platz auf C: schaffen; `work/` (**nicht** in den Tags) erst nach externer Sicherung löschen; Claude Code nur im Repo-Ordner starten (Einzelheiten privat) |
| jede Sitzung | Claude Code im Ordner `KI_Trading_MT5_v4` starten (nur dann gelten Wächter-Hook und Regeln) |

## 4. Zielbild

**Paket `kit/` im v4-Repo:** Broker-Adapter aus `mt5-trading-ai` (gekürzt, korrigiert), Strategie + Statistik aus v4 (kopiert mit Herkunftskopf), Order-Lebenszyklus klein neu für einen Betreiber. v4-Engine, SimBroker und Orakel bleiben unverändert und dienen **nur in Tests** als Differenz-Orakel; `kit/` importiert nie `reference/`, `oracles/`, `validation/` (AST-Test).

```
kit/  domain/ (Typen, Rundung, Geld Decimal, Zeit)   broker/ (seam, mt5_real, sim, sim_modul, readonly)
      orders/ (retcodes, ids, lifecycle, reconcile)  state/ (journal, store)   risk/ (sizing, band, limits, guards)
      strategy/ (base, rev, donchian_ref, notrade, meta_filter)   run/loop.py   probe/mechanik.py
      gates/ (tor_t, trade_test, demo_live)   report/ (redact, bericht)   research/ (stats, trials, daten)
      backtest/ (kosten, runner, paritaet)   ui/ (Statusseite 127.0.0.1)   live_guard.py   cli.py
kit_tests/  Einheit, hypothesis, regression/ (Altrepo), differenz_v4/, orakel/ (SHA-gepinnt), privat/
```

**Wiederverwendung:** `mt5-trading-ai/venue/mt5.py` RealMt5Terminal (Retcode-0-Regel, Füllart-Bitmaske, Serverversatz, Stop-Level), `venue/protocol.py`, `fake.py`, `risk/sizing.py`, `waehrung.py`, `tools/geheimnis_scan.py`, `stubs/MetaTrader5.pyi`, 8 Regressionstests · v4 `reference/research/{baseline,signals,stats,trials,notrade}.py`, `registers/{retcodes,cost_truth,symbols,killer_tests}.json` · Orakel `oracles/{tfd1_oracle,t09_causal,t14_positions,t15_unknown}.py`, `tests/moneypath_harness.py` (nur Tests) · v3 Verlustleiter, OMS-Regeln, Killer-Tests. **Nicht übernommen:** Mt5Venue-Gottobjekt, Betriebsskript, Mutationstore, Validator, Fremdanbindungen, Rollen/Signaturen, WORM/Shamir/Mehrzonen.

**Ein Takt für alles:** Demo, Trockenlauf und Backtest nutzen dieselben Module; nur das Terminal wechselt (echtes MT5 / MT5-Attrappe / Historien-SIM).

**Kernregeln im Code:**
- Journal vor dem Senden (fsync); UNBEKANNT nie blind neu senden, Klärung über `magic`+Symbol+Zeitfenster, Negativnachweis nach 60 s; Auftragskennung im `magic` (nicht im kürzbaren Kommentar).
- Server-SL **und** -TP im Eröffnungsauftrag; Schutzprüfung alle ≤ 5 s und direkt nach jedem Fill; ohne SL nach 30 s → Schließen per Ticket.
- SL/TP-Ausführung = eigener Ausstieg; Stop-out → K2 + Meldung; Ein-/Auszahlungen getrennt gebucht (verschieben keine Anker); Fremdpositionen sperren nur Einstiege und werden nie angefasst. **K3 = alle eigenen Positionen** (magic-Namensräume Strategie + Probe).
- **Demo-Wächter hat Vorrang vor allem**, auch vor Schutz-SL, Schließen und K3: Ist `trade_mode ≠ DEMO` oder `account_info` fehlt → 0 Sendungen, K1-Sperre, Meldung, Prozessende. Zusätzlich muss `terminal_info().data_path` = eigenes portables Demo-Terminal sein.
- **Hebelband (versiegelt 5–15):** gilt für den Namensraum STRATEGIE. Einstieg nur, wenn der Buchhebel nach dem Fill im Korridor 5,25–14,25 liegt **und** rechnerisch beim Kurs = TP noch ≥ 5,25 und beim Kurs = SL noch ≤ 14,25 bleibt (sonst kein Trade). Boden 5 / Deckel 15 werden an Prüfpunkten geprüft (täglich 21:30 Berlin und nach jedem Fill): unter 5 → ganze Position glattstellen, über 15 → reduzieren; Zwangsausstiege sind eigene Ausstiegsart im Bericht. Einfachste Variante: höchstens 1 offene Strategieposition.
- **Tagesbudget:** Einstieg nur, wenn Verlust bis SL der neuen Position (Hebel × SL-Abstand + Kosten) plus Restrisiko aller offenen Positionen ≤ 3 % − heutiger Verlust; Tagesanker = Equity zu Serverzeit 00:00. Tagesstopp und LOSS_LOCK gelten fürs ganze Konto; LOSS_LOCK-Anker = Equity beim Demo-Live-Start.
- Laufzeit aus installierter, getaggter Kopie `%USERPROFILE%\KI-Trading-Bot\app\<tag>` (bis F-03b `%LOCALAPPDATA%\kit`); Laufzeitdaten je Modus getrennt (`sim/trocken/backtest/probe/demo/live`); fehlt der Zustand, obwohl ein Journal existiert → Sperre; Kontoabdruck = HMAC-SHA256 mit lokalem Geheimschlüssel (nie im Repo).
- Zwei Hashes: `mechanik_hash` (feste Dateiliste: domain, broker, orders, state, risk, run, probe, live_guard, Laufzeitversionen – **ohne** ui, report, gates, research, backtest) für Tor T; `strategie_hash` für die Trefferquoten-Tore.

**KI-Rolle:** Claude ist Entwicklungs- und Auswertungsagent. Im Geldpfad entscheidet deterministischer Code. „KI“ im Bot = **vorregistrierter Meta-Filter**: ein Lernmodell schätzt je Signal die Wahrscheinlichkeit „Ziel vor Stop“; nur Signale über der Schwelle werden gehandelt. Offline trainiert, als eingefrorene JSON-Parameter geladen, Laufzeit nur Standardbibliothek. Kein Sprachmodell trifft Handelsentscheidungen.

## 5. Tore (Schwellen und Zählregeln vor der Messung in `config/tore.toml` eingefroren, gehasht)

**Zählregeln (für 85/95/50):** Trade = Strategieposition von Eröffnung bis vollständiger Schließung; Ergebnis = Summe aller Deals inkl. Kommission und Swap; Gewinn nur > 0 (0 = Verlust); nur Namensraum STRATEGIE (Probe zählt nie); neuer `strategie_hash` = neuer Zählstart; 50-%-Fenster beginnt nach deiner Aufhebung neu (alte Trades bleiben im Bericht).

| Tor | Wo | Bestanden, wenn |
|---|---|---|
| **T – Technik** | SIM mit Fehlerinjektion (0 Defekte) + Demo-Probe T-PROBE + Mechanik-Dauerlauf T-DAUER | ≥ 300 gesendete Orderoperationen (≥ 100 Eröffnen, ≥ 100 Schließen, ≥ 50 Ändern), **≥ 95 % fehlerfrei über alle gesendeten** (Ziel 99 %), Quote Absicht→Operation ausgewiesen; Null-Toleranz: Position > 30 s ohne SL, Doppel-Fill, Sendung auf Nicht-Demo, UNBEKANNT > 15 min, offene Abgleichdifferenz, Kill-Drill außerhalb Zielzeit (K1/K2 ≤ 5 s, K3 ≤ 60 s), Schutz-/Schließabsicht durch Risikogrenze abgewiesen; D-/KT-Skripte mit deklariertem Soll-Ergebnis zählen getrennt; Fenster = alle Operationen seit der ersten unter dem aktuellen `mechanik_hash` |
| **85 – Trade-Test** (→ Demo-Live) | Backtest: Entwicklung 01.01.2010 (oder frühester Balken) – 30.06.2021 als Walk-Forward außerhalb der Anpassung; Holdout 01.07.2021–30.06.2026 einmalig | Gesamt-OOS (Entwicklung + Holdout): ≥ 200 Trades, Trefferquote ≥ 85 %, Erwartungswert in R mit 95-%-Bootstrap-Untergrenze > 0, Gewinnfaktor ≥ 1,2, realisiert Ø Verlust ≤ 3× Ø Gewinn, Trefferquote über 95.-Perzentil der Zufallsbasis (komplette Ausstiegslogik, zufällige Richtung, gleiche Einstiegszeiten, ≥ 1.000 Wiederholungen), Max-Drawdown vom Equity-Hoch < 25 % (= kein LOSS_LOCK, egal an welchem Tag man startet; Equity läuft durch, Sperrereignisse rechnet der Backtest als Schatten weiter = nicht bestanden), kein 50-%-Ereignis in der Tradefolge, Hebelband und Tagesbudget eingehalten · Holdout allein: ≥ 40 Trades und ≥ 85 % · Plan-Zusatzkriterien nur mit deinem OK beim PREREG: DSR ≥ 0,95 mit allen Versuchen, ≥ 3/4 Teilperioden positiv, Gewinnfaktor bei Kosten ×1,5 > 1,0 |
| **95 – Demo-Live** (→ Echtgeld-Entscheidung, nur du) | Demo-Live, kumulativ seit Start unter einem `strategie_hash` | ≥ 100 Trades und ≥ 3 Monate, Trefferquote ≥ 95 %, Erwartungswert > 0, Gewinnfaktor ≥ 1,2, kein LOSS_LOCK, Tor T laufend erfüllt; Signaltreue zum täglichen Schatten-Backtest ≥ 95 % und Ist-Kosten ≤ 1,25× Modell (Zusatz, nur mit deinem OK) |
| **50 – Stopp** (immer aktiv) | im Bot | Trefferquote der letzten min(n; 50) Trades ab n = 20 ≤ 50 % → K3 + Sperre + Meldung |

„Nicht bewertbar“ = nicht bestanden. Jede Strategie-, Modell- oder Schwellenänderung nach Datensicht = neuer gezählter Versuch.

## 6. Sicherheit – harte Grenzen (CLAUDE.md + Hook + `permissions.deny` + Code-Tests)

1. Der Agent handelt **nur auf DEMO** (Wächter §4). Er meldet sich nie an, gibt nie Passwörter/Kontonummern ein, eröffnet keine Konten, bewegt kein Geld. MT5 nur über die `kit`-CLI aus `.venv-bot`; Altrepo-Code wird nur gelesen, nie ausgeführt; keine eigenen MT5-Skripte.
2. **LIVE technisch getrennt:** eigenes portables Live-Terminal unter **eigenem Windows-Benutzer oder auf eigenem Rechner/VPS**, Passwort nicht gespeichert; keine Agentensitzung unter diesem Benutzer. Der Live-Pfad im Code bleibt hart gesperrt; freischalten nur du (Schalterdatei + Zertifikate + Entsperr-PIN).
3. **Entsperren nur durch dich:** LOSS_LOCK, 50-%-Sperre, K3-Sperre und Live-Freigaben nur über `kit entsperren`/`kit freigeben` mit einer **PIN, die du in deiner eigenen Konsole festlegst** (gespeichert nur als scrypt-Hash, nie im Chat).
4. **Wächter-Hook** (Matcher `*`, Befehl `py -3.11 -B -I "$CLAUDE_PROJECT_DIR/tools/agent_waechter.py" || exit 2`, intern jede Ausnahme → Exit 2, Timeout 20 s) + **`permissions.deny`** (Pfade in `~/AppData/...`-Form). Verweigert u. a.:
   - `kit entsperren|freigeben|pin-setzen|live`, Schreiben/Löschen unter `~/AppData/Local/kit/{demo,live,freigaben}/**`, `config/live_freigabe.json`, eingefrorene Schwellendateien (Versuchsprotokoll nur anhängen), `tools/agent_waechter.py`, `.githooks/`, `.claude/settings*.json`, `~/.claude/settings*.json`, `~/.claude.json`, `.mcp.json`, `claude mcp add`;
   - Lesen von `~/AppData/Roaming/MetaQuotes/**` (accounts.dat, assistant.ini, common.ini); Befehle mit `MetaTrader5`, `order_send`, `order_check`, `2234[56]` außer `.venv-bot\Scripts\python.exe -m kit <erlaubter Befehl>`; Schreiben von Dateien mit `import MetaTrader5` außerhalb von `kit/broker/mt5_real.py`;
   - `gh` nur per Allowlist (`gh api` ohne Schreibflags, `gh run list/view/watch`, `gh auth status`, `gh repo view`); `git` mit `--force*`/`-f`/`--delete`/`:ref`/`+ref`/`--mirror`/`--prune`/`--no-verify`/`-n`/`-c core.hooksPath`/`clean -x|-X` sowie jeder Befehl mit der öffentlichen Repo-URL außer `python tools/publish.py`;
   - MCP-Terminal-, Browser-, Planungs- und Remote-Werkzeuge in diesem Projekt.
   Jede Sitzung prüft mit `echo KIT_WAECHTER_PROBE` (muss verweigert werden), dass der Hook wirkt; sonst Abbruch. Hinweis: Hooks laden nur beim Sitzungsstart und ein Timeout blockiert nicht – deshalb jede kritische Regel zusätzlich im Code.
5. Nie committen/pushen: Zugangsdaten, Kontonummern/-abdrücke, Allowlists, rohe MT5-Logs/Journale, `.env`, Rohkursdaten. Agent sieht nur redigierte Exporte (Kennzahlen, Abstände in Points).
6. Keine Anlageberatung, keine Gewinnzusage – fester Satz in jedem Bericht.
7. Tabu: v3.0-Ordner, Server und Konten des Betreibers außerhalb dieses Repos, GitHub-/System-/Sicherheitseinstellungen, dauerhaftes Löschen (außer Caches; nie `git clean -x/-X`). Systemänderungen wie Windows-Aufgabenplanung nur mit eigener Freigabezeile.
8. Statt „strengere Variante“ gilt: **einfachste Variante, die die Abnahme erfüllt**; Verschärfung nur aus Sicherheitsgründen (Punkte 1–7).
9. Pakete nur hash-gesperrt von PyPI; mit diesem Plan freigegeben: `MetaTrader5==5.0.6090` (~0,1 MB) + `numpy` (~15 MB) für `.venv-bot` (Python 3.11); `numpy`, `scikit-learn` (+ `scipy`, `joblib`, `threadpoolctl`, ~70 MB) für `.venv-forschung`; `mypy` für Entwicklung.

## 7. GitHub-Routine nach jedem Lauf (`tools/publish.py lauf --lauf <ID> --titel "…" --oeffentlich`)

1. Umgebung: Zweig `main`, `private/main` ist Vorfahr (nur Fast-Forward), Hooks aktiv; Identität `KI-Trading v4 Agent <agent@localhost.invalid>`.
2. **Säubern:** nur aufgezählte Cache-Pfade (`__pycache__`, `.pytest_cache`, `.ruff_cache`, `.hypothesis`, `*.prof`), nie `git clean`; unbekannte Dateien → Abbruch.
3. Laufdateien: `CHANGELOG.md` (Abschnitt `<ID>`), `HANDOFF.md`, `NEXT_PROMPT.md`.
4. **Scan privat:** Größe (≤ 2 MB), verbotene Namen, Benutzerpfade und Sperrliste nur für **neue/geänderte** Dateien (Diff gegen `private/main`, eingefrorene Pfade ausgenommen); Geheimnis-/Token-/Login-Muster über den ganzen Baum mit SHA-gepinnter Ausnahmeliste für synthetische Testmuster. Sperrliste liegt **außerhalb** des Repos (`%LOCALAPPDATA%\kit\sperrliste.txt`).
5. Tests: `kit_tests` voll + `tools/kerntests.py` (feste Liste von Orakel-Modulen, bei 05d7adc nachweislich grün) schnell, voll bei Änderung eingefrorener Pfade.
6. Commit `<ID>: Titel` (Rumpf aus CHANGELOG, Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`), Tag `lauf/<ID>`, Push nach `private`, Remote-SHA prüfen.
7. **Öffentlicher Spiegel** (nur wenn Ziel per GET öffentlich ist und die Spitze eine `PUBLIC_SNAPSHOT.md` trägt; sonst überspringen, nie ein Repo anlegen): Positivliste und Ausschlüsse aus `tools/repo_regeln.json` (seit F-03g alles außer `docs/bot/privat/` und dem Großteil von `referenz/`) → `git archive` in Scratch außerhalb des Repos → Ersetzungen → Null-Toleranz-Rescan (Inhalt, Dateinamen, Commit-Metadaten; auch gesperrte Begriffe, EUR-Beträge ab 1.000, Brokerkennung) → Tests im Export → **eine** verwaiste Momentaufnahme mit fester Agent-Identität → `--force-with-lease=refs/heads/main:<SHA aus ls-remote>` → Prüfung.
8. Blockiert der Spiegel: privater Stand bleibt, Spiegel unverändert, Befundliste (Werte maskiert). Blockiert ein Schritt davor: nichts wird gepusht. Nie `--no-verify`.

## 8. Laufplan und ehrlicher Zeitplan

| Lauf | Inhalt | Ergebnis für dich | Agent | frühestens |
|---|---|---|---|---|
| **F-00** | Neustart (führe ich **direkt nach Freigabe** aus) | Konzept eingefroren, neue Regeln, Plan + Prompts im Repo, Hook/Deny vorbereitet, privater Push | ≤ 3 h | 04./05.10. |
| **F-00b** | Hook live prüfen, `publish.py` + Spiegel + CI | erster öffentlicher Spiegel (nach SPIEGEL-OK) | 3 h | 05.10. |
| **F-01** | Geldpfad-Kern auf SIM | Order-Lebenszyklus fehlerfest, gegen v4-Orakel geprüft | 5–6 h | 06.10. |
| **F-02** | MT5-Anschluss, portables Demo-Terminal, Rauchtest, Datenabzug, **erster Demo-Trade** | 1 Demo-Trade mit SL/TP auf deinem Konto | 5–6 h | 07.–08.10. (Mo–Fr) |
| **F-03** | Risiko (Band, Tagesbudget, Sperren, Zähler), Takt, Kill, Probe, Tor-T-Werkzeug, T-SIM, Trockenlauf | kompletter Bot-Code, 0 Defekte in SIM | 6 h | 08.–09.10. |
| **F-03b** | Installieren, T-PROBE, Kill-Drills, T-DAUER starten (nur Mo–Fr 08–22 Uhr) | Technik-Messung läuft 1–2 Wochen | 3–4 h | Mo 12.10. |
| **F-04** | Backtester, Trade-Test-Werkzeug, 2 Ziel/Stop-Strategien + Referenz | ehrlicher Entwicklungsbericht | 6 h | 12.–14.10. |
| **F-05** | KI-Meta-Filter, Forschungsrunde 2 (bis 3 Runden) | Holdout-Kandidat oder ehrliches „nein“ | 6 h | 15.–18.10. |
| **F-06** | 85-%-Tor mit einmaligem Holdout | Entscheidung Demo-Live ja/nein | 4 h | entfällt (Projekt ruht, F-05e) |
| **F-07** | Tor T auswerten, Statusseite, 95-%-Bewertung, **Demo-Live-Start** | Bot handelt autonom auf Demo; **Prompts enden** | 4–6 h | entfällt (Projekt ruht, F-05e) |
| M-xx (optional) | Monatscheck | Fortschritt 95-%-Tor | 2–3 h | monatlich |
| L-01 (optional) | Echtgeld-Entscheidungsvorlage | nur wenn 95-%-Tor erfüllt; Start nur durch dich | 4–6 h | – |

- Korrekturrunden `F-0xb/c`; abgebrochene Läufe setzen mit gleicher ID fort (lokale WIP-Commits, Veröffentlichung beim Abschluss). Demo-Teile nur bei offenem Markt – sonst Folgelauf, nicht improvisieren.
- F-04–F-06 laufen parallel zu T-DAUER und dürfen den `mechanik_hash` nicht ändern; nötige Geldpfad-Fixes erst nach dem Tor-T-Zertifikat oder mit bewusster Neumessung (F-07b).
- Wird das 85-%-Tor nicht erreicht: höchstens 3 Forschungsrunden, dann entscheidest du (weiter forschen / Demo-Live bewusst ohne Tor als Datensammlung / Pause).
- 95-%-Tor: frühestens ~Februar 2027 und nur bei ≥ 34 Trades/Monat; allgemein ≈ 100 / (Trades pro Monat) Monate – F-05/F-06 berichten die erwartete Frequenz.

## 9. Verifikation (jeder Lauf)

- `pytest kit_tests` grün, `ruff` sauber, `tools/kerntests.py --schnell` grün, CI grün.
- Sicherheit: REAL-Attrappe → 0 Sendungen auf allen Pfaden (auch Schutz-SL, K3, Probe bei geöffnetem Live-Riegel); Mutation des Demo-Wächters macht Test rot; `echo KIT_WAECHTER_PROBE` wird verweigert; offene MCP-Ports → `kit pruefen` ERROR und kein Schreibmodus.
- Ab F-02 Ende-zu-Ende auf Demo: Rauchtest-Export ohne Kennungen; Demo-Trade Journal = Broker; ab F-03b `kit tor-t --stand`.
- `publish.py` Exit 0: Remote-SHA = HEAD; Spiegel = 1 Commit mit Quell-SHA in `PUBLIC_SNAPSHOT.md`, Rescan 0 Treffer.

## 10. Kritische Dateien

v4: `reference/research/{baseline,signals,stats,trials,notrade}.py`, `reference/policy/{band,params}.py` (Band-Semantik), `registers/{retcodes,cost_truth,symbols,killer_tests,parameters}.json`, `reference/moneypath/{engine,sim}.py`, `tests/moneypath_harness.py`, `oracles/{tfd1_oracle,t09_causal,t14_positions,t15_unknown}.py`, `validation/{checks_semantics,checks_hygiene}.py` (Scanmuster zum Kopieren), `docs/SIM_SPEC.md` §8, `.claude/settings.json`, `.gitignore`, `CLAUDE.md`. Extern lesend: `PhilippCode1/mt5-trading-ai` (`mt5_trading_ai/venue/mt5.py` ab ~Z. 2261, `venue/protocol.py`, `venue/fake.py`, `risk/sizing.py`, `tools/geheimnis_scan.py`, `stubs/MetaTrader5.pyi`). v3 (nur lesen): `risk/limits.md`, `execution/oms_ems.md`, `execution/broker_killer_tests.md`.

---

## Anhang A – Lauf F-00

Erledigt am 04.10.2026 (siehe `CHANGELOG.md`, Abschnitt F-00). Der ursprüngliche Ablauf steht im Tag `lauf/F-00`.

## Anhang B – Copy-&-Paste-Prompts

Die Vorlagen aller Laufprompts stehen in [`docs/bot/PROMPTS.md`](bot/PROMPTS.md). Der jeweils nächste, an den echten Stand angepasste Prompt steht in `NEXT_PROMPT.md`.
