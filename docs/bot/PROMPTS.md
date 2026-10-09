# Copy-&-Paste-Prompts (Plan F-1)

Quelle: docs/FAST_TRACK_PLAN.md, Anhang B. Am Ende jedes Laufs passt der Agent den nächsten Prompt an den echten Stand an und schreibt ihn nach NEXT_PROMPT.md; diese Fassungen sind die Planvorlage.

Lauf F-00 lief am 04.10.2026 direkt nach der Planfreigabe (ohne eigenen Prompt).


Jeden Prompt in einer **neuen Claude-Code-Sitzung in der Repo-Wurzel** einfügen (Laptop: `KI_Trading_MT5_v4`, VPS: `%USERPROFILE%\ki-trading` als `kitdev`; nur dort greift der Wächter) und die `<…>`-Platzhalter ausfüllen (unausgefüllter Platzhalter = der Agent fragt zuerst bzw. lässt den betroffenen Teil weg). Am Laufende passe ich den nächsten Prompt an den echten Stand an und gebe ihn dir; diese Fassungen sind der Plan. Jeder Prompt gilt zusammen mit `CLAUDE.md` und `docs/FAST_TRACK_PLAN.md`.

### Prompt F-00b

```text
Lauf F-00b – KI-Trading MT5 Fast-Track: Wächter prüfen, Veröffentlichung, CI.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/FAST_TRACK_PLAN.md §6–§7.
Startprüfung: Baum sauber, HEAD = private/main; führe "echo KIT_WAECHTER_PROBE" aus – wird es NICHT verweigert, sofort stoppen und mir melden.
SPIEGEL-OK: <ja/nein> für PhilippCode1/ki-trading-mt5-v4 (Repo-Status von mir: <öffentlich / privat>).

Aufgaben:
1. tools/publish.py vollständig nach Plan §7 (pruefen, lauf, oeffentlich, aufraeumen, scan; Exit 0/1/2/3), Tests mit erfundenen Werten (inkl. "work/ bleibt nach Säubern erhalten", "Spiegel überspringt privates/fehlendes Ziel", "fester Commit-Autor im Scratch").
2. .githooks (pre-commit: Diff-Scan + ruff; commit-msg: ^(F-\d{2}[a-z]?|M-\d{2,3}|L-\d{2}): ; pre-push: öffentliche URL gesperrt + kit-Schnelltests), core.hooksPath.
3. .github/workflows/ci.yml (privat): Jobs kit (3.11), kern (3.12, --require-hashes), scan; Actions auf SHA gepinnt; contents: read.
4. Live-Probe des Wächters auswerten; Änderungsbedarf nur als Patch-Vorschlag docs/bot/waechter_patch.diff (Wächter, Hooks und Einstellungen ändert nur ich: git apply in meiner Konsole); Test, dass jede Regel aus Plan §6.4 greift.
5. Bei SPIEGEL-OK = ja: erster Spiegel per publish.py; sonst nur privat.

Abnahme: Probe verweigert; publish.py pruefen ohne Befund; CI grün; privat Commit F-00b = Remote-HEAD; Spiegel (falls ja): 1 Commit, PUBLIC_SNAPSHOT.md mit Quell-SHA, Rescan 0 Treffer, kein Konzept-, Betreiber- oder Finanzmaterial.
Abschluss: python tools/publish.py lauf --lauf F-00b --titel "Veroeffentlichung und CI" --oeffentlich (bzw. ohne --oeffentlich), Bericht + Prompt F-01.
```

### Prompt F-01

```text
Lauf F-01 – KI-Trading MT5 Fast-Track: Geldpfad-Kern auf SIM.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/FAST_TRACK_PLAN.md §4–§6. Startprüfung inkl. Wächter-Probe.

Ziel: Lebenszyklus einer Orderoperation ohne MT5 gegen ein SIM-Terminal, fail-closed, gegen v4-Orakel differenzgetestet.
Aufgaben:
1. kit/domain: types, rounding (SL/TP vom Markt weg aufs Tickraster, Volumen nur abrunden, stops/freeze level), money (Decimal), zeit (Serverzeit/UTC/Berlin ohne tzdata).
2. kit/daten/retcodes.json (Kopie mit Herkunft) + kit/orders/retcodes.py: Code 0 nur mit Order-/Deal-ID und Volumen > 0 = Erfolg; unbekannter Code und 10008 bei Deal = UNBEKANNT.
3. kit/orders/ids.py: Auftragskennung als Digest im magic (oberste Bits = Namensraum STRATEGIE/PROBE).
4. kit/state: journal (JSONL, fsync, Tagesrotation, Replay, Schema ohne Login/Server/Name), store (atomar, LOCK, STOP, HMAC-Kontoabdruck mit lokalem Schlüssel, unlesbar oder fehlend trotz Journal = Sperre); Ablage je Modus, echte Ablage unter pytest verboten.
5. kit/broker: seam (Terminal-Protokoll), sim (Kerzenpfad, SL/TP-Auslösung, Lücke = schlechterer Open, SL vor TP in derselben Kerze, Hedging/Netting, Fehler REJECT(code)/TIMEOUT/DISCONNECT ausgeführt+nicht/PARTIAL/DUPLICATE/Absturz vor Netz/Spätdeal).
6. kit/orders/lifecycle: GEPLANT(fsync) → check → send → Klasse → höchstens 3 Neuversuche in 30 s nur bei NOT_EXECUTED → Ende; UNBEKANNT hält Reservierung, sperrt Risikozunahme im Symbol, Klärung per magic+Symbol+Zeitfenster, Negativnachweis nach 60 s, nie blind neu senden.
7. kit/orders/reconcile: SL/TP = eigener Ausstieg; Stop-out → K2 + Meldung; Ein-/Auszahlungen getrennt (Anker bereinigt); manueller Eingriff an eigener Position → Einstiegssperre + Meldung; Fremdpositionen nie anfassen; eigene Position ohne SL → SL in ≤ 30 s, sonst per Ticket schließen.
8. kit_tests: Einheit + hypothesis; differenz_v4/ (t14 ≥ 500 Dealfolgen, t15 R1–R4/R6/R7, Retcode-Matrix 41×5, moneypath_harness) + ABWEICHUNGEN.md; orakel/ mit fest eingetragenem SHA-256; conftest blockiert import MetaTrader5.

Abnahme: kit_tests < 2 min grün; Absturz vor Netz → UNBEKANNT → Negativnachweis → 0 Positionen; DUPLICATE/Spätdeal → genau 1 Position; kein send ohne vorheriges GEPLANT; Journal ohne Kennungen; zweiter Schreiber scheitert an LOCK; Kerntests --schnell grün.
Grenzen: kein MT5 in diesem Lauf.
Abschluss: publish.py lauf --lauf F-01 --titel "Geldpfad-Kern auf SIM" --oeffentlich; Bericht + Prompt F-02.
```

