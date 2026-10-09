# CHANGELOG

## F-05e – 09.10.2026 – Projekt ruht – Übergabe an den VPS
- **Start:** Wächter-Probe verweigert, Arbeitsbaum sauber, HEAD = private/main, `tools\dev.ps1 alles` grün, Versuchsprotokoll VERIFIZIERT. Bot-Stand (nur gelesen): T-DAUER läuft, Tor T BESTANDEN (Live-Stand 435 Sendungen, 100 % fehlerfrei; zertifiziert sind 378, `berichte/tor_t/2026-10-09.md`), keine Sperren.
- **Entscheidung des Betreibers:** ENDE – das Projekt ruht. Weiterarbeit auf dem Windows-VPS, öffentlich über den bestehenden Spiegel. Eingetragen in `docs/bot/ENTSCHEIDUNGEN.md`; der Laufprompt F-05e wurde dafür verbessert (Zeilen WEITERARBEIT und SPIEGEL, Übergabe-Aufgaben, unabhängige Prüfung vor dem Veröffentlichen; Vorlage in `docs/bot/PROMPTS.md`).
- **Analyse der Übergabe** (Workflow, 3 Prüfer): Die VPS-Anleitung kannte nur den Bot-Umzug. Sperrliste, GitHub CLI und `.venv-forschung` fehlten für `kitdev`. Der Kerzenbestand war für `kitbot` statt `kitdev` vorgesehen. `publish.py` stürzte ohne GitHub CLI nach dem privaten Push ab. Die Tags `rel/F-03b-*` lagen nur lokal. Es fehlte ein Wiederaufnahme-Prompt.
- **Umsetzung:**
  - `docs/INSTALLATION_VPS.md`: Weg „nur Entwicklung“, §0a Reihenfolge, §6 Entwicklungsplatz, §7a/§7b Abnahme, §8 neue Probleme.
  - `deploy/windows-vps/README.md`; Skripte `30_software.ps1` (GitHub CLI), `60_agent.ps1` (`.venv-forschung`, `dev.ps1 alles`, `kit forschung pruefen`, Warnungen), `00_vorpruefung.ps1` (`gh`), `40_bot.ps1` (Beispiel-Tag `lauf/F-05d`).
  - Doku: BETRIEB, VPS_IDEEN, ENTWICKLUNG, ARCHITEKTUR, SICHERHEIT, NOTFALL.
  - `tools/publish.py`: mit `--oeffentlich` ohne GitHub CLI Abbruch vor dem Commit; fällt sie später aus, wird nur der Spiegel übersprungen (Exit 3). Beides mit Test.
  - Tags `rel/F-03b-1/-2` ins private Repo gepusht.
- **CLAUDE.md verschärft:** Projekt ruht (ohne Zielzeile nur Startprüfung und Bericht); auf dem VPS nur `kitdev`, `kitbot` tabu; Abschlussbefehl mit `.venv-312`.
- **Abschlussstand „Projekt ruht“** in README, HANDOFF, FAST_TRACK_PLAN (F-06/F-07 entfallen), docs/README und ENTSCHEIDUNG_NACH_T. Folgeprompt **F-05f** (Wiederaufnahme auf dem VPS als `kitdev`, Zeilen SPIEGEL, ZIEL, MECHANIK-OK) in `NEXT_PROMPT.md` und `docs/bot/PROMPTS.md`.
- **Abschlussprüfung** (Workflow, 3 Prüfer + Gegenprüfung): kein KRITISCH/HOCH. Umgesetzt:
  - Token-Recht *Workflows: Read and write* (der Spiegel enthält `.github/workflows/ci.yml`, sonst lehnt GitHub den Push ab).
  - Anmeldung der GitHub CLI nur per *Paste an authentication token* mit demselben eingeschränkten Token, keine Browser-Anmeldung.
  - Bot-Status bedingt formuliert: T-DAUER läuft bis zum Stopp durch den Betreiber.
  - NOTFALL §6 an „Projekt ruht“ angepasst.
  - F-05f: Benutzerprüfung über `$env:USERNAME`, Sperrliste für jeden Commit, venv-Anlage erlaubt, Kerzenbestand bestätigt der Betreiber.
  - `60_agent.ps1`: Fehler der Forschungstests ohne Abbruch, damit die Warnungen immer erscheinen.
- Mechanik unverändert (`4fab5281…`); kein Bot-Start oder -Stopp durch den Agenten.

## F-05d – 09.10.2026 – Tor-T-Zertifikat
- **Start:** Wächter-Probe verweigert, Arbeitsbaum sauber, HEAD = private/main, `tools\dev.ps1 alles` grün, Versuchsprotokoll VERIFIZIERT. Zeile `NACH-TOR-T` leer = offen.
- **Verlauf T-DAUER:** ab 08:00 rund 35 Probe-Zyklen je Stunde. Um 09:55 beendete sich der Bot selbst („Algo Trading/Handel am Terminal nicht freigegeben“), der Betreiber startete ihn um 11:54 neu. Derselbe Abbruch trat schon am 06.10. um 00:25 auf. Es gab keine Fehlsendung. Das ist kein Defekt, sondern das vorgesehene Verhalten; als Betriebsbeobachtung in der Entscheidungsvorlage festgehalten. Mindestzahlen erreicht gegen 12:50.
- **Zertifikatswerkzeug** `kit/gates/zertifikat.py`, `kit tor-t --stand --zertifikat`:
  - Zertifikat nur bei BESTANDEN; das Urteil wird aus dem redigierten Export nachgerechnet; strenger als das Tor: keine offene Operation am Fensterende.
  - Gebunden an `mechanik_hash`, Commit (nur auf sauberem Commit ohne Fremddateien im Geldpfad), SHA-256 von `config/tore.toml` und des Exports (byte-gleiche Kopie).
  - Belege nur mit demselben `mechanik_hash`; Dateien exklusiv angelegt, nie überschrieben; Auswertung mit der Wanduhr.
  - `tor_t.auswerten` liefert zusätzlich Fenster (erster/letzter Satz, UTC) und die Zahl offener Operationen.
  - Tests: `kit_tests/test_tor_t_zertifikat.py`. Mechanik unverändert.
- **Prüfung** des Werkzeugs vor dem echten Zertifikat (Workflow, 3 Prüfer + Gegenprüfung). Ein HOCH-Befund wurde behoben: Bei einer am Journalende noch offenen Operation (z. B. UNBEKANNT nach einem Abbruch) wäre ein Zertifikat möglich gewesen. Ebenfalls behoben: Testlücken (Quoten-Zweig, kein Export bei unsauberem Baum, CLI), getrennte Kill-Zahlen für Drills und echte Kills, ehrlicher Skript-Satz, Modus und Python-Version im Zertifikat.
- **Tor T BESTANDEN** (`berichte/tor_t/2026-10-09.md`, `.json`, `_export.json`):
  - 378 Sendungen (Eröffnen 125, Schließen 128, Ändern 125), 378 fehlerfrei = 100 %, 0 offen, 0 Defekte.
  - Skripte D-01/04/06/09/10/12 PASS; Kill-Drills K1/K2 ≤ 1,02 s, K3 ≤ 1,09 s.
  - Fenster Satz 1–2257 (05.10. 20:28 bis 09.10. 11:15 UTC); Commit `62e782f`, `mechanik_hash` `4fab5281…`.
  - Belege: F-03c-Nachweise (Trockenlauf mit Wochenende und Mittwochs-Rollover, T-SIM) und T-PROBE.
- **Entscheidungsvorlage** `docs/bot/ENTSCHEIDUNG_NACH_T.md` (B / C / ENDE; Empfehlung ENDE, T-DAUER kann der Betreiber außerhalb des Probe-Fensters beenden); Folgeprompt F-05e.
- **Abschlussprüfung** (Workflow): kein KRITISCH/HOCH. Umgesetzt: wiederholtes Selbstende (06.10. und 09.10.) in der Vorlage, Hinweis „erst nach Fensterende beenden“ (`--beenden` lässt eine offene Probe-Position stehen), Wortlaut im Stand-Bericht, Wiederaufnahme-Vorlage im Prompt F-05e.
- Doku: Schnittstellen (CLI, Zertifikatsformat), README, FAST_TRACK_PLAN-Status, Entscheidungen, Dokumentübersicht; Stand-Bericht vom Morgen als überholt markiert.

## F-05c – 09.10.2026 – Entscheidung nach V9
- **Start:** Wächter-Probe verweigert, Arbeitsbaum sauber, HEAD = private/main, `tools\dev.ps1 alles` grün, Versuchsprotokoll VERIFIZIERT (56 Einträge).
- **Entscheidung des Betreibers nach V9: A – Pause der Strategieforschung** (Antwort „A“ im Chat zum Laufprompt F-05c). Eingetragen in `docs/bot/ENTSCHEIDUNGEN.md` (Änderungen, Zeile V9), vermerkt in `docs/bot/ENTSCHEIDUNG_V9.md`. Keine Forschung, Holdout ungezogen, F-06/F-07 entfallen vorerst.
- **Bot-Stand (nur lesend, 09.10. 03:40 und 04:05):** T-DAUER läuft, keine Sperren, PIN gesetzt. Der Laptop fuhr gegen 04:00 während der Veröffentlichung selbst herunter (nichts committet, nichts gepusht); der Betreiber startete Bot und MT5 um 04:04 neu, danach 525 Journalsätze. Tor T LÄUFT: 6 Sendungen (Eröffnen 1, Schließen 4, Ändern 1), 6 fehlerfrei, 0 Defekte – unverändert seit 05.10., weil T-DAUER seitdem nur außerhalb des Handelsfensters lief.
- **Mindestzahlen nicht erreicht → kein Zertifikat, Prognose** (`berichte/tor_t/2026-10-09_stand.md`): höchstens 42 Probe-Zyklen ≈ 126 Sendungen je Stunde im Fenster; bindend „Eröffnen ≥ 100“ und „gesendet ≥ 300“ ≈ 100 Zyklen ≈ 2½–5 Stunden Fensterzeit. Bei ungestörtem Lauf voraussichtlich am Freitag, 09.10., sonst am Montag, 12.10. Bei Defekt, NICHT_BESTANDEN oder Sperre startet F-05d sofort (die Zählung wächst dann nicht mehr).
- **Folgeprompt F-05d** (Tor-T-Auswertung aus dem redigierten Export und Zertifikat an `mechanik_hash` gebunden, danach Zeile `NACH-TOR-T` für die nächste Entscheidung); Vorlage in `docs/bot/PROMPTS.md`.
- **Prüfung** (Workflow, 3 Prüfer + Gegenprüfung): kein KRITISCH/HOCH. Umgesetzt: Startbedingung F-05d auch bei Defekt, NICHT_BESTANDEN oder Sperre (eine Null-Toleranz-Sperre friert die Zählung ein); `kit stop --beenden` statt `kit stop`; keine Wochenend-Selbstbeendigung behaupten (montags erst `kit status` prüfen); T-DAUER-Start am 05.10. 22:39; leere Zeile `NACH-TOR-T` = offen; Zertifikat nennt die SIM-Belege für Wochenende und Mittwochs-Rollover (Probe hält nie über Nacht).
- Doku: README-Stand, FAST_TRACK_PLAN-Statuszeile, Dokumentübersicht. Kein Code geändert; Mechanik unverändert (`4fab5281…`).

## F-05b – 09.10.2026 – Richtungsmodell Runde 3
- **Start:** Wächter-Probe verweigert, Arbeitsbaum sauber, HEAD = private/main, `tools\dev.ps1 alles` grün, Protokoll VERIFIZIERT, SHA der Vorregistrierung `F05B_ENTWURF.md` geprüft. Der Betreiber hat den Start bestätigt (PREREG-OK ja).
- **Bot-Stand (nur lesend):** T-DAUER läuft (seit 09.10. wieder), keine Sperren, PIN gesetzt; Tor T LÄUFT (6 Sendungen, 6 fehlerfrei) – nachts außerhalb des Handelsfensters keine Probe-Sendungen.
- **Diagnose vor dem Code:** Die 67/95 STOP_ZU_ZIEL-Ablehnungen bei S-REV-01 in Runde 2 kamen von frühen EURUSD/GBPUSD-Kerzen mit einer Stelle mehr als das Kursraster: Der Takt rundet SL/TP aufs Raster, dadurch liegt Stop knapp über 3 × Ziel. Die Prüfung „handelbar“ der Runde 3 rundet genauso; die gespiegelten SL/TP werden wie im Takt gerundet.
- **Richtungsmodell** `kit/strategy/richtung.py` (Hülle: Kauf- gegen Verkaufsmodell zu denselben Abständen, nur handelbare Punkte, Vorsprung > d*), `kit/research/richtung.py` (Datensatz mit zwei Labels, Purge über beide Ausstiege, Auswertung, Bericht mit Richtungsvorsprung und Geometrie), `forschung/richtung_training.py`, `forschung/runde3.py`. HGB-Modelle verlustfrei kompakt gespeichert (Datei sonst > 2 MB), nach dem Schreiben bitgleich geprüft. Versuchsprotokoll: Runde F-05b (seq 44–54).
- **Gegenproben (grün, vor der Datensicht):** Spiegelung per Handrechnung (auch JPY), Stop/Ziel wie im Takt auch unter dem Raster, Entscheidungen der Hülle, Modellbindung beider Modelle, Purge über beide Ausstiege mit Trainer-Mutation und Negativfällen, Zuordnung Kauf-Label → Kauf-Modell → BUY-Order, Signal-/Trade-/Datensatz-Parität im Takt (H1/H4, auch Kurse unter dem Raster), Zufallspfad-Gegenprobe, Präfix-Invarianz H1/H4 (≥ 200 t09-Suffixe), Lecktest (Fensterschnitt i+6, AUC +0,10), Trainingskette bei wirksamem Purge, Handrechnung der Berichtszahlen.
- **Review** (8 Agenten) vor der Datensicht: im Ergebnispfad keine KRITISCH/HOCH; zwei Testlücken (Richtungswahl nie geprüft, Vertauschung Kauf/Verkauf unentdeckt) und kleinere Punkte behoben. Nach der Auswertung eine Ergebnisprüfung (4 Agenten): alle Zahlen und Hashes nachgerechnet, Modelle bitgleich neu trainiert, keine privaten Werte; Darstellung im Bericht korrigiert (Werkzeugänderung W1, seq 55; JSON unverändert), Spiegel-Doku und -Test um Modelle und Datensätze ergänzt.
- **Ergebnis Runde 3** (`berichte/forschung/2026-10-09_runde3.md`): **kein Kandidat.** Richtungsvorsprung im Datensatz −0,5 / +0,1 / −0,2 / +0,1 Punkte; im Takt Quote − Zufallsmittel −0,9 bis +0,7 Punkte, nie über dem 95. Perzentil; E[R] −0,035 bis −0,053 R, Gewinnfaktor 0,87–0,89. Alle Läufe technisch gültig (Signal- und Trade-Parität 100 %, Datensatz-Parität im Haupt- und 3,25-Profil 100 %).
- **Entscheidung nach V9 vorbereitet:** `docs/bot/ENTSCHEIDUNG_V9.md` (drei Runden, 20 Versuche, Optionen A/B/C, Empfehlung A: Pause der Strategieforschung, T-DAUER zu Ende messen); Folgeprompt F-05c mit Zeile `ENTSCHEIDUNG-V9`.
- Doku: Architektur §5c, Schnittstellen (Aufruf, Modell- und Datensatzformat, Protokoll), Entwicklung (Tests), Glossar, Prompt-Vorlagen. Mechanik unverändert (`4fab5281…`).