### Prompt F-02

```text
Lauf F-02 – KI-Trading MT5 Fast-Track: MT5-Anschluss und erster Demo-Trade (nur Mo–Fr bei offenem Markt).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/FAST_TRACK_PLAN.md §3, §4, §6. Startprüfung inkl. Wächter-Probe.
Meine Angaben: MCP-Server aus: <ja/nein>. Kein Live-Konto mit gespeichertem Passwort im Terminal: <ja/nein>. Demokonto: <Hedging/Netting>, Währung <…>, Guthaben <…>, Hebel <…>, befristet bis <…/unbefristet>.
GLOBAL-MT5-ENTFERNEN: <ja/nein/schon erledigt> (ja = du darfst "py -3.11 -m pip uninstall -y MetaTrader5" ausführen).
PORTABLES-DEMO-TERMINAL-OK: <ja/nein> (ja = du kopierst C:\Program Files\MetaTrader 5 nach %LOCALAPPDATA%\kit\mt5_demo und legst einen Start mit /portable an; ich melde mich dort an).

Aufgaben:
1. Vorprüfung: MCP-Ports geschlossen und MetaTrader5 nicht im globalen Python, sonst stoppen bzw. laut Freigabezeile handeln.
2. .venv-bot (Python 3.11) mit hash-gesperrtem requirements/bot-runtime.lock.txt (MetaTrader5==5.0.6090, numpy).
3. Portables Demo-Terminal anlegen (falls OK) und mich per Rückfrage bitten: dort mit dem Demokonto anmelden, Algo Trading an, "Max. Balken: Unbegrenzt".
4. Altrepo-Quellen per gh api nur lesen. kit/broker/mt5_real.py nach Plan §4 (initialize nur mit path des portablen Terminals, nie login/password/server; terminal_info().data_path prüfen; Demo-Wächter vor jeder Sendung; order_check vor order_send; Füllart aus Bitmaske; deviation je Symbol; SL+TP im Einstieg; Historie per magic; copy_rates None = Fehler); sim_modul (Attrappe), readonly, stubs; 8 Regressionstests aus dem Altrepo.
5. kit/live_guard.py: REAL immer gesperrt; DEMO-Schreiben nur bei trade_mode DEMO + richtigem Terminalpfad + Kontoabdruck in der Demo-Allowlist (kit konto-registrieren, nur DEMO).
6. CLI: pruefen (ERROR bei offenen MCP-Ports/globalem MetaTrader5), rauchtest (lesend, redigierter Export inkl. margin_mode, Währung, Hebel, Füllarten, stops_level; Hedging Pflicht, sonst Stopp mit Hinweis), daten-ziehen (01.01.2010 bzw. frühester Balken bis 30.06.2021, D1/H4/H1, 7 FX-Symbole; SQLite unter %USERPROFILE%\KI-Trading-Bot\marktdaten\entwicklung.sqlite; SHA-256 je Abzug; Abruf wiederholen bis zweimal gleicher Hash; ABGESCHNITTEN, wenn erster Balken > 7 Tage nach Start obwohl D1 älter ist oder Anzahl ≥ maxbars − 10; < 6 Jahre H1 → Stopp mit Bericht), probe einzel --schreiben (nur DEMO: volume_min mit SL+TP, SL enger, per Ticket schließen; misst Erhalt von magic/comment).
7. rauchtest, daten-ziehen und probe einzel führst du selbst auf meinem Demokonto aus (D7). Bei "Invalid account", Algo Trading aus oder geschlossenem Markt: stoppen und mir genau sagen, was zu tun ist.

Abnahme: Adapter in kit_tests vollständig über die Attrappe; REAL-Attrappe → 0 Sendungen auf allen Pfaden, Wächter-Mutation macht Test rot; AST: MetaTrader5 nur verzögert im Adapter, kein login/password; rauchtest/daten-ziehen: 0 order_send/order_check; Exporte ohne Kennungen; Demo-Trade: Journal = Broker, SL/TP ≤ 30 s auf dem Server, magic erhalten; docs/bot/RAUCHTEST.md (redigiert).
Grenzen: nur DEMO; Holdout-Daten (ab 01.07.2021) nicht ziehen.
Abschluss: publish.py lauf --lauf F-02 --titel "MT5-Anschluss und erster Demo-Trade" --oeffentlich; Bericht + Prompt F-03.
```

### Prompt F-03

```text
Lauf F-03 – KI-Trading MT5 Fast-Track: kompletter Bot-Code (Risiko, Takt, Kill, Probe, Tor T) mit SIM-Nachweis.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/FAST_TRACK_PLAN.md §4–§6, docs/bot/RAUCHTEST.md. Startprüfung inkl. Wächter-Probe.
BAND-PROBE-OK: <ja/nein> (ja = Probe-Positionen [nur volume_min, nur Technik-Messung] sind von der Band-Untergrenze ausgenommen, nicht von Obergrenze, Demo-Wächter, Pflicht-SL; nein = Probe hält das Band ein).

Ziel: ALLE Teile im Bot-Prozess jetzt fertig, damit die spätere Messung nicht neu starten muss.
Aufgaben:
1. kit/risk: sizing (tick_value + Kreuzkurs-Gegenprobe, nur abrunden), band (Plan §4: Einstiegsprüfung inkl. Kurs=TP ≥ 5,25 und Kurs=SL ≤ 14,25; Prüfpunkte 21:30 Berlin + nach Fill; < 5 glattstellen, > 15 reduzieren; max. 1 Strategieposition), limits (Tagesbudget 3 % als Einstiegsprüfung; LOSS_LOCK 25 %; 50-%-Stopp; Zählregeln Plan §5), guards (Kursalter 5 s, Korridor, Spread ≤ 3× Median, Fenster 08–22 Uhr, Freitag ab 20 Uhr keine Einstiege, Margin-Level, Demo-Wächter-Vorrang).
2. kit/run/loop: STOP-Datei jede Sekunde, Schutzprüfung ≤ 5 s und nach jedem Fill, Handelslogik je Minute, nach Neustart zuerst Abgleich; K1/K2 ≤ 5 s, K3 eigene Positionen flach ≤ 60 s; 50/95-Zähler und rollierender Technik-Wächter im Prozess; Meldungen (Windows-Benachrichtigung).
3. kit/probe/mechanik: Profil PROBE (volume_min, alle 7 Symbole, eigener magic-Bereich, unbedingte DEMO-Prüfung auch bei geöffnetem Live-Riegel), Zyklen Öffnen → SL enger → Schließen (≤ 1 je 10 min und Symbol), D-Skripte (referenz/docs/SIM_SPEC.md §8) und Killer-Tests (referenz/registers/killer_tests.json) mit deklariertem Soll-Ergebnis.
4. kit/gates/tor_t + config/tore.toml (eingefroren, Hash; mechanik_hash-Dateiliste ausdrücklich); kit/report (redact, bericht deutsch mit Einordnungssatz); CLI stop --k1/--k2/--k3, entsperren und pin-setzen (nur interaktiv, für mich; Agent per Hook gesperrt), installieren --tag, sichern --ziel, tor-t --stand.
5. docs/bot/NOTFALL.md (STOP-Datei, Knopf Algo Trading, K3, Entsperren mit PIN) und docs/bot/prereg/F04_ENTWURF.md (vollständige Parametertabelle der F-04-Strategien, siehe F-04).
6. T-SIM (≥ 10.000 hypothesis-Folgen, alle Fehlerarten, Matrix 41×5) und Trockenlauf mit beschleunigter Uhr über 5 Handelstage inkl. Wochenende und Mittwochs-Rollover → 0 Defekte, Replay = Abgleich.

Abnahme: jede Limit-/Band-/Sperrstufe per Test ausgelöst, Abbau nie durch Risikogrenzen gesperrt, Sperren überleben Neustart und gelöschten Zustand; Kill-Zeiten in SIM; Probe auf REAL-Attrappe → 0 Sendungen; T-SIM und Trockenlauf 0 Defekte; Entsperren ohne PIN unmöglich (Test).
Grenzen: in diesem Lauf keine schreibenden Demo-Operationen außer Kurztest probe einzel.
Abschluss: publish.py lauf --lauf F-03 --titel "Bot-Code komplett" --oeffentlich; Bericht + Prompt F-03b (mit SHA-256 von F04_ENTWURF.md für F-04).
```

### Prompt F-03b

```text
Lauf F-03b – KI-Trading MT5 Fast-Track: Technik-Messung auf Demo starten (nur Mo–Fr 08–22 Uhr, freitags bis 20 Uhr).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/bot/NOTFALL.md. Startprüfung inkl. Wächter-Probe und kit pruefen.
Meine Vorbereitung: Standby aus: <ja/nein>. PIN gesetzt (kit pin-setzen in meiner Konsole): <ja/nein>.

Aufgaben:
1. Release taggen, kit installieren --tag; Bot läuft nur aus %USERPROFILE%\KI-Trading-Bot\app\<tag>.
2. T-PROBE beaufsichtigt in dieser Sitzung: D-Skripte und Killer-Test-Teilmenge mit Soll-Ergebnis; Kill-Drills K1/K2/K3 je 3×; mind. 5 Wiederanlauf-/Trennungsdrills.
3. T-DAUER (Mechanik-Dauerlauf) losgelöst im Benutzerkontext starten (Start-Process, keine Systemänderung) und mir zeigen, wie ich ihn stoppe; Messung braucht ein Wochenende und einen Mittwochs-Rollover mit offener Position.
4. Wochenexport redigieren; Zwischenstand kit tor-t --stand in berichte/tor_t/.

Abnahme: T-PROBE-Ergebnisse je Skript PASS/FAIL dokumentiert; Drills in Zielzeit; T-DAUER läuft aus der installierten Kopie; nur Probe-magic-Bereich handelt.
Grenzen: nur DEMO; bei geschlossenem Markt Folgelauf statt Improvisation.
Abschluss: publish.py lauf --lauf F-03b --titel "Technik-Messung gestartet" --oeffentlich; Bericht + Prompt F-04.
```