## F-05 – 09.10.2026 – KI-Meta-Filter Runde 2
- **Start:** Wächter-Probe verweigert, Arbeitsbaum sauber, HEAD = private/main, `tools\dev.ps1 alles` grün, Versuchsprotokoll VERIFIZIERT, SHA der Vorregistrierung `F05_ENTWURF.md` geprüft. Der Betreiber hat den Start bestätigt (PREREG-OK ja).
- **Bot-Stand (nur lesend):** keine Sperren, **PIN gesetzt**; T-DAUER vom Betreiber am 09.10. wieder gestartet (vorher seit 06.10. aus, „Algo Trading nicht freigegeben“); Tor T LÄUFT (6 Sendungen, 6 fehlerfrei, 0 Defekte).
- **Forschungsumgebung:** `.venv-forschung` (Python 3.11, scikit-learn 1.9.1, numpy 2.4.6, scipy 1.17.1, joblib, threadpoolctl, dazu pytest/hypothesis für die Tests), hash-gesperrt über `requirements/forschung.lock.txt`; `tools\dev.ps1 forschung`; das Training prüft die installierten Versionen gegen das Lock. `kit/` bleibt Standardbibliothek.
- **KI-Meta-Filter** `kit/strategy/meta_filter.py`: Hülle um die Basisstrategie, Merkmale (1)–(12) laut Prereg, Wahrscheinlichkeit aus eingefrorenen JSON-Parametern (logistische Regression, HistGradientBoosting) nur mit `math`; Parität zu scikit-learn 2,2·10⁻¹⁶. Jedes Modell trägt seine Trainingsgrenzen; die Hülle verweigert Modelle, deren Daten ins Testfenster reichen.
- **Runde 2** `kit/research/meta.py` (Datensatz mit demselben Fensterschnitt wie die Signal-Parität, Kerzen wie im Takt, Walk-Forward mit Purge und Embargo, Schwellenregel, Auswertung über den unveränderten Takt, Bericht) und `forschung/meta_training.py`/`forschung/runde2.py` (Training, Export, Aufruf). Eingefrorene Modelle `forschung/modelle/F05/` (nicht im öffentlichen Spiegel); Datensätze nur lokal in `work/f05/`.
- **Versuchsprotokoll:** Runden F-04 und F-05 getrennt (eigene Vorregistrierung, Familien, Werkzeugfamilie, Code-Liste `CODE_F05`); `pruefen` meldet zusätzlich Neusignatur nach der Sicht und prüft Bericht- und Modell-Hashes; `vorab --lauf F-05` verlangt „ja“ und den SHA. F-04 bleibt unverändert VERIFIZIERT. Einträge F-05: seq 32–42.
- **Gegenproben (grün, vor der Datensicht):** Merkmale gegen eine unabhängige Rechnung; Präfix-Invarianz am Datensatz-Bauer für H1 und H4 (≥ 200 t09-Suffixe); Lecktest (Fensterschnitt bis i+6 wird erkannt, Zukunftsmerkmal hebt die Validierungs-AUC um ≥ 0,10); Purge/Embargo/Plan mit Mutation nur im Trainer; Modellbindung (Modell des Folgefensters, Holdout-Modell in 2021-H1 verweigert); Kerzen = Terminal (H1/H4, Kostenfaktor, Lücken); Signal- und Trade-Parität der Hülle im Takt inkl. Mutation „roher H4-Spread“; Laufzeit-Parität ≤ 1e-9 (auch mit fehlenden Werten, Probe ohne scikit-learn nachgerechnet); Trainingskette unabhängig von Kursen ab Testbeginn; Ende-zu-Ende mit Datensatz-Parität.
- **Reviews:** Entwurfsprüfung (9 Agenten) und Code-Review (9 Agenten) vor der Datensicht, beide ohne Leckage-Befund; umgesetzt u. a. Modellbindung, gemeinsamer Fensterschnitt, Datensatz-Parität, Embargo ohne 1.1./25.12., Datensicht atomar, unabhängige Purge-Gegenprobe, Plan-Bindung. Nach der Auswertung eine Ergebnisprüfung (5 Agenten): alle Zahlen und Hashes nachgerechnet, keine privaten Werte; die Spalte „50-%-Ereign.“ zählte LOSS_LOCK-Schatten mit – Berichtsgenerator korrigiert (Folge und Schatten getrennt, Zufallsmittel, Erklärsätze; Werkzeugänderung W1, seq 43), Markdown aus dem unveränderten JSON neu erzeugt. Tests sichern jetzt, dass Kostenprofile, Modelle und Datensätze nicht in den Spiegel gelangen.
- **Ergebnis Runde 2** (`berichte/forschung/2026-10-09_runde2.md`): **kein Kandidat.** Trefferquoten 72,0/71,9 % (S-REV-01, LOGREG/HGB) und 57,9/62,8 % (S-REV-02); der Filter hob die Quote gegenüber F-04 (70,1 % bzw. 51,2 %), aber die Zufallsbasis zu denselben Zeitpunkten stieg gleich mit (Zufallsmittel 72,9/72,3 % bzw. 57,8/63,5 %). Er findet Marktphasen, keine Richtung (Quote − Zufallsmittel −0,9 bis +0,1 Punkte; bei S-REV-02 vor allem Geometrie: weiter Stop). E[R] −0,03 bis −0,04, Gewinnfaktor 0,91–0,95; Drawdown 22–73 % (Start 2013 mit vollem Kapital, nicht direkt mit F-04 vergleichbar). Alle Läufe technisch gültig, Signal-, Trade- und Datensatz-Parität 100 %.
- **Runde 3 vorbereitet:** `docs/bot/prereg/F05B_ENTWURF.md` (Richtungsmodell: nur handelbare Zeitpunkte, Kauf gegen Verkauf zu denselben Abständen, mindestens 50 Validierungssignale, 4 Versuche, Familie F05B-RICHTUNG), SHA `b1ec2a2e…`; PREREG nach Delegation eingetragen. Nach V9 die letzte Runde, danach entscheidet der Betreiber.
- Doku: Architektur (§5b KI-Meta-Filter), Schnittstellen (Runde-2-Dateien und -Aufruf, Protokollprüfung), Entwicklung (`.venv-forschung`, Tests, Ablauf einer Lernmodell-Runde), Glossar, Prompt-Vorlage F-05b. `tools/publish.py` unverändert; `forschung/modelle/**` vom Spiegel ausgeschlossen. Mechanik unverändert (`4fab5281…`).