### Prompt F-04

```text
Lauf F-04 – KI-Trading MT5 Fast-Track: Geld-Backtester, Trade-Test-Werkzeug, erste Ziel/Stop-Strategien.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/FAST_TRACK_PLAN.md §5, docs/bot/prereg/F04_ENTWURF.md. Startprüfung. T-DAUER nicht stören; mechanik_hash darf sich nicht ändern.
PREREG-OK: <ja/nein> für docs/bot/prereg/F04_ENTWURF.md, SHA-256 <…> (S-REV-01 Mean-Reversion H1, S-REV-02 Rückkehr H4/Sitzungsspanne – beide mit Server-TP, Stop ≤ 3× Ziel, Einstiegshebel/SL-Rahmen nach Band und Tagesbudget; S-BL-01 = BL-TFD1 unverändert nur als Referenz in eigener Versuchsfamilie, zählt nicht für das 85-%-Tor).
ZUSATZKRITERIEN-OK: <ja/nein> (DSR ≥ 0,95, ≥ 3/4 Teilperioden, Kosten ×1,5; nein = nur berichten).
Ohne PREREG-OK = ja: nur Werkzeuge bauen, keine Datensicht.

Aufgaben:
1. kit/research/stats.py, trials.py als Kopien (Herkunft, SHA-Pin); forschung/versuchsprotokoll.jsonl (Hashkette: Commit, Daten-Hash, Kostenprofil, Schwellen-Hash, PREREG-Zeile); Hashes von Backtester, trade_test.py, kosten.py und Strategien vor der ersten Datensicht eintragen.
2. Kostenprofil aus Rauchtest + referenz/registers/cost_truth.json; kit/backtest/kosten.py mit Differenztest gegen referenz/reference/economics/costs.py.
3. kit/backtest/runner.py: derselbe Takt inkl. Band, Tagesbudget, Sperren, Zählregeln; Kosten, Swap mit Dreifachtag, EUR; Equity durchgehend, Sperrereignisse als Schatten weiterrechnen; paritaet.py.
4. kit/gates/trade_test.py + config/trade_test.toml (eingefroren): alle Kriterien Plan §5 inkl. Zufallsbasis mit kompletter Ausstiegslogik (≥ 1.000 Wiederholungen), realisiertes Verhältnis, Drawdown vom Hoch, 50-%-Ereignis, Trades pro Monat.
5. Gegenproben auf synthetischen Daten: Präfix-Invarianz (Muster referenz/oracles/t09_causal.py, ≥ 200 Suffixe), Signal-Differenz S-BL-01 gegen referenz/oracles/tfd1_oracle.py, Zufallsreferenz netto ≈ −Kosten; Mutationen "Kosten aus", "Look-ahead", "Lot aufrunden" machen Tests rot.
6. Bei PREREG-OK: Walk-Forward auf der Entwicklungsperiode; Bericht berichte/forschung/<datum>_entwicklung.md (+ .json, nur %, R, Anzahl, Trades/Monat). Holdout nicht ziehen.

Abnahme: Gegenproben grün; Kosten-Handrechnung EURUSD und USDJPY auf den Cent; Parität; Versuchsprotokoll verifiziert; Bericht ehrlich je Kriterium inkl. Band-Wirkung; mechanik_hash unverändert.
Abschluss: publish.py lauf --lauf F-04 --titel "Backtester und Trade-Test" --oeffentlich; Bericht + Prompt F-05.
```

### Prompt F-05

```text
Lauf F-05 – KI-Trading MT5 Fast-Track: KI-Meta-Filter und Forschungsrunde 2.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, den F-04-Bericht. Startprüfung. T-DAUER nicht stören.
PREREG-OK: <ja/nein> für docs/bot/prereg/F05_ENTWURF.md, SHA-256 <…> (Meta-Filter auf den Signalen von S-REV-01/S-REV-02; Auswahlregel vorab: nur Varianten, die ALLE Entwicklungskriterien des 85-%-Tors erfüllen; davon die höchste Wilson-95-%-Untergrenze der Trefferquote, bei Gleichstand mehr Trades/Monat; erfüllt keine alles → kein Holdout, Folgelauf F-05b).

Aufgaben:
1. .venv-forschung hash-gesperrt (numpy, scikit-learn inkl. scipy, joblib, threadpoolctl).
2. Labels nach Dreifach-Barriere (Ziel/Stop/Zeit); nur kausale Merkmale; Walk-Forward mit Purge und Embargo; logistische Regression und HistGradientBoosting; Schwelle wählt Trades. Zeitbarriere/Frühausstiege sind auch in der Zufallsbasis enthalten.
3. Eingefrorenes Modell als JSON + kit/strategy/meta_filter.py nur mit Standardbibliothek; Parität zu scikit-learn ≤ 1e-9.
4. Lecktest (Zukunftsmerkmal macht Test rot); jede Konfiguration = gezählter Versuch.
5. Trade-Test-Kennzahlen je Variante; Kandidat nach der Vorab-Regel; erwartete Trades/Monat und Datum für 100 Demo-Trades; Bericht berichte/forschung/<datum>_runde2.md.

Abnahme: Purge/Embargo/Lecktest grün; Laufzeit-Parität; Versuchsprotokoll vollständig; ehrlicher Bericht (auch "kein Kandidat").
Grenzen: kein Sprachmodell im Handelspfad; Holdout bleibt ungezogen.
Abschluss: publish.py lauf --lauf F-05 --titel "KI-Meta-Filter Runde 2" --oeffentlich; Bericht + Prompt F-06 oder F-05b (höchstens 3 Runden, dann entscheide ich).
```

### Prompt F-05b (Forschungsrunde 3, nur ohne Kandidat aus F-05)

```text
Lauf F-05b – KI-Trading MT5 Fast-Track: Forschungsrunde 3 (die letzte nach V9).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, die Berichte F-04/F-05. Startprüfung. T-DAUER nicht stören.
PREREG-OK: <ja/nein> für docs/bot/prereg/F05B_ENTWURF.md, SHA-256 <…> (Idee der Runde 3, gezählte Versuche, eigene Familie; Auswahlregel wie F-04/F-05; erfüllt keine alles → kein Holdout, Entscheidungsvorlage nach V9).

Aufgaben: eigene Runde im Versuchsprotokoll; Datensicht; Gegenproben und unabhängiges Review vor der Datensicht; Auswertung über denselben Takt (drei Kostenprofile, alle Kriterien, Zufallsbasis); Bericht berichte/forschung/<datum>_runde3.md.
Abnahme: wie F-05.
Abschluss: publish.py lauf --lauf F-05b --titel "<Titel>" --oeffentlich; Bericht + Prompt F-06 (Kandidat) oder Entscheidungsvorlage nach V9 (ich entscheide).
```

### Prompt F-05c (Entscheidung nach V9, nur nach drei Runden ohne Kandidat)

```text
Lauf F-05c – KI-Trading MT5 Fast-Track: Entscheidung nach V9 umsetzen.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/bot/ENTSCHEIDUNG_V9.md und die Forschungsberichte. Startprüfung. T-DAUER nicht stören.
ENTSCHEIDUNG-V9: <A Pause, T-DAUER zu Ende | B Demo-Live ohne Tor als Datensammlung | C: neue Idee in einem Satz>

Aufgaben: Entscheidung in docs/bot/ENTSCHEIDUNGEN.md eintragen; A: Tor-T-Stand, bei erreichten Mindestzahlen Auswertung und Zertifikat; B: Vorregistrierung der Datensammlung, kein Start; C: neue Vorregistrierung als Entwurf, keine Datensicht.
Abschluss: publish.py lauf --lauf F-05c --titel "Entscheidung nach V9" --oeffentlich; Bericht + passender Folgeprompt.
```

### Prompt F-05d (Tor-T-Zertifikat nach Entscheidung A, erst bei erreichten Mindestzahlen)

```text
Lauf F-05d – KI-Trading MT5 Fast-Track: Tor T auswerten und Zertifikat erstellen (Entscheidung V9 = A).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/bot/ENTSCHEIDUNGEN.md, berichte/tor_t/. Startprüfung. T-DAUER nicht stören; keine Forschung.
NACH-TOR-T: <offen | B | C: Idee in einem Satz | ENDE>

Aufgaben: Defekte, NICHT_BESTANDEN oder Sperre → sofort auswerten (nicht entsperren). Sonst Mindestzahlen nicht erreicht → nur Stand und Prognose, kein Commit, Prompt erneut. Erreicht → Tor T aus dem redigierten Export auswerten; Defekte mit Ursachenakte, Regressionstest, Korrektur (neuer mechanik_hash = neue Messung statt Zertifikat); BESTANDEN → Zertifikat berichte/tor_t/<datum>.json + .md an mechanik_hash gebunden. Dann NACH-TOR-T (leer = offen): offen = Entscheidungsvorlage; B = Vorregistrierung der Datensammlung, kein Start; C = neue Vorregistrierung als Entwurf, keine Datensicht; ENDE = Abschlussstand.
Abschluss: publish.py lauf --lauf F-05d --titel "Tor-T-Zertifikat" --oeffentlich; Bericht + passender Folgeprompt.
```

### Prompt F-05e (Entscheidung nach dem Tor-T-Zertifikat; so ausgeführt am 09.10.2026 mit ENDE)