## F-04 – 08.10.2026 – Backtester und Trade-Test
- **Start:** Wächter-Probe verweigert, `kit pruefen` ohne Warnung („Agent-Wächter sperrt die Laufzeitablage“). Der Arbeitsbaum enthielt den vom Betreiber eingespielten Wächter-Patch (gestaged, byte-identisch mit `docs/bot/waechter_patch.diff`); der Agent hat ihn unverändert als eigenen Commit übernommen.
- **Bot-Stand (nur lesend):** Probe-Ablage 385 Sätze, keine Sperren, letzter Start endete am 06.10. 00:25 mit „Algo Trading am Terminal nicht freigegeben“; Tor T LÄUFT (6 Sendungen, 6 fehlerfrei, 0 Defekte); `mechanik_hash` 4fab5281… unverändert.
- **Backtester** `kit/backtest/`: derselbe Takt (`kit.run.loop.Bot`) über einem Historien-SIM, Schritt je H1-Schluss; Kostenmodell (Spread je Kerze, Kommission je Seite, Swap mit Dreifachtag, Umrechnung EURUSD/EURJPY, Kosten × f); Vorgriffswächter; LOSS_LOCK/STOP50 als Schatten (Equity läuft durch); Speicherjournal; schnelle Ausstiegsrechnung für Parität und Zufallsbasis.
- **Trade-Test** `kit/gates/trade_test.py` + `config/trade_test.toml` (eingefroren): alle Kriterien von Plan §5 inkl. Zufallsbasis (1.000 Wiederholungen, komplette Ausstiegslogik), Bootstrap-Untergrenze, Drawdown vom Hoch, 50-%-Ereignisse, unabhängige Band-/Budget-Nachrechnung (inkl. Stop ≤ 3 × Ziel), Technik-Kriterium (Parität 100 %).
- **Strategien:** S-REV-01, S-REV-02 und S-BL-01 genau nach Vorregistrierung (`kit/strategy/{rev,donchian_ref,varianten}.py`).
- **Forschung:** `stats.py`/`trials.py` als Kopien mit SHA-Pin; Versuchsprotokoll mit Hashkette, Vorprüfung (Code und Mechanik = Vorregistrierung, Arbeitsbaum committet), Vollständigkeitsprüfung, Schutz gegen Umschreiben; `kit forschung vorab|kostenprofil|entwicklung|pruefen|aenderung`.
- **Gegenproben (grün):** Kosten-Handrechnung EURUSD (100,13 EUR) und USDJPY (135,20 EUR) auf den Cent; Differenztest Kosten gegen `costs.py`; Präfix-Invarianz mit 208 t09-Suffixen (Strategien und Runner) sowie mehrere Symbole/JPY/H4/Swap; Signal-Differenz S-BL-01 gegen `tfd1_oracle`; Zufallsreferenz netto ≈ −Kosten; Mutationen „Kosten aus“, „Look-ahead“ (auch nur USDJPY), „Lot aufrunden“ werden erkannt; Datei- gleich Speicherjournal.
- **Review vor der Datensicht** (Workflow, 25 Agenten, jeder Befund KRITISCH/HOCH doppelt gegengeprüft): 7 bestätigte Befunde, alle behoben – Holdout-Grenze am Kerzenende statt -beginn, S-REV-02 rechnet den Einstieg mit dem Spread der Quote, „bestanden“ verlangt technische Gültigkeit und Parität, fail-closed Vorprüfung vor Datensicht und Auswertung, vollständigere Code-Liste plus `mechanik_hash`, Daten an die Hashes der Datensicht gebunden, keine Zweitauswertung, Spreadprofil privat.
- **Datensicht und Werkzeugänderung W1:** Die Entwicklungsdaten (F-02) stehen in **Serverzeit**, nicht in UTC (Versatz nie gemessen; Datenprüfung: Wochenöffnung immer Mo 00:00 Serverzeit, New-Yorker Sommerzeit). Der Datenleser rechnet mit +3 h um; Datenbericht F-02, Doku und Entscheidungen korrigiert; künftige Abzüge bleiben in Serverzeit.
- **Ergebnis Runde 1** (`berichte/forschung/2026-10-08_entwicklung.md`): **keine** der 12 Varianten erfüllt das 85-%-Tor, kein Holdout-Kandidat. Trefferquoten 58–70 % (S-REV-01) bzw. 34–51 % (S-REV-02), jeweils knapp unter dem Zufallsmittel und unter dem 95. Perzentil; E[R] −0,05 bis −0,18, Gewinnfaktor 0,71–0,87; mit dem Band (Hebel ≥ 5,25) Drawdown über 90 %. Alle 36 Läufe technisch gültig, Parität 100 %, Protokoll VERIFIZIERT.
- **Spiegel-Nachtrag (W2):** Der Rescan des öffentlichen Spiegels fand in der Kopie `kit/research/trials.py` einen Namen aus dem privaten Kontext (Docstring und ein Wert in `ACTORS`, aus der Referenz übernommen). Er ist neutral durch „Assistenz“ ersetzt, Pin und privater Differenztest sind angepasst, die Änderung steht als Werkzeugänderung W2 im Versuchsprotokoll. Ergebnisse unberührt: Kein Protokolleintrag nutzt diesen Wert.
- **Spiegel-Export verlegt:** `tools/publish.py` exportiert jetzt in den Ordner `kit-publish` unter LOCALAPPDATA. Bisher lag der Export in der alten Ablage (Ordner `kit` unter LOCALAPPDATA), die der Wächter seit dem Patch sperrt. Dort verweigerten die Wächtertests im Export jeden relativen Pfad, und der Spiegel blieb rot.
- **Runde 2 vorbereitet:** `docs/bot/prereg/F05_ENTWURF.md` (Meta-Filter, 4 Versuche, SHA `88bdd6cc…`), PREREG nach Delegation eingetragen.
- Doku: Architektur (§5a Backtest und Trade-Test), Schnittstellen (`kit forschung`, Forschungsdateien), Entwicklung (Strategie-Ablauf, Gegenproben), Konfiguration, Glossar. Mechanik unverändert.

## F-03g – 06.10.2026 – Übergabe öffentlich
- **Öffentlicher Spiegel vollständig**: Code, alle Tests, Werkzeuge, VPS-Skripte (`deploy/windows-vps/`), CI, Git-Hooks, die gesamte Dokumentation sowie `CLAUDE.md`, `HANDOFF.md` und `NEXT_PROMPT.md`. Privat bleiben nur private Betreibernotizen und der Großteil des eingefrorenen Konzeptarchivs `referenz/`. Aus der Referenz sind die Dateien öffentlich, die die Differenztests und die F-04-Orakel brauchen.
- **Tests im Spiegel**: Mit `privat` markierte Tests werden dort automatisch übersprungen; die Kerntests der Referenz enden mit einem Hinweis statt eines Fehlers. Sechs bisher private Tests laufen jetzt öffentlich, zwei neue Tests sichern die Spiegelregeln.
- **Übernahme**: README mit Lesereihenfolge, Abgrenzung öffentlich/privat und Hinweisen zum Weiterarbeiten im eigenen Fork; Doku-Index, Entwicklung und Sicherheit nachgezogen.
- **Testkorrektur**: Zwei Umzugstests schrieben Altbestand und Umzugsmarke im selben Windows-Zeittakt (~16 ms). Der bewusst strikte Zeitvergleich wertete das gelegentlich als nicht umgezogen, und der Test fiel zufällig um. Die Tests datieren den Altbestand jetzt fest zurück; der Code bleibt fail-closed.
- Mechanik und Bot-Code unverändert.

## F-03f – 06.10.2026 – Neuordnung und VPS-Vorbereitung
- **Repo neu geordnet**: 1.115 → 307 getrackte Dateien. Der Ballast der Konzeptphase (838 Dateien: Evidenz, ADRs, Validator, Generatoren, Konzepttests und -doku) ist aus dem Arbeitsbaum entfernt und vollständig in den Tags `konzept-c11-gruen`/`konzept-c12-wip` erhalten. Die eingefrorene Referenz liegt geschlossen und bytegleich unter `referenz/` (nur Orakel für Tests; Kerntests 4.405 grün). Die Wurzel enthält nur noch Lebendes.
- **Vollständige Dokumentation** unter `docs/`: Übersicht mit Glossar, Architektur, Schnittstellen (CLI, Exit-Codes, Dateiformate, Strategie-Protokoll), Konfiguration, Entwicklung und Erweiterung, dazu Installation, Betrieb, Wartung, Sicherheit und kritische Bewertung (privat).
- **Windows-VPS vorbereitet** (privat, `deploy/windows-vps/`):
  - Skripte für Vorprüfung, System, getrennte Benutzer für Bot und Agent, Software, Bot-Einrichtung, Aufgabenplanung, Agent-Arbeitsplatz und Status; alle mehrfach ausführbar und ohne gespeicherte Zugangsdaten.
  - Autostart-Hülle mit Neustart-Regeln (kein Neustart nach einem Sicherheits-Ende).
- **Bedienung** (Mechanik unverändert):
  - `kit wiederherstellen --aus <zip>`;
  - Tagessicherung ohne Konsole (nie in Agentensitzungen; Schlüssel nur interaktiv);
  - `kit tor-t --ohne-export`;
  - rechnerspezifische `lokal.toml` (nur Terminalpfad und Symbolnamen);
  - Ablage-Umleitung über eine Testvariable geschlossen.
- **Werkzeuge**: `tools/dev.ps1` (einrichten, test, kern, lint, scan), `ruff check .` statt Dateilisten, CI zusätzlich unter Windows, Kerntests aus `referenz/`, öffentlicher Spiegel nur mit Bot, Tests und Entwickler-Doku.
- **Integrität**: `kit lauf` aus einer Installation prüft vor dem Start den `mechanik_hash` gegen `INSTALLATION.json` (auch im Autostart); bei Abweichung Exit 2.
- **CI-Korrektur**: Der Linux-Job war seit F-03b rot. Ursache: Zwei Umzugstests erhalten auf ext4 gleiche Datei-Zeitstempel. Der Zeitstempelvergleich ist jetzt strikt; bei Gleichstand entscheidet der SHA-Abgleich im Umzugsbuch (fail-closed).
- **Abschluss-Review** (Doku gegen Code, VPS-Skripte, Repo-Integrität): Alle bestätigten Befunde sind behoben. Betroffen waren Autostart (Anführungszeichen bei `cmd`, BEENDEN während der Pause, MT5-Prüfung vor jedem Start), Herzschlag nur bei laufendem Prozess, zentrale VPS-Konfiguration, sprachunabhängige und abgesicherte RDP-Beschränkung, Exit-Code-Prüfungen, Statusskript und Veröffentlichung.

## F-03b – 05.10.2026 – Technik-Messung gestartet
- **Erster Demo-Trade** (22:28): EURUSD 0,01 Lot, SL und TP im Auftrag, SL enger, Schließen per Ticket – jeweils ERLEDIGT (10009), 0 Abgleichdifferenzen. Deal-Grund EXPERT, magic und Kommentar erhalten, Positions-ID = Ticket, Kommission 0, Uhrabweichung 0,05 s. Alles wie in der Vorflug-Recherche (`docs/bot/RAUCHTEST.md`).
- **T-PROBE** (`berichte/tor_t/2026-10-05_tprobe.md`): D-01, D-04, D-06, D-09, D-10 und D-12 je 3× PASS, kein FAIL. Kill-Drills: K1 und K2 in 1,0 s, K3 flach in 1,1 s. Der Server lehnt die D-04/D-06-Fehlfälle schon bei order_check ab (10014, 10025, 10016, 10013). Die übrigen NICHT_TESTBAR kamen vom dünnen Kursstrom gegen 22:30 Uhr (Kurs älter als 5 s); die Skripte haben sich korrekt geweigert.
- **T-DAUER läuft** seit 22:39 aus der installierten Kopie `rel/F-03b-2`, mechanik_hash `4fab5281…`. Probe-Einstiege nur im Fenster 08–22 Uhr (freitags bis 20 Uhr); erster Tor-T-Stand LAEUFT, 0 Defekte (`berichte/tor_t/2026-10-05_stand.md`).
- **Laufzeitablage verlegt** nach `%USERPROFILE%\KI-Trading-Bot`:
  - Grund: Windows leitet `%LOCALAPPDATA%`-Schreibzugriffe aus paketierten Apps (die Claude-Desktop-App und alles, was sie startet) in einen Paket-Cache um. Die Konsole des Betreibers sah andere Dateien als der Bot (STOP-Datei, `kit stop`, Status, PIN).
  - `kit umziehen` kopiert den Altbestand prüfend, ohne Überschreiben und ohne Löschen. Die Mechanik ist unverändert.
- **Drei Review-Runden zum Umzug** (Workflows, jeder Befund unabhängig gegengeprüft). Korrekturen nur außerhalb der Mechanik, neues Modul `kit/umzug.py`:
  - **Umzugs-Tor:** Bot-Start, Probe, Terminalbefehle, `pin-setzen` und `entsperren` verweigern mit „erst kit umziehen“, solange eine frühere Ablage (`%LOCALAPPDATA%\kit` oder ihre Paket-Cache-Kopie) Journale, Freigaben oder eine echte STOP-Datei hat, die nicht im **Umzugsbuch** (`UMZUG.json`, Pfad + SHA-256) stehen. Sonst begänne die neue Ablage leer, und dauerhafte Sperren, Anker und PIN wären still weg. Später neu geschriebene Altdaten öffnen das Tor wieder. `kit stop` bleibt immer frei.
  - **`kit umziehen`:**
    - Steuerdateien (STOP, BEENDEN, Protokolle) zählen nicht als Daten. STOP wird nach der Max-Regel zusammengeführt (Drill-Dateien nicht), BEENDEN nie übernommen.
    - Hat das Ziel schon eigene Daten, übernimmt er die Sperren: BOT_SPERRE, nachzuholende Auslöser wie beim Botstart, Symbolsperren dauerhaft. Bei unlesbarem Altjournal setzt er fail-closed K2.
    - Jede Datei geht über eine Teil-Datei mit SHA-Prüfung und wird erst dann unter ihrem Namen angelegt (nie überschreiben). Ein Abbruch setzt fort.
    - Übernommen wird je Quelle nur, was seit der letzten Übernahme entstand (Stand im Umzugsbuch). Vom Betreiber schon aufgehobene Sperren kommen so nicht zurück, und die Marke eines früheren Umzugs bleibt gültig.
    - `--von` wählt bei mehreren Altbeständen. `--abschliessen` beendet einen verwaisten Umzug mit K2 auf allen Modi, auch auf noch nicht kopierten.
  - **Wächter:**
    - `kit installieren` verweigert, solange der Repo-Wächter die neue Ablage nicht sperrt; `kit pruefen` warnt.
    - Gehärteter Patch-Vorschlag `docs/bot/waechter_patch.diff` (nur der Betreiber spielt ihn ein):
      - Unter der Ablage ist nur `export/` lesbar. Gesperrt sind dort auch 8.3-Namen, `.`, `//`, `..`, ein Punkt am Namensende, Quoting- und Escape-Tricks sowie Platzhalter.
      - Shell-Argumente werden je Einzelbefehl aufgelöst (relativ, Variablen, Git-Bash-Laufwerke). Such-, Listen-, Kopier- und Wechselbefehle dürfen keinen Elternordner der Ablage treffen.
      - Ebenfalls gesperrt: UNC- und Gerätepfade, Ordnernamen aus Variablen oder Join-Path, die Paket-Cache-Kopien und Dateiangaben anderer Werkzeuge (SendUserFile, Artifact inkl. `out_dir`).
      - `kit sichern` ist nur noch für den Betreiber.
      - 129 Wächtertests in einer Wegwerfkopie grün.
      - Gegenprobe: alle 385 Shell-Befehle dieser Sitzung durch den gepatchten Wächter; neue Fehlalarme nur noch bei Befehlen, deren Text Ablagepfade nennt.
  - `kit sichern` läuft nur interaktiv beim Betreiber, weil die Sicherung Rohjournale und auf Wunsch die Schlüssel enthält.
- **Betrieb:**
  - Versatzmessung: Das erste Symbol wird bis 30 s gemessen, jedes weitere bis 5 s. Ausgewichen wird nur bei stehendem Kursstrom; andere Fehler gelten sofort, und die Meldung nennt jede Ursache.
  - Lauf, Skriptläufe und Einzelprobe schreiben ein ENDE, wenn der Start nach dem START-Satz scheitert, auch bei Strg+C im Bot-Fenster (ENDE ABBRUCH). Der Status meldet dann nicht mehr fälschlich „läuft“. Geschrieben wird über ein frisch von der Platte gelesenes Journal, damit ein Abbruch mitten im Schreiben die Hashkette nicht bricht.
  - `kit starten` meldet „Gestartet“ erst, wenn der Bot einen neuen START mit der Mechanik der Installation ins Journal geschrieben hat (höchstens 150 s). Einen sofort endenden Bot meldet es mit dem Ende des Konsolenprotokolls.
- Entscheidungen nach Delegation: PREREG F-04 = ja (SHA `621351dc…`), Ablage verlegt (`docs/bot/ENTSCHEIDUNGEN.md`).

## F-03e – 05.10.2026 – Folgeprompt korrigiert
- `NEXT_PROMPT.md` ist jetzt der angepasste F-03b-Prompt: Rauchtest, Registrierung und Daten sind erledigt; der Lauf beginnt mit dem ersten Demo-Trade und installiert `lauf/F-03e`. In F-03d war versehentlich der alte Stand veröffentlicht worden. Code unverändert.