```text
Lauf F-05e – KI-Trading MT5 Fast-Track: Entscheidung nach dem Tor-T-Zertifikat umsetzen und das Projekt für die Weiterarbeit auf dem Windows-VPS übergeben.
Du übernimmst das Projekt ohne Vorwissen; alles Nötige steht im Repo. Lies zuerst README.md → HANDOFF.md → docs/README.md → CLAUDE.md (die harten Grenzen gelten für jede KI), dann docs/bot/ENTSCHEIDUNG_NACH_T.md, berichte/tor_t/<datum>.md, docs/bot/ENTSCHEIDUNGEN.md, docs/INSTALLATION_VPS.md und deploy/windows-vps/.
Arbeitsordner: Repo-Wurzel. Startprüfung: echo KIT_WAECHTER_PROBE muss verweigert werden (sonst abbrechen und mir melden), git status sauber, HEAD = private/main, powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles grün, .venv-311\Scripts\python.exe -m kit forschung pruefen = VERIFIZIERT.
Arbeite vollautomatisch nach deiner Empfehlung, ohne Rückfragen; harte Grenzen aus CLAUDE.md gelten unverändert. Bot-Stand nur lesend (kit status --modus probe, kit tor-t --stand --ohne-export); den Bot weder starten noch stoppen; kein MT5-Zugriff; nichts in Profilen oder Ablagen anderer Benutzer; keine Zugangsdaten. Öffentliche Doku frei von privaten Werten und Details zu Systemen außerhalb des Projekts.
ENTSCHEIDUNG-NACH-T: <ENDE | B | C: Idee in einem Satz>
WEITERARBEIT: <Windows-VPS, Benutzer kitdev | Laptop>
SPIEGEL: <ja = öffentlicher Spiegel über publish.py --oeffentlich (Sichtbarkeit und Einstellungen der Repos bleiben unverändert) | nein>

Aufgaben:
1. Entscheidung und Weiterarbeit mit Datum in docs/bot/ENTSCHEIDUNGEN.md eintragen (Abschnitt Änderungen). Zeile leer: nichts entscheiden, kein Commit; nur Bot-Stand berichten und den Prompt erneut ausgeben.
2. ENDE: Abschlussstand „Projekt ruht“ in README.md, HANDOFF.md, docs/README.md, FAST_TRACK_PLAN-Statuszeile und ENTSCHEIDUNG_NACH_T.md – belegt (Tor T, drei Runden), nicht belegt (Handelsvorteil), erhalten (im Repo; nur lokal beim Betreiber), offen für eine Wiederaufnahme. B/C: Vorregistrierung als Entwurf (DEMO_DATEN_ENTWURF.md bzw. F05C_ENTWURF.md mit SHA), kein Start, keine Datensicht.
3. Übergabe an den Weiterarbeitsort: erfassen, was nur lokal liegt (Sperrliste, Kerzenbestand, Bot-Ablage, Tags, Anmeldungen), und den Weg dorthin in INSTALLATION_VPS.md, deploy/windows-vps/README.md, BETRIEB.md, VPS_IDEEN.md und ENTWICKLUNG.md nachziehen (bei ENDE: „nur Entwicklung“, ohne Bot, MT5, Autologon und Aufgaben). Einrichtungsskripte so ergänzen, dass der Entwicklungsbenutzer startklar wird (GitHub CLI, .venv-forschung, Warnungen bei fehlender Sperrliste oder Anmeldung); bekannte Stolpersteine im Werkzeug beheben (außerhalb des Geldpfads, mit Test).
4. Wiederaufnahme-Prompt F-05f für die erste Sitzung am neuen Ort: Vorlage in docs/bot/PROMPTS.md, NEXT_PROMPT.md daraus, Startprüfung für den Entwicklungsbenutzer, Zielzeile.
5. CLAUDE.md nur verschärfen (Ruhezustand, Benutzertrennung auf dem VPS), nie lockern.
6. Laufende T-DAUER: Hinweis an mich (Beenden außerhalb des Probe-Fensters, Offline-Sicherung der nur lokalen Daten).

Abnahme: Entscheidung eingetragen; Übergabe vollständig und vor dem Veröffentlichen unabhängig geprüft; mechanik_hash unverändert; tools\dev.ps1 alles grün.
Grenzen: keine Änderung an Tor- oder Risikowerten oder am Geldpfad; kein Echtgeld; kein Demo-Live; Holdout ungezogen; Sichtbarkeit und Einstellungen der GitHub-Repos unverändert.
Abschluss: publish.py lauf --lauf F-05e --titel "Projekt ruht – Übergabe an den VPS" --oeffentlich (bei SPIEGEL = nein ohne --oeffentlich); Bericht + Folgeprompt F-05f.
```

### Prompt F-05f (Wiederaufnahme nach ENDE, erste Sitzung auf dem VPS als kitdev)