## F-03d – 05.10.2026 – Demo-Vorbereitung (Rauchtest, Registrierung, Daten)
- **Erster Kontakt mit dem echten Demokonto** (nur lesend), nachdem der Betreiber MT5 gestartet und ein gültiges Demokonto angemeldet hat: DEMO, Hedging, EUR, Hebel 1:100. Alle 7 Symbole sind voll handelbar (FOK, stops_level 0, Spreads 0–7 Points), Serverversatz +3 h, Umrechnungskurse lesbar. Bericht: `docs/bot/RAUCHTEST.md` (redigiert).
- Demokonto registriert (nur HMAC-Abdruck, lokal).
- **Datenabzug** der Entwicklungsperiode 2010–06/2021 vollständig: 7 Symbole × D1/H4/H1, je 11,5 Jahre, alle Abzüge OK. Der Holdout ist nicht gezogen. Kennzahlen: `berichte/daten/2026-10-05_entwicklung.md`.
- `kit daten-ziehen` robuster:
  - ein Terminalfehler betrifft nur seine Zeile (Status FEHLER mit Hinweis);
  - Vorprüfung gegen „Max. Balken“ (MT5 liefert Historie nur so weit ab heute zurück; Status MAXBARS_ZU_KLEIN mit Anleitung);
  - `--fehlende` zieht nur, was noch nicht als OK vorliegt.
- Nachweise auf dem F-03c-Stand (`berichte/tor_t/2026-10-05_f03c_nachweise.md`): T-SIM mit 10.000 Abläufen bestanden; Trockenlauf 7 Tage mit 3.001 Sendungen, 100 % fehlerfrei, 0 Defekte, Replay gleich.
- Noch nicht gelaufen: erster Demo-Trade, T-PROBE und T-DAUER. Der Knopf „Algo Trading“ blieb bis zum Ende des Handelsfensters aus; es wurde nichts gesendet.

## F-03c – 05.10.2026 – Vorflug-Korrekturen vor dem ersten Demo-Lauf
Vor dem ersten Lauf auf einem echten Demo-Server lief eine Vorflug-Prüfung als Workflow. Vier Recherchen prüften die Semantik der echten MetaTrader5-Python-API an MQL5-Doku und Forum, jede mit einer unabhängigen Gegenprüfung. Danach folgte eine Auswirkungsanalyse auf den Code.
- **Ergebnis der Recherche:** Python-Aufträge tragen DEAL_REASON_EXPERT und den magic des Auftrags. Ein Handschluss im Terminal hat Grund CLIENT und magic 0, ebenso SL/TP-Schlüsse bei manchen Brokern. Ein erfolgreiches order_check liefert 0. Die Historie läuft auf der Server-Wanduhr. Symbole außerhalb der Marktübersicht liefern keinen Tick, und eine Terminal-Option kann den Python-Handel sperren.
- **Adapter:**
  - Der Serverversatz wird fein gemessen (Tick rückt vor). `zeit()` folgt danach der Serveruhr auf monotoner Basis; Stellen der PC-Uhr wirkt nicht.
  - Ohne Versatz gibt es keine Historie und keinen Start.
  - Symbole werden in der Marktübersicht automatisch ausgewählt.
  - Die Python-API-Sperre zählt zu „Handel erlaubt“.
  - Kerzenabschluss nach der angeglichenen Uhr; eine Kurszeit in der Zukunft gilt als unstimmig (kein Einstieg).
- **Lebenszyklus:**
  - Sperren aus Retcodes (z. B. 10018 „Markt zu“) laufen nach 1 h ab. Sperren aus Beobachtungen bleiben, bis der Betreiber sie mit `entsperren --grund SYMBOL:<Symbol>` aufhebt; sichtbar in `kit status` mit allen Gründen.
  - Deals werden über den magic bestätigt (SL/TP/SO ausgenommen), Fenster ±120 s.
- **Abgleich:**
  - Zuordnung über die Positions-ID: Handschluss mit magic 0 ist ein manueller Eingriff, SL/TP mit magic 0 ein eigener Ausstieg, auch nach einem Neustart.
  - Ein eigener Auftrag mit Handgrund ist kein Eingriff, aber nur, wenn er nachweislich aus dem Auftrag stammt.
  - „Erledigt“ ohne Deal-Ticket wird nachgetragen.
- **Einzelprobe:** misst den Serverversatz, prüft den offenen Markt und berichtet je Deal Grund, magic und Positionsbezug sowie den Erhalt von magic und Kommentar.
- **Rauchtest:** nennt die Ursachen getrennt (Knopf Algo Trading, Python-API-Option, Konto ohne Algo-Handel, fehlender Umrechnungskurs).
- **D-Skripte:**
  - Erwartete Retcodes nach Recherche erweitert (D-04: 10013/10014/10038; D-06: gleicher Wert 10025/10016, ungültiger SL 10016/10013); je Schritt die Stufe CHECK/SEND.
  - Zusätzliche Prüfungen, dass Position bzw. SL nach einer Ablehnung unverändert sind.
- **Adversariales Review** (3 Prüflinsen, je Befund ein Gegenprüfer, 9 bestätigt, keiner verworfen), alle Befunde behoben mit Tests (`kit_tests/test_vorflug_f03b.py`, `kit_tests/test_review_f03c.py`):
  - Skript-Kennungen sind je Lauf eindeutig (sonst endete jede Wiederholung mit FAIL).
  - Die installierte Kopie besteht `pruefen`, die Installation verlangt den Wächter im Repo, und `starten` meldet einen sofort endenden Bot.
  - `entsperren ALLE` schreibt keinen Sammelsatz mehr (LOSS_LOCK-Anker und Zählfenster bleiben).
  - Umrechnungspaare werden auch mit Broker-Endung gefunden.
  - Die stündliche Messung blockiert höchstens 2 s.
  - Der erste Tick nach dem Abonnement wird abgewartet.
- **Ordnung:** 39 Dateien hatten durch Python-Patches unter Windows CRLF-Zeilenenden; alle lebenden Dateien sind wieder LF.
- **Prüfstand:** kit_tests 317 grün, ruff sauber.

## F-03a – 05.10.2026 – Spiegel-Korrektur
- Der Null-Toleranz-Rescan des öffentlichen Spiegels hat ein Testmuster in `kit_tests/test_review_f03.py` als Betrag erkannt (Ziffern + Währungskürzel). Das Testmuster ist umformuliert, die Prüfung bleibt gleich streng.