```text
Lauf F-05f – KI-Trading MT5: Wiederaufnahme auf dem Windows-VPS (Benutzer kitdev).
Stand: Das Handelsprojekt ruht seit F-05e (09.10.2026, Entscheidung ENDE). Tor T ist bestanden und zertifiziert (berichte/tor_t/2026-10-09.md); einen Handelsvorteil gibt es nicht (drei Runden, 20 Versuche); der Holdout ist ungezogen.
Du übernimmst ohne Vorwissen; alles Nötige steht im Repo. Lies README.md → HANDOFF.md → docs/README.md → CLAUDE.md (die harten Grenzen gelten für jede KI), dann docs/bot/ENTSCHEIDUNGEN.md (Abschnitt Änderungen), docs/bot/ENTSCHEIDUNG_NACH_T.md und docs/INSTALLATION_VPS.md §0a und §6.
Arbeitsordner: Repo-Wurzel (%USERPROFILE%\ki-trading), Windows-Benutzer kitdev.
Startprüfung – schlägt ein Punkt fehl: nichts ändern, kein Commit, mir genau sagen, was ich tun muss:
1. echo KIT_WAECHTER_PROBE muss verweigert werden, sonst sofort abbrechen.
2. Benutzername = kitdev (PowerShell: $env:USERNAME); git status sauber; git fetch private; HEAD = private/main.
3. .venv-311, .venv-312 und .venv-forschung vorhanden; fehlt eine, darfst du sie mit powershell -ExecutionPolicy Bypass -File tools\dev.ps1 einrichten bzw. forschung anlegen (nur lokale venvs, keine Repoänderung).
4. powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles grün, ohne den Hinweis „.venv-forschung fehlt“; .venv-311\Scripts\python.exe -m kit forschung pruefen = VERIFIZIERT.
5. .venv-311\Scripts\python.exe -B -c "from kit.gates.tor_t import mechanik_hash; print(mechanik_hash()[:8])" = 4fab5281 (sonst gilt das Tor-T-Zertifikat für diesen Code nicht).
6. Sperrliste und GitHub CLI: .venv-312\Scripts\python.exe -B tools\publish.py pruefen --oeffentlich ohne Befund (prüft die Sperrliste über das Werkzeug, ohne dass du sie liest, und ob gh vorhanden ist). Fehlt die Sperrliste: kein Commit, mich bitten. Fehlt nur gh und SPIEGEL = nein: weiter, nur privat veröffentlichen. Bei SPIEGEL = ja zusätzlich gh auth status angemeldet. Nichts davon selbst anlegen (INSTALLATION_VPS.md §6).
Grenzen: kein MT5; den Bot weder starten noch stoppen; keine Aufgabenplanung; nichts im Profil oder in der Ablage von kitbot; Bot-Status nur aus C:\KI-Trading\austausch, falls vorhanden. Kein Echtgeld, kein Demo-Live; Tor- und Risikowerte bleiben versiegelt (D3–D5); der Holdout bleibt ungezogen; der mechanik_hash ändert sich nur mit MECHANIK-OK = ja.
SPIEGEL: <ja | nein = nur privat veröffentlichen>
ZIEL: <B – Demo-Datensammlung ohne Tor vorregistrieren | C: neue Idee in einem Satz | BOT-VPS – Bot unter kitbot vorbereiten, ohne Start | TECHNIK – offene Technikpunkte | ANDERES: in einem Satz>
MECHANIK-OK: <nein | ja = Geldpfad-Änderungen erlaubt, danach ist eine neue Tor-T-Messung nötig>

Aufgaben:
1. ZIEL leer: nur Startprüfung, kein Commit; Ergebnis berichten und diesen Prompt erneut ausgeben.
2. Ziel mit Datum in docs/bot/ENTSCHEIDUNGEN.md eintragen (Abschnitt Änderungen, „Betreiber im Laufprompt F-05f“).
3. B: docs/bot/prereg/DEMO_DATEN_ENTWURF.md mit SHA (Variante mit Begründung, Regeln, Abbruchkriterien, Messgrößen Signaltreue/Ist-Kosten/Ausführung, Dauer, Kennzeichnung „ohne Tor 85 – führt nie zu Echtgeld“) und Plan der Demo-Live-Bausteine; kein Start.
   C: docs/bot/prereg/F05C_ENTWURF.md (eigene Informationsquelle, Familie, Versuche, Gegenproben, Auswahlregel wie F-04/F-05, ehrliche Einordnung gegen die drei Runden); keine Datensicht (PREREG-OK im Folgeprompt). Die Anleitung zum Kerzenbestand (INSTALLATION_VPS.md §6) immer mitgeben; ob er vorhanden ist, bestätige ich (du prüfst die Ablage nicht).
   BOT-VPS: Checkliste für mich nach docs/INSTALLATION_VPS.md §4–§5; kein Start, keine Aufgabe.
   TECHNIK: Entwurf je offenem Punkt (Ursache, Änderung, Test, Folge für den mechanik_hash); umsetzen nur mit MECHANIK-OK = ja.
   ANDERES: Plan und Übergabe nur in diesem Repo; nichts außerhalb anlegen.
4. Status „Projekt ruht“ in README.md, HANDOFF.md, docs/README.md, der FAST_TRACK_PLAN-Statuszeile und allen Kästen „Projekt ruht“ in docs/ und deploy/windows-vps/README.md durch den neuen Stand ersetzen; NEXT_PROMPT.md aus der passenden Vorlage ableiten.
Abnahme: Startprüfung grün; Ziel eingetragen; mechanik_hash unverändert (außer bei MECHANIK-OK); tools\dev.ps1 alles grün.
Abschluss: .venv-312\Scripts\python.exe -B tools\publish.py lauf --lauf F-05f --titel "Wiederaufnahme auf dem VPS" --oeffentlich (bei SPIEGEL = nein ohne --oeffentlich). Exit 3 = privat erledigt, Spiegel blockiert; Exit 2 oder 4: nicht wiederholen, sondern melden. Bericht auf Deutsch und passender Folgeprompt.
```

### Prompt F-06

```text
Lauf F-06 – KI-Trading MT5 Fast-Track: 85-%-Trade-Test mit einmaligem Holdout.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, Forschungsberichte F-04/F-05. Startprüfung.
HOLDOUT-OK: <ja/nein> für Kandidat <ID aus F-05-Bericht>. Ohne ja: abbrechen mit Bericht.

Aufgaben:
1. Siegel HOLDOUT_GEOEFFNET im Versuchsprotokoll (mein OK, Commit, Hashes von Strategie, Modell, Schwellen, Backtester).
2. Holdout-Daten 01.07.2021–30.06.2026 jetzt erstmals ziehen (eigene Datei, Hash), genau einmal auswerten.
3. trade_test vollständig (Gesamt-OOS + Holdout allein) mit Urteil je Kriterium.
4. docs/bot/TRADE_TEST_ERGEBNIS.md (Werte, Urteil, Trades/Monat, Einordnung). Bestanden → config/strategie_demo_live.toml vorbereiten. Nicht bestanden → Optionen (neue Variante nur Forward / Demo-Live bewusst ohne Tor als Datensammlung / Pause) – ich entscheide.

Abnahme: Holdout genau einmal geöffnet (zweiter Versuch bricht ab, Test); Parameter/Kosten/Universum hashgleich zur Vorregistrierung.
Abschluss: publish.py lauf --lauf F-06 --titel "85-Prozent-Trade-Test" --oeffentlich; Bericht + Prompt F-07.
```