## F-03 – 05.10.2026 – Bot-Code komplett
- `config/tore.toml` (eingefroren, SHA-256 in `kit/gates/__init__.py`): versiegeltes Band 5–15 / Korridor 5,25–14,25, LOSS_LOCK 25 %, Tagesbudget 3 %, Stop ≤ 3 × Ziel, 50-%-Stopp, Zählregeln, Tor T / 85 / 95 und die ausdrückliche `mechanik_hash`-Dateiliste.
- `kit/risk`: Nominal und Ergebnis in Kontowährung mit Tickwert-Gegenprobe über Kreuzkurse (`sizing`); Hebelband mit Einstiegsprüfung inkl. Kurs = TP/SL, Gesamtobergrenze, höchstens einer Strategieposition und Probe-Ausnahme nur unten (V4); Prüfpunkte BAND_BODEN/BAND_DECKEL (`band`); Tagesbudget, Tagesstopp, LOSS_LOCK, Tradebuch nach Zählregeln, 50-%-Stopp, 95-%-Stand (`limits`); Einstiegswächter (Demo-Vorrang, Fenster 08–22 Berlin, freitags bis 20 Uhr, Kursalter, Fehlkurs-Korridor, Spread, Margin-Level) (`guards`).
- `kit/run/loop.py` – der Takt: STOP/BEENDEN-Datei jede Sekunde, Schutztakt ≤ 5 s und nach jedem Fill (Demo-Wache, Abgleich mit Schutzaktionen, Anker, Grenzen, Technik-Wächter), Strategie je Minute (nur frische Kerzen, stabile Kennung je Kerze), Zeitbarriere, Band-Prüfpunkt täglich 21:30 und nach jedem Fill. K1 vorübergehend; K2/K3 und alle Grenz-Sperren dauerhaft (Journal + Zustand, fail-closed vereinigt). K3 schließt alle eigenen Positionen (Ziel ≤ 60 s). Drills ohne dauerhafte Sperre. Wiederverbinden bei Terminalfehlern; Demo-Vorrang beendet den Prozess.
- `kit/probe`: Probe-Mechanik (volume_min, alle 7 Symbole, ≤ 1 Zyklus je 10 min und Symbol: Öffnen → SL enger → Schließen) und D-Skripte D-01/04/06/09/10/12 mit deklariertem Soll-Ergebnis (Killer-Tests KT-04/05/07/12/16/19/21–25/31/32); Netting-, Pending-, Teilfill- und Netztrennungs-Skripte begründet NICHT_TESTBAR.
- `kit/gates/tor_t.py`: Tor-T-Auswertung allein aus dem Journal (Fenster je `mechanik_hash`, Quote über alle Sendungen, Skripte getrennt, alle Null-Toleranz-Arten); `kit/report` (Redigieren, deutscher Bericht mit Einordnungssatz).
- PIN (scrypt) und Entsperren nur für den Betreiber (interaktive Konsole, nie in einer Agentensitzung, nie bei laufendem Bot); gelöschter Zustand bleibt gesperrt, bis der Betreiber ihn aus dem Journal wiederherstellt.
- CLI: `lauf --modus probe|demo --schreiben`, `stop --k1|--k2|--k3|--beenden|--k1-aufheben`, `status`, `tor-t --stand`, `entsperren`, `pin-setzen`, `installieren --tag`, `sichern --ziel`, `probe skripte`, `trockenlauf`. Demo-Live bleibt gesperrt bis F-06/F-07.
- SIM: Swap/Rollover (Dreifachtag), Kerzen und Deals zeitlich indiziert. Adapter: Kontoabdruck je Verbindung zwischengespeichert, Historienpolster 1 h statt 14 h, sobald der Serverversatz gemessen ist. Abgleich: Folgeläufe lesen ab letztem Lauf − 15 min (stündlich volles Fenster), Journalbeginn als Untergrenze.
- `docs/bot/NOTFALL.md` (Anhalten, K1–K3, Entsperren, Kontowechsel, Rechte des Agenten) und `docs/bot/prereg/F04_ENTWURF.md` (vollständige Parametertabelle S-REV-01, S-REV-02, Referenz S-BL-01; 12 + 1 gezählte Versuche; Auswahlregel).
- Zwei unabhängige Code-Reviews (Sicherheit; Risiko/Tore) mit zusammen 29 Befunden. Ein Weg zu einer Sendung auf ein Nicht-DEMO-Konto wurde nicht gefunden. Alle Befunde sind behoben, je Befund ein Regressionstest (`kit_tests/test_review_f03.py`):
  - **Ablage:** Laufzeitablage fest über die Windows-Shell-API; `KIT_HOME` gilt nur in Tests. Ein schreibender Bot je Windows-Benutzer.
  - **Skripte und Einzelprobe:** eröffnen nie trotz Sperre.
  - **PIN:** nur interaktiv, auch beim direkten Python-Aufruf; mindestens 10 Zeichen, scrypt N=2^16, nach 5 Fehlversuchen 1 h gesperrt; `sichern` ohne PIN-Dateien.
  - **Kapital und Anker:**
    - Kapital, Stop-out und Abgleich-Auslöser werden sofort angewandt und beim Neustart aus dem Journal nachgeholt.
    - Ein-/Auszahlungen verschieben nur Anker, deren Equity-Lesung vor dem Deal lag; am Tageswechsel wird nichts doppelt gezählt.
    - Nach dem Aufheben von LOSS_LOCK gilt ein neuer Anker.
  - **Abbau:** höchstens ein offener Abbau je Ticket; nach Ablehnung Wartezeit von 30 s, verdoppelt bis 15 min.
  - **Einstieg:** kein Einstieg, solange einer unterwegs ist (Band, Budget, eine Strategieposition); nur Hedging-Konten.
  - **Kill:**
    - K3-Zeit läuft ab der Sperre, auch über einen Neustart.
    - Kill-Dauer nicht mehr aus alten Datei-Änderungszeiten.
    - Drills gehen den echten Weg über die STOP-Datei.
    - Technik-Pause und Vorfälle überdauern bzw. wiederholen sich beim Neustart korrekt.
  - **Abgleich:** Doppel-Ausführung wird erkannt (DOPPEL_FILL → Sperre); Kontowechsel während der Sendung ist ein Vorfall. Fenster ±3 h plus stündliche Neumessung des Serverversatzes (Zeitumstellung beim Broker); Deals eigener Operationen werden nie wegen der Startzeit übergangen.
  - **Tor T:** FAIL eines Skripts bleibt FAIL; Notschluss zählt immer; UNBEKANNT-Dauer ab der Sendung; nur Operationen des Fensters; Absicht→Operation nicht doppelt gezählt; Zielzeiten nur für Drills.
  - **Sonstiges:** `strategie_hash` mit allen Einstellungen; Prüfpunkt wird nach einem Fehler nachgeholt; Umrechnungssymbol wird ausgewählt; Netting-Swap im SIM; schärferes Redigieren.
- Nachweise (auf dem Endstand, Berichte unter `berichte/tor_t/`):
  - T-SIM: 10.000 zufällige Abläufe mit allen Fehlerarten, 41 Retcodes, Spätlieferungen, SL-Verlust, Fremdhandel, Neustarts und Wechsel auf REAL.
  - Trockenlauf: 7 Tage im 1-s-Takt über die MT5-Attrappe mit Wochenende, Mittwochs-Rollover mit offener Position und Neustart.

## F-02 – 05.10.2026 – MT5-Anschluss (Code)
- `kit/broker/mt5_real.py`: MT5-Adapter (Herkunft Altrepo, gekürzt und korrigiert): MetaTrader5 nur verzögert importiert; `initialize` nur mit `path`, nie mit Zugangsdaten; startet kein Terminal; prüft den verbundenen Terminalpfad; Serverzeit ↔ UTC (Versatzmessung über Tickfortschritt, Historienfenster gepolstert); Füllart aus der Bitmaske (ohne gemeldete Füllart kein Raten); `None` aus positions/orders/deals/rates = Fehler; Decimal an der Grenze; Kapital-, Gebühren- und Handelsdeals getrennt.
- `kit/broker/sim_modul.py`: MetaTrader5-Attrappe über dem SIM-Terminal – der echte Adaptercode läuft vollständig in CI (zählt order_send/order_check für Nur-Lese-Nachweise, verweigert initialize mit Zugangsdaten). `kit/broker/readonly.py`: Nur-Lese-Hülle.
- `kit/live_guard.py`: REAL immer gesperrt; Schreiben nur bei DEMO + Algo Trading an + Kontoabdruck (HMAC) in der lokalen Demo-Allowlist; `konto-registrieren` nur für DEMO.
- `kit/research/daten.py`: lesender Kerzenabzug in SQLite außerhalb des Repos, SHA-256 je Abzug, Wiederholung bis zweimal gleicher Hash, ABGESCHNITTEN/INSTABIL/LEER/ZU_KURZ, Holdout-Sperre.
- `kit/betrieb.py` + CLI: `rauchtest` (nur lesend, redigiert: keine Login-Nummer, kein Server-/Firmenname, keine Kontostände; Befunde zu Hedging, Algo Trading, Max. Balken), `daten-ziehen [--holdout]`, `konto-registrieren`, `probe einzel --schreiben` (nur DEMO: volume_min mit SL+TP → SL enger → per Ticket schließen → Abgleich; verweigert bei Befund aus `pruefen`). MT5-Fehler enden mit klarer deutscher Meldung (Exit 4) statt Traceback.
- `config/kit_demo.toml` (Symbole, Zeiträume; Zugangsdaten-Schlüssel technisch verboten), `.venv-bot` mit hash-gesperrtem `requirements/bot-runtime.lock.txt` (MetaTrader5 5.0.6090, numpy 1.26.4).
- Regressionen aus dem Altrepo übernommen (`kit_tests/test_regression_altrepo.py`, 8 Fälle); dabei Lücke geschlossen: „Erledigt“ ohne Order- und Deal-Ticket gilt jetzt als UNBEKANNT (Klärung über Abgleich) statt als Fill.
- Umgebung: globales MetaTrader5 aus Python 3.11 entfernt (`kit pruefen` alles OK, MCP-Ports geschlossen).
- Demo-Teile **nicht** ausgeführt: Das laufende MT5-Terminal meldet „Authorization failed“ (kein gültiges Demokonto angemeldet). Anmeldung darf nur der Betreiber; Rauchtest, Datenabzug und erster Demo-Trade folgen in F-03b.
- Tests: kit_tests 212 grün, Kerntests grün, ruff sauber.

## F-01 – 05.10.2026 – Geldpfad-Kern auf SIM
- `kit/domain`: Typen (Decimal), Rundung (Volumen nur abrunden, SL/TP vom Markt weg, Mindestabstand), Geld-Helfer, Zeit (Berlin ohne tzdata).
- `kit/orders`: Retcode-Einordnung (Kopie der v4-Matrix, Regel Code 0), Auftragskennung als Digest im magic (Präfix + Namensraum), Lebenszyklus (Journal vor dem Senden, UNBEKANNT mit Reservierung und Symbolsperre, Negativnachweis nach 60 s, kein blindes Neusenden, höchstens 3 Versuche in 30 s, Demo-Vorrang vor allem, Wiederherstellung nach Absturz), Abgleich (Server-SL/TP = eigener Ausstieg, Stop-out → K2, manueller Eingriff/Fremdposition sperren und werden nie angefasst, Schutzpflicht ≤ 30 s, Kapitalbewegungen getrennt).
- `kit/state`: Journal (JSONL, fsync je Satz, Hashkette, Kontokennungen verboten), Zustand (atomar, fehlend/unlesbar = Sperre), Ein-Schreiber-Sperre (OS-Lock), STOP-Datei K1–K3, HMAC-Kontoabdruck.
- `kit/broker`: Terminal-Naht und SIM-Terminal (Kerzenpfad mit SL/TP-Auslösung, Lückenregel, Hedging/Netting, Fehlerinjektion).
- Differenztests gegen v4-Orakel: T-15 (11 Szenarien wie Orakel), T-14 (600 Zufallsfolgen Hedging/Netting = Orakel = SIM-Wahrheit), Retcode-Matrix 41×5; Abweichungen dokumentiert (`kit_tests/differenz_v4/ABWEICHUNGEN.md`); Orakel-Kopien SHA-gepinnt.
- Gegenproben: absichtlich gebrochene Regeln (Frühnachweis, Vorzeichen im Positionsbuch) machen die Differenztests rot.
- Unabhängiges Code-Review (2 Prüfer, 23 Befunde) eingearbeitet, je Befund ein Regressionstest (`kit_tests/test_review_f01.py`): lokale Ablehnung überdeckt nach Neustart nie eine gesendete Operation (Doppelsendung verhindert); STOP-Datei in jeder Kodierung (UTF-8-BOM/UTF-16 aus PowerShell) mit höchster Stufe; Demo-Prüfung standardmäßig fail-closed; Operation nur einmal anstoßbar; neue Operation sendet nur den Rest der Absicht; späte Restfills nach Negativnachweis gemeldet; kontoweite Sperre bei Konto-Retcodes; Pending-Orders vorerst nicht freigegeben; Code 0 bei SL/TP nur über Abgleich; Abgleich über Positions-ID (kein Fehlalarm nach Schluss per Ticket), breites Historienfenster, verarbeitete Deals journalisiert (kein Doppelzählen nach Neustart), Gebühren getrennt von Kapital, keine Automatik an Netting-Positionen mit Fremdvolumen, Journal nur bei Änderung; Journal robust gegen Uhrsprung und abgerissene letzte Zeile, Schlüsselvarianten von Kontokennungen gesperrt; Zustand-Speichern mit Wiederholung unter Windows; SIM: Lücke über TP füllt zum Eröffnungskurs, Fremdhandel verschmilzt im Netting.
- Tests: kit_tests 189 grün; Geldpfad unter 2.000 Zeilen (Grenze 5.000).

## F-00c – 04.10.2026 – Spiegel-Korrektur
- Erster Spiegel-Versuch in F-00b wurde vom eigenen Null-Toleranz-Rescan blockiert (ein Kommentar in `tools/publish.py` enthielt einen vierstelligen Euro-Betrag als Beispiel) – Kommentar umformuliert.
- `publish.py`: Korrekturläufe verlangen nur noch eine aktualisierte `HANDOFF.md` (Folgeprompt darf gleich bleiben).

## F-00b – 04.10.2026 – Veröffentlichung und CI
- `tools/publish.py`: Abschlussroutine (säubern nur Caches, Fast-Forward-Prüfung, unbekannte Dateien, Größen-/Namensgrenzen, Diff- und Baum-Scan, kit_tests + Kerntests, Commit mit fester Agent-Identität, Tag `lauf/<ID>`, Push nach `private` mit Remote-SHA-Prüfung) und bereinigter öffentlicher Spiegel (Positivliste, Ersetzungen aus externer Sperrliste, Null-Toleranz-Rescan, Tests im Export, eine Momentaufnahme mit `--force-with-lease` auf den gelesenen Stand).
- Git-Hooks in `.githooks/` (pre-commit: Diff-Scan + ruff; commit-msg: Titelmuster + Vermerk für eingefrorene Pfade; pre-push: öffentliche URL gesperrt + kit-Schnelltests), `core.hooksPath` aktiv.
- CI `.github/workflows/ci.yml` (kit 3.11, Kerntests 3.12, Baum-Scan), Actions auf Commit-SHA gepinnt.
- `.scan_basislinie.json` (eine begründete Ausnahme: synthetisches Testpasswort im eingefrorenen Konzepttest).
- Projekt-Skill `.claude/skills/kit-lauf` (Start-/Abschlussroutine).
- Tests: kit_tests 104 grün (neu: test_publish), Marker `privat` für Tests, die nur im privaten Repo laufen.
- Hinweis: Diese Läufe liefen auf ausdrücklichen Wunsch des Betreibers autonom in einer Sitzung ohne aktiven Wächter-Hook (Sitzung im Elternordner gestartet); Grenzen wurden selbst eingehalten. Live-Probe des Hooks folgt in der ersten Sitzung im v4-Ordner.

## F-00 – 04.10.2026 – Neustart Fast-Track
- Plan F-1 freigegeben (`docs/FAST_TRACK_PLAN.md`): schlanker Demo-Bot statt Konzeptbürokratie; Entscheidungen D1–D9 in `docs/bot/ENTSCHEIDUNGEN.md`.
- Konzeptphase eingefroren: Tags `konzept-c11-gruen` (e5619d3, letzter grüner Stand) und `konzept-c12-wip` (05d7adc) im privaten Repo; Bundle-Sicherung lokal.
- Wurzel-Laufdateien der Konzeptphase umbenannt nach `archiv/konzept-c/` (keine gültigen Regeln mehr); neue `CLAUDE.md` mit harten Sicherheitsgrenzen und schlankem Laufablauf.
- Neu: `tools/agent_waechter.py` (fail-closed PreToolUse-Hook + `permissions.deny` in `.claude/settings.json`, ersetzt den nie aktiven Pfadlogger), `tools/kit_scan.py` (Geheimnis-/Personendaten-Scan, Muster als Kopie), `tools/kerntests.py` (35 Orakelmodule, 4.440 Tests grün), `tools/repo_regeln.json` (lebend/eingefroren, Spiegelziel).
- Neu: Gerüst `kit/` (`version`, `pruefen` mit MCP-Port- und Global-MT5-Prüfung, Laufzeitablage je Modus mit Testsperre) und `kit_tests/` (Struktur-, Scan-, Wächter-, Ablagetests); `pytest` startet jetzt die schlanke Suite.
- `.gitignore`/`.gitattributes` gehärtet (Geheimnisse, MT5-Dateien, Rohdaten; keine Zeilenendenumwandlung).
- Plan, alle Copy-&-Paste-Prompts (`docs/bot/PROMPTS.md`), öffentliche Kurzfassung und private Sicherheits-To-dos abgelegt.