### Prompt F-07

```text
Lauf F-07 – KI-Trading MT5 Fast-Track: Technik-Tor auswerten und Demo-Live starten (Mo–Fr).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, docs/bot/TRADE_TEST_ERGEBNIS.md, berichte/tor_t/. Startprüfung inkl. Wächter-Probe.
AUFGABENPLANUNG-OK: <ja/nein> (ja = Windows-Aufgabe im Benutzerkontext, ohne gespeichertes Passwort, ohne Adminrechte, startet nur DEMO; Definition vorher anzeigen).
ZUSATZKRITERIEN-95-OK: <ja/nein> (Signaltreue ≥ 95 %, Ist-Kosten ≤ 1,25× Modell).

Aufgaben:
1. Tor T aus dem redigierten Export auswerten. Jeder Defekt: Ursachenakte docs/bot/defekte/D-<nnn>.md + Regressionstest + Korrektur; ändert sich der mechanik_hash → F-07b (neue Messung) statt Start.
2. Tor T UND 85-%-Tor bestanden: T-DAUER beenden (Probe läuft im Demo-Live nicht), Release taggen und installieren, config/strategie_demo_live.toml aktivieren, LOSS_LOCK-Anker = Equity jetzt, Demo-Live starten; 50-%-Stopp und 95-%-Zähler aktiv.
3. kit/gates/demo_live.py + config/demo_live.toml (eingefroren): kumulativ seit Start, täglicher Schatten-Backtest auf den Demo-Kerzen, Urteil täglich.
4. kit/ui: Statusseite 127.0.0.1 (Standardbibliothek, Zufallsport + Sitzungstoken): Zustand, Positionen (redigiert), Tore 95/50/T, Berichte zum Herunterladen, Knöpfe K1/K2/K3 (schreiben nur die STOP-Datei).
5. Bei AUFGABENPLANUNG-OK: Neustart-Aufgabe; tägliche Sicherung; Meldung 14 Tage vor bekanntem Kontoablauf.
6. docs/bot/DEMO_LIVE.md: Bedienung, tägliche Kontrolle, Notfall, Kontowechsel (neuer Abschnitt, neuer Anker), was der Agent nicht darf.

Abnahme: Zertifikat berichte/tor_t/<datum>.json an mechanik_hash gebunden; Demo-Live läuft aus installierter Kopie; Statusseite und Kill-Knöpfe per Test wirksam; demo_live-Urteil reproduzierbar.
Abschluss: publish.py lauf --lauf F-07 --titel "Demo-Live-Start" --oeffentlich. Prompt-Kette endet hier; optional nur noch M-01 und – falls das 95-%-Tor erreicht wird – L-01.
```

### Prompt M-xx (optional, monatlich)

```text
Lauf M-<nn> – KI-Trading MT5: Monatscheck Demo-Live.
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, letzten Monatsbericht. Startprüfung inkl. Wächter-Probe.
Aufgaben: redigierten Monatsexport erzeugen; demo_live-Urteil (95-%-Fortschritt, 50-%-Stopp), Erwartungswert, Gewinnfaktor, Drawdown, Tagesstopps, LOSS_LOCK, Tor T rollierend, Kosten Ist vs. Modell, Signaltreue, Betriebsgesundheit (Neustarts, Standby, Platz, Sicherungsdatum, Kontoablauf). Nur Fehler korrigieren (Ursachenakte + Test); keine Strategie-/Schwellenänderung ohne meinen Auftrag. Bericht berichte/monat/<JJJJ-MM>.md.
Abschluss: publish.py lauf --lauf M-<nn> --titel "Monatscheck" --oeffentlich. Wenn 95-%-Tor erfüllt: Hinweis auf L-01.
```

### Prompt L-01 (optional, nur wenn 95-%-Tor erfüllt)

```text
Lauf L-01 – KI-Trading MT5: Echtgeld-Entscheidungsvorlage (nur Vorlage – starten werde nur ich).
Arbeitsordner: KI_Trading_MT5_v4. Lies CLAUDE.md, HANDOFF.md, alle Monatsberichte. Startprüfung inkl. Wächter-Probe.
Aufgaben: 95-%-Tor vollständig prüfen; docs/bot/LIVE_ENTSCHEIDUNG.md mit Ergebnis je Kriterium, ehrlichem Verlustrisiko und Anleitung für mich: eigenes portables Live-Terminal unter eigenem Windows-Benutzer oder VPS ohne Agentenzugriff, Passwort nicht speichern, Broker-Checkliste (EU-reguliert, Python/EA-Automatisierung erlaubt, keine KI-Klausel), Live-Risikoprofil-Entwurf mit Optionen, Live-Riegel (Schalterdatei, Zertifikate, PIN). Live-Pfad im Code nur so weit, dass er ohne meine Schalter nie sendet (Tests). Entscheidungszeile leer lassen.
Grenzen: Der Agent startet nie Live, setzt keine Live-Schalter, sieht keine Live-Zugangsdaten.
Abschluss: publish.py lauf --lauf L-01 --titel "Echtgeld-Entscheidungsvorlage" --oeffentlich.
```
