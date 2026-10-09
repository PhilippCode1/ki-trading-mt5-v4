# Schnittstellen

Alle Stellen, an denen der Bot mit etwas anderem spricht: MT5, Betreiber (CLI und Steuerdateien), Dateien, Strategien, Tests und VPS-Skripte. Architektur: [ARCHITEKTUR.md](ARCHITEKTUR.md).

## 1. MetaTrader 5 (Broker-Adapter)

**Protokoll** `kit.broker.seam.Terminal`. Implementiert von `Mt5Terminal` (echt), `SimTerminal` (Tests, Trockenlauf) und `ReadOnlyTerminal` (Hülle ohne Sendefunktion für den Rauchtest):

| Methode | Rückgabe | Bemerkung |
|---|---|---|
| `account()` | `AccountSnapshot` | `trade_mode` (DEMO/REAL/…), `margin_mode` (HEDGING …), Equity, `abdruck` = HMAC-SHA256(`geheim\hmac.key`, "login\|server")[:32], `trade_allowed` = Konto ∧ Expert ∧ Terminal ∧ Python-API nicht gesperrt |
| `symbol(name)` | `SymbolSpec` | Tickgröße/-wert, Volumenraster, Stops-Level, Füllart aus Bitmaske (FOK > IOC > RETURN) |
| `quote(name)` | `Quote` | Bid/Ask, `time_msc` in UTC |
| `bars(name, tf, start, ende)` | `[Bar]` | `copy_rates_range`, Serverzeit → UTC, `is_closed` |
| `positions()`, `orders()` | Listen | eigene + fremde; Zuordnung über `magic` |
| `deals(seit, bis)` | `[Deal]` | Historie in Server-Wanduhr, 1 h Polster; Kapitalbuchungen getrennt |
| `check(req)` | `CheckResult` | `order_check`; Erfolg = Retcode 0 |
| `send(req)` | `SendResult \| None` | `order_send`; `None` = Ausgang unbekannt → UNBEKANNT |
| `zeit()` | float (UTC) | Serveruhr auf monotoner Basis nach Versatzmessung |
| nur echt: `verbinden()`, `trennen()`, `messe_versatz(symbol)`, `versatz_s`, `rest_s`, `info` | | `initialize(path=…)` – **nie** `login`/`password`/`server`; ohne laufendes `terminal64.exe` → Fehler (der Bot startet kein Terminal) |

**Verwendete MT5-Funktionen:** `initialize`, `shutdown`, `terminal_info`, `account_info`, `symbol_info`, `symbol_select`, `symbol_info_tick`, `copy_rates_range`, `positions_get`, `orders_get`, `history_deals_get`, `order_check`, `order_send`. `MetaTrader5` wird nur in `kit/broker/mt5_real.py` importiert (Test + Wächter).

**Gesichertes MT5-Verhalten** (live geprüft, `docs/bot/RAUCHTEST.md`):
- Python-Aufträge tragen Deal-Grund EXPERT und behalten den `magic`. Ein Handschluss im Terminal hat Grund CLIENT und `magic` 0.
- `order_check` meldet Erfolg mit 0. Fehlfälle wie 10014, 10025, 10016 und 10013 lehnt der Server schon dort ab.
- Serverversatz +3 h. Die Historie läuft auf der Server-Wanduhr.

## 2. Auftragskennung

| Feld | Aufbau |
|---|---|
| `client_id` | `k` + 24 Hex (SHA-256 von `strategie\|symbol\|zeit\|aktion\|nummer`) |
| `magic` | `0x4B49 << 48 \| namensraum << 44 \| digest44` – Namensraum 1 = STRATEGIE, 2 = PROBE |
| Kommentar | `kit:` + client_id (kann vom Broker gekürzt werden – maßgeblich ist `magic`) |
| Absicht-Präfixe | `S-` Strategie, `P-`/`PS-` Probe, `PE-` Einzelprobe, `SK-` Skripte, `SCHUTZ-`, `NOTSCHLUSS-`, `K3-`, `ZEITBARRIERE-`, `BAND_BODEN-`, `BAND_DECKEL-` |

## 3. Kommandozeile `python -m kit <befehl>`

Ausführen im Repo (Entwicklung) bzw. über die Startdateien der Installation. Befehle mit MT5 nur aus `.venv-bot`.

| Befehl | Zweck | MT5 | Wer |
|---|---|---|---|
| `version` | Version | – | alle |
| `pruefen` | Umgebung: Python, Platz, MCP-Ports 22345/22346, globales MetaTrader5, Wächter (Exit 1 bei FEHLER) | – | alle |
| `rauchtest` | nur lesend: Terminal, Konto, Symbolverträge, Versatz; Export | ja | Betreiber/Agent |
| `daten-ziehen [--holdout] [--fehlende]` | Kerzen D1/H4/H1 → `marktdaten\*.sqlite`, SHA-256 je Abzug | ja | Betreiber/Agent; Holdout nur mit HOLDOUT-OK |
| `konto-registrieren` | aktuelles DEMO-Konto (Abdruck) in die Allowlist | ja | Betreiber |
| `probe einzel\|skripte --schreiben` | ein Demo-Zyklus bzw. D-Skripte (`referenz/docs/SIM_SPEC.md` §8, privat) | ja | beaufsichtigt |
| `lauf --modus probe\|demo --schreiben [--dauer-min]` | der Takt im Vordergrund (`demo` bis F-07 gesperrt) | ja | Startdateien/Autostart |
| `stop --k1\|--k2\|--k3\|--beenden\|--k1-aufheben [--modus]` | Kill-Stufe bzw. geordnetes Ende über Steuerdatei | – | alle, **immer erlaubt** |
| `status [--modus]` | Sätze, Sperren, STOP, letzter Start/Ende, PIN gesetzt, Demokonten, `umzug_offen`, Meldungen | – | alle |
| `tor-t --stand [--modus] [--ohne-export]` | Tor-T-Urteil (+ Export) | – | alle |
| `tor-t --stand --zertifikat [--modus]` | bei BESTANDEN: frischer redigierter Export, daraus Zertifikat `berichte/tor_t/<datum>.json` + `.md` und Exportkopie (nur auf sauberem Commit, nie überschreiben) | – | alle |
| `entsperren --grund <K2\|K3\|LOSS_LOCK\|STOP50\|STOP_OUT\|NULLTOLERANZ\|NICHT_DEMO\|ZUSTAND\|SYMBOL:x\|ALLE>` | Sperre mit PIN aufheben | – | **nur Betreiber**, interaktiv |
| `pin-setzen` | PIN festlegen/ändern (≥ 10 Zeichen, scrypt) | – | **nur Betreiber**, interaktiv |
| `installieren --tag <tag>` | `git archive` → `app\<tag>`, `INSTALLATION.json`, Startdateien | – | Betreiber (Wächter ohne Lücke nötig) |
| `starten --tag <tag> [--modus]` | Installation losgelöst starten, wartet auf START (≤ 150 s) | Kind | Betreiber |
| `umziehen [--von <pfad>] [--abschliessen]` | Altablage übernehmen / abgebrochenen Umzug fail-closed abschließen | – | alle |
| `wiederherstellen --aus <zip>` | Sicherung übernehmen (nie überschreiben, Sperren übernehmen) | – | Betreiber |
| `sichern --ziel <ordner> [--mit-schluessel]` | ZIP: Journale, Zustände, Freigaben, Exporte (+ Schlüssel/PIN) | – | Bot-Benutzer/Betreiber; nie Agent; Schlüssel nur interaktiv |
| `trockenlauf [--tage] [--schritt-s]` | kompletter Takt gegen die MT5-Attrappe, beschleunigte Uhr | – | alle |
| `forschung vorab --prereg-ok "…" \| kostenprofil \| entwicklung [--prozesse n] \| pruefen \| aenderung --dateien a,b --grund "…"` (dazu `--lauf`, Standard F-04, wirkt bei `vorab` und `aenderung` – F-05 hat eigene Vorregistrierung, Familien und Werkzeugfamilie –, und `--datum JJJJ-MM-TT`, Standard heute UTC) | Versuchsprotokoll und Entwicklungsauswertung F-04, offline, nur Entwicklungsdaten (§5a, [ARCHITEKTUR.md](ARCHITEKTUR.md) §5a): `vorab` Vorregistrierung vor jeder Datensicht, `kostenprofil` erste Datensicht, `entwicklung` alle Läufe und Bericht, einmal je Familie (`--prozesse` Standard Kerne − 4, mindestens 1), `pruefen` Protokoll prüfen (Befunde und Vollständigkeit aller vorregistrierten Läufe), `aenderung` Werkzeugkorrektur nach der Datensicht eintragen (committete Dateien) | – | Agent/Betreiber |
| `.venv-forschung\Scripts\python.exe -m forschung.runde3 daten \| entwicklung [--datum …] [--prozesse n]` | Runde 3 (F-05b, Richtungsmodell, [ARCHITEKTUR.md](ARCHITEKTUR.md) §5c): `daten` = Datensicht F05B-DATEN, `entwicklung` = Training, Modelle, Takt-Läufe, Bericht `<datum>_runde3`, einmal je Familie | wie runde2 | Agent/Betreiber |
| `.venv-forschung\Scripts\python.exe -m forschung.runde2 daten \| entwicklung [--datum …] [--prozesse n]` (kein kit-Befehl; scikit-learn nur in `.venv-forschung`) | Runde 2 (F-05, [ARCHITEKTUR.md](ARCHITEKTUR.md) §5b): `daten` = Datensicht F05-DATEN (Datensätze je Basis), `entwicklung` = Training, Modelle, Takt-Läufe, Bericht, einmal je Familie | Exit 1 = nicht ausgeführt (Protokoll-, Daten-, Holdout-, Ablagefehler, Datei existiert) | Agent/Betreiber |

**Exit-Codes:**

| Code | Bedeutung |
|---|---|
| 0 | ok, bzw. gewolltes Ende (BEENDEN/Laufzeit) |
| 1 | nicht ausgeführt, FEHLER oder Programmfehler (bei `forschung`: Protokoll-, Daten-, Holdout- oder Ablagefehler) |
| 2 | ohne `--schreiben` bzw. `forschung vorab` ohne `--prereg-ok`, bzw. Sicherheits-Ende des Takts (Demo-Vorrang) |
| 3 | Terminal dauerhaft weg (10 Verbindungsfehler), bzw. Datenabzug unvollständig |
| 4 | MT5 nicht nutzbar (nicht angemeldet, Versatz nicht messbar) |
| 5 | Live/Demo-Prüfung verweigert |
| 6 | Skripte FAIL, Trockenlauf nicht ok bzw. Versuchsprotokoll mit Befunden oder unvollständig (`forschung pruefen`) |
| 7 | Betreiberbefehl in einer Agentensitzung oder ohne Konsole |

Die Autostart-Hülle `bot_dienst.ps1` startet bei 0 und 2 nicht neu. Bei 3, 4 und 5 wartet sie ohne Begrenzung, bei anderen Codes höchstens 10-mal in 6 h.

## 4. Steuerdateien (Kill-Schalter ohne Konsole)

| Datei | Wirkung |
|---|---|
| `<Ablage>\<modus>\STOP` mit `K1`, `K2` oder `K3` | wird jede Sekunde gelesen. K1 vorübergehend, K2/K3 dauerhafte Sperre. Unlesbar oder ohne Stufe = K1. Kodierung egal (UTF-8, UTF-16). `DRILL` im Inhalt legt nur der Bot für Kill-Übungen an. |
| `<Ablage>\<modus>\BEENDEN` | geordnetes Ende im nächsten Takt; Positionen behalten Server-SL/TP |
| `<Ablage>\<modus>\MELDUNGEN.txt` | Ausgabe des Bots: `JJJJ-MM-TT hh:mm:ss STUFE Text` (INFO/WARNUNG/ALARM) |

## 5. Dateien und Formate der Laufzeitablage `%USERPROFILE%\KI-Trading-Bot`

| Pfad | Format |
|---|---|
| `<modus>\journal\JJJJ-MM-TT.jsonl` | ein Satz je Zeile: `{seq, t, art, code, text, daten, prev, h}`. `h` = SHA-256 über den Satz ohne `h`, `prev` = `h` des Vorgängers (Kette ab 64×„0“). Jeder Satz mit `fsync`. Verbotene Schlüssel: login, passw, server, konto, account, investor, email, company, name. |
| Satzarten | START, ENDE, OP_GEPLANT/GESENDET/ERGEBNIS/GEKLAERT/LOKAL_ABGELEHNT, DEAL, ABGLEICH, SPERRE, BOT_SPERRE, BOT_ENTSPERRT, KILL, KILL_FLACH, KILL_AUFGEHOBEN, VORFALL, ANKER, TAGESSTOPP, TECHNIK_PAUSE, PRUEFPUNKT, SIGNAL, SKRIPT; nur im Backtest-Journal (Standard: Arbeitsspeicher): SCHATTEN |
| `<modus>\zustand.json` | `{modus, sperren, tag, tag_anker, loss_anker, tagesstopp_tag, mechanik_hash, strategie_hash}`, atomar geschrieben; fehlt er trotz Journal → Sperre ZUSTAND |
| `freigaben\demo_konten.json` | `{"abdruecke": [...]}` – Allowlist der Demokonten (nur HMAC-Abdrücke) |
| `freigaben\pin.json`, `pin_fehler.json` | scrypt-Salz/-Hash, Fehlversuche |
| `geheim\hmac.key` | 32 Zufallsbytes; ohne ihn passt die Allowlist nicht mehr |
| `marktdaten\entwicklung.sqlite` | Tabellen `abzug(id, gezogen, symbol, zeitrahmen, start, ende, anzahl, erster, letzter, sha256, status)`, `kerze(abzug, zeit, o, h, l, c, spread)`. Kerzenzeiten in **Serverzeit** (der Abzug misst den Versatz nicht; `ziehen` verweigert ein Terminal mit gemessenem Versatz). Die Forschung liest nur über `kit.research.daten.lesen`: Datei schreibgeschützt geöffnet, gebunden an den Abzug der Datensicht (`soll_sha`) bzw. jüngster OK-Abzug, Zeiten mit `versatz_s` (F-04: +3 h aus `config/trade_test.toml`) nach UTC umgerechnet, Anzahl und SHA-256 nachgerechnet (fehlt der Abzug oder passt er nicht → `DatenFehler`); beginnt eine Kerze ab Holdout-Beginn → Abbruch (`HoldoutGesperrt`), beginnt sie davor und endet danach (D1/H4) → verworfen und gezählt (`verworfen_holdout`). In Protokoll und Bericht gehen nur die Kennzahlen des Abzugs (ohne Kurse). |
| `export\<name>-<UTC>.json/.md` | redigierte Exporte (Rauchtest, Skripte, Tor T, Trockenlauf) – für den Agenten lesbar |
| `app\<tag>\` | Installation: `kit\`, `config\`, `requirements\`, `INSTALLATION.json {tag, commit, mechanik_hash, python, installiert}`, `start_probe.cmd`, `start_demo.cmd`, `stop.cmd` |
| `schreiber\LOCK`, `<modus>\LOCK` | Schreibsperren (ein schreibender Bot je Windows-Benutzer) |
| `UMZUG.json` | Umzugsbuch `{status, von, belegt, buch[pfad:sha256], stand{quelle\|modus: seq}, zeit}` |
| `aktiver_tag.txt`, `dienst.log`, `herzschlag_url.txt` | VPS: Tag für den Autostart, Protokoll der Hülle, optionale Ping-URL |

## 5a. Forschungsdateien (F-04, F-05)

| Pfad | Format |
|---|---|
| `forschung/versuchsprotokoll.jsonl` | Versuchsprotokoll im Format von `kit.research.trials`: je Zeile ein Eintrag `{seq, prev, body, hash}` (JSON, Schlüssel sortiert); `hash` = SHA-256(`prev` + kanonisches JSON von `body`), `prev` des ersten Eintrags = 64×„0“. Nur anhängen, bestehende Zeilen werden nie neu geschrieben. Einträge nur über die kit-CLI (`kit forschung`); der Agent-Wächter sperrt Write/Edit der Datei. Bei gebrochener Kette verweigert jedes Anhängen. |
| `body` | Pflicht: `kind`, `actor`, `date` (JJJJ-MM-TT), `family`; bei DATA_VIEW, TRIAL, CHANGE_AFTER_VIEW und HOLDOUT_ACCESS zusätzlich `variant_id`, bei DATA_VIEW und HOLDOUT_ACCESS `split` (F-04: DATA_VIEW und TRIAL tragen `split` = DEVELOPMENT); HOLDOUT_ACCESS außerdem `approval_ref` und `seal_id` (in F-04 nicht benutzt) |
| Arten | `PREREG_SIGNED` (`vorab`): Lauf, Pfad und SHA-256 der Vorregistrierung, Freigabezeile, Commit, `code` {Pfad: SHA-256} der F-04-Dateien, SHA-256 von `tore.toml` und `trade_test.toml`, `mechanik_hash` · `DATA_VIEW` (`kostenprofil`, Familie F04-DATEN, Variante KOSTENPROFIL): Kennzahlen und SHA-256 je Abzug, Name der Datenbank, SHA-256 des Spreadprofils (das Profil selbst nur privat in `config/kostenprofil/f04_spreadprofil.json`), Kostenprofile ohne Swappunkte, SHA-256 der Startwerte · `TRIAL` mit `phase` = `BEGINN` (Parameter, `zaehlt`, `strategie_hash`, Daten-Hashes, Namen der Kostenprofile) bzw. `ERGEBNIS` (Kurzkennzahlen, Name und SHA-256 des JSON-Berichts, Auswahl); beide Phasen zusätzlich Commit, `code`, `mechanik_hash`, SHA-256 von Vorregistrierung, Startwerten und Spreadprofil sowie `seq` der Datensicht · `CHANGE_AFTER_VIEW` (Familie F04-WERKZEUG, Variante `W<n>`, Grund, Commit, neue `code`-Hashes) |
| Familien | `F04-ZIEL-STOP` (12 gezählte Varianten S-REV-01/02), `F04-REFERENZ` (S-BL-01, zählt nie für das Tor), `F04-DATEN` (Datensicht und Kostenprofil), `F04-WERKZEUG` (Werkzeugänderungen nach der Sicht); Runde 2: `F05-META` (4 gezählte Varianten `F05-REV01-LOGREG`, `F05-REV01-HGB`, `F05-REV02-LOGREG`, `F05-REV02-HGB`), `F05-DATEN` (Datensicht der Datensätze), `F05-WERKZEUG`. Jede Runde wird gegen ihre eigene Vorregistrierung und Code-Liste geprüft (`protokoll.runde`); eine Werkzeugänderung erlaubt neue Hashes nur im eigenen Lauf. |
| Prüfung seit F-05 | zusätzlich je Lauf die eigene Vorregistrierung; `NEUSIGNATUR_NACH_SICHT` (PREREG_SIGNED einer Familie nach ihrer Datensicht), `BERICHT_FEHLT/ABWEICHUNG` und `MODELL_FEHLT/ABWEICHUNG` (Dateien eines ERGEBNIS-Eintrags gegen ihren SHA-256; Modelldateien fehlen im öffentlichen Spiegel absichtlich). `vorab --lauf F-05` verlangt in der Freigabezeile „ja“ und den SHA-256 der Vorregistrierung. |
| Einträge F-05b | wie F-05 mit Familien `F05B-RICHTUNG` (4 Varianten `F05B-REV01-LOGREG`, `F05B-REV01-HGB`, `F05B-REV02-LOGREG`, `F05B-REV02-HGB`), `F05B-DATEN`, `F05B-WERKZEUG`; Code-Liste `CODE_F05B` (= `CODE_F05` + Richtungsmodell); Bericht `<datum>_runde3` (Schema `f05b_runde3/1`). |
| Einträge F-05 | `PREREG_SIGNED` (Lauf F-05, SHA-256 von `F05_ENTWURF.md`, `code` = `CODE_F05`) · `DATA_VIEW` F05-DATEN, Variante DATENSATZ: Abzüge der F-04-Datensicht (H1/H4) mit deren `seq`, je Basis Dateiname, SHA-256 und Zählung des Datensatzes (Signale, ohne Merkmale, offen, außerhalb des Handelsfensters, Stop > 3 × Ziel), Merkmalsnamen, Zeitbasis · `TRIAL` F05-META `BEGINN` (Basis, Modell, Hyperparameter, Merkmale, Gitter, Purge/Embargo, Plan, Datensatz-SHA) und `ERGEBNIS` (Kurzkennzahlen, Bericht und dessen SHA-256, Auswahl, Modelldatei und deren SHA-256) |
| Prüfung (`kit forschung pruefen`) | Kette und Regeln (`trials.verify`: keine Datensicht vor der Vorregistrierung, Holdout nie über DATA_VIEW/TRIAL, HOLDOUT_ACCESS nur nach Vorregistrierung und höchstens einmal je Familie), SHA-256 der Vorregistrierung, Commit ist Vorfahr von HEAD und enthält genau die eingetragenen Hashes, Code jedes TRIAL gleich der Vorregistrierung oder durch ein früheres CHANGE_AFTER_VIEW erlaubt, `mechanik_hash` jedes TRIAL gleich der Vorregistrierung (ohne Ausnahme), der committete Stand des Protokolls ist ein Präfix der Datei. Dazu Vollständigkeit (je Familie PREREG_SIGNED, Datensicht F04-DATEN, je Variante TRIAL BEGINN und ERGEBNIS). Urteil VERIFIZIERT, UNVOLLSTAENDIG oder BEFUNDE. |
| `berichte/tor_t/<datum>.json`, `.md`, `<datum>_export.json` | Tor-T-Zertifikat (Schema `tor_t_zertifikat/1`, `kit/gates/zertifikat.py`): nur bei BESTANDEN; Urteil aus dem redigierten Export nachgerechnet; gebunden an `mechanik_hash`, Commit, SHA-256 von `config/tore.toml` und des Exports (byte-gleiche Kopie daneben); Fenster (erster/letzter Satz, UTC), Zählungen, Quote, Skripte, Kill-Stufen, Defekte; Belege aus Trockenlauf/T-SIM/T-PROBE nur mit demselben `mechanik_hash`; wird nie überschrieben |
| `berichte/forschung/<datum>_entwicklung.md` und `.json` | Entwicklungsbericht (JSON-Schema `f04_entwicklung/1`): nur Prozent, R, Anzahlen und Trades je Monat; keine Kurse, Swappunkte und Spreadprofil nur als „privat“ (Spreadprofil mit gekürztem SHA-256); Grenzen und Einordnung im Text; wird nie überschrieben |
| `berichte/forschung/<datum>_runde2.md` und `.json` | Bericht Runde 2 (Schema `f05_runde2/1`): wie der Entwicklungsbericht, dazu Filterwirkung (Entscheidungen und Gewinnquote der Basissignale), Schwellen je Testfenster, Modell- und Datensatz-Parität, Trades je handelbarem Monat, Kandidat mit erwarteten Trades je Monat und Datum für 100 Demo-Trades; nie überschrieben |
| `forschung/modelle/F05/<Variante>.json` | **nicht im öffentlichen Spiegel** (die Modelle enthalten aus dem privaten Spread abgeleitete Werte); eingefrorenes Modell (Schema `meta_filter/1`, kompaktes JSON, floats exakt): Variante, Basis (Name, Parameter), Art, Merkmale, Hyperparameter, Versionen, Datensatz-SHA; je Testfenster `test_von`, `test_bis`, `embargo_bis`, Anpassungs- und Validierungsbeginn, Mengengrößen und Purge-Zählung, Validierung (Kandidaten der Schwelle), `schwelle`, `modell` (LOGREG: `mittel`, `skala`, `koeffizienten`, `achsenabschnitt`; HGB: `basis` und `baeume` mit Knoten [Wert, Merkmal, Schwelle, fehlend_links, links, rechts, Blatt]; jeweils `training` mit den Trainingsgrenzen), Parität; dazu `holdout` (gleicher Aufbau, offenes Fenster) und `paritaet_max`. Nie überschrieben; `kit.strategy.meta_filter.laden` prüft Schema und Basis. |
| `forschung/modelle/F05B/<Variante>.json` | **nicht im öffentlichen Spiegel**; Schema `richtung/1`: wie `meta_filter/1`, je Fenster `modell_kauf` und `modell_verkauf` (gleiche Trainingsgrenzen) und `schwelle` = d* für den Vorsprung; HGB-Bäume kompakt in `baeume_kompakt` (Blatt = Wert, innerer Knoten = [Merkmal, Schwelle, links, rechts, fehlend_links 0/1]); `kit.strategy.richtung.laden` packt verlustfrei aus. |
| `work/f05b/<Basis>.jsonl` | **lokal, nie im Repo**: je handelbarem Punkt Symbol, Kerze, Entscheidungszeit, Basisrichtung, Merkmale `x`, SL/TP für Kauf und Verkauf, `label_k`, `label_v`, Ausstiege beider Richtungen, `t_exit` (späterer), `geometrie` = Stop/(Stop + Ziel) |
| `work/f05/<Basis>.jsonl` | **lokal, nie im Repo** (abgeleitete Kursdaten): je Signal Symbol, Kerze, Entscheidungszeit, Richtung, SL, TP, Einstieg, Merkmale `x`, Label, Ausstieg (Zeit, Grund, Ergebnis), `takt_moeglich`; das Protokoll trägt den SHA-256 |
| `config/trade_test.toml` | Verfahren des Trade-Tests (TOML), eingefroren; Schlüssel in [KONFIGURATION.md](KONFIGURATION.md) |
| `config/kostenprofil/f04_startwerte.json` | **privat** (nicht im Spiegel), Schema `kostenprofil/1`: Kommission gemessen und Gegenprobe je Lot und Seite mit Quelle, Swappunkte (long, short) je Symbol mit Quelle und Grenze, Dreifachtag, Umrechnungsgebühr mit Quelle, SHA-256 der Quelle. Die Swappunkte erscheinen nie in Protokoll oder Bericht (dort „privat“); das Protokoll trägt den SHA-256 der Datei. Die Auswertung nimmt daraus nur Swappunkte und Umrechnungsgebühr (Kommission und Dreifachtag aus `config/trade_test.toml`). |
| `config/kostenprofil/f04_spreadprofil.json` | **privat** (nicht im Spiegel), Schema `spreadprofil/1`, geschrieben von `kit forschung kostenprofil`: Spread je Symbol aus den H1-Kerzen in Points (Median, 10./90. Perzentil, Mittel, Anteil 0, Anzahl Kerzen). Das Protokoll trägt nur seinen SHA-256; `entwicklung` bricht ab, wenn die Datei nicht mehr dazu passt. |
| `<Ablage>\marktdaten\entwicklung.sqlite` | nur lesend über `kit.research.daten.lesen` (§5) |

## 6. Strategie-Schnittstelle (für F-04 ff.)

```python
class Strategie(Protocol):
    name: str; zeitrahmen: str; rueckblick: int; symbole: tuple[str, ...]; max_halte_s: float | None
    def signal(self, symbol: str, kerzen: list[Bar]) -> Signal | None: ...
    def parameter(self) -> dict: ...
Signal(symbol, side, sl, tp, kerze, grund)
```

Die Strategie liefert nur Richtung, SL und TP. Größe, Hebelband, Tagesbudget, Sperren und Ausführung gehören dem Takt. `strategie_hash` (Name, Zeitrahmen, Rückblick, Symbole, Zeitbarriere, alle Felder, Parameter, Quelltext des Moduls) steht im START-Satz. Ein neuer Hash beginnt die Zählung für die Tore 85/95/50 neu.

**F-04-Strategien** (Vorregistrierung `docs/bot/prereg/F04_ENTWURF.md`):

| Strategie | Zeitrahmen | Signal | TP / SL | `max_halte_s` |
|---|---|---|---|---|
| S-REV-01 `rev.MittelwertRueckkehr` | H1 | Schluss fällt erstmals unter SMA − k·σ (n = 48; Vorkerze noch ≥ ihrem Band) → Long; spiegelbildlich Short | TP = e ± ⌈z_tp·ATR / Point⌉ Ticks, SL = e ∓ r · TP-Ticks (Stop/Ziel = r exakt) | 86400 (24 h) |
| S-REV-02 `rev.Fehlausbruch` | H4 | Hoch über dem Spannenhoch der L Kerzen davor, Schluss wieder darunter → Short; spiegelbildlich Long; beides zugleich → kein Signal | TP wie S-REV-01; SL = Extrem der Kerze ± 0,1·ATR, vom Markt weg aufs Raster | 86400 (24 h) |
| S-BL-01 `donchian_ref.run` | D1 | Donchian-Kanalkreuzung, ATR-Anfangsstopp, Nachführung (BL-TFD1) | kein Server-TP → läuft nie über den Takt, zählt nie für Tor 85 | – |

`varianten.varianten()` liefert die feste Reihenfolge: 8 × S-REV-01 (k ∈ {2,0; 2,5}, z_tp ∈ {0,50; 0,75}, r ∈ {2; 3}), 4 × S-REV-02 (L ∈ {20; 40}, z_tp ∈ {0,5; 1,0}), dann S-BL-01; IDs wie `S-REV-01-k2.0-z0.50-r2`.

**Konventionen** (gelten auch für jede neue Strategie):
- **Erwarteter Einstieg e** = Kurs, zu dem Takt und SIM eröffnen: Kauf = Ask = Schluss + Spread · Point, Verkauf = Bid = Schluss (die Kerzen sind Bid-Kerzen). SL und TP werden von e aus gerechnet.
- **Raster:** SL und TP absolut auf dem Tickraster (Tick = Point: 0,001 bei *JPY, sonst 0,00001); Ziel mindestens 1 Tick, Abstände aufgerundet. Preise und Ticks in `Decimal`, Indikatoren in `float` (ATR nach Wilder über das übergebene Fenster).
- **Kein Signal** bei zu kurzem Fenster (< `rueckblick`), ATR ≤ 0 oder nicht endlich; S-REV-01 auch bei σ = 0.
- **Stop/Ziel-Prüfung im Takt:** Rundung, Stops-Level, Stop ≤ 3 × Ziel (`STOP_ZU_ZIEL`), Größe, Band und Budget prüft `Bot.einstieg_strategie`. Die Strategie filtert nicht selbst (S-REV-02 liefert auch Signale mit Stop > 3 × Ziel); die Ablehnung steht als SIGNAL/ABGELEHNT im Journal und zählt in der Quote Signal → Trade.
- **Aufruf:** Der Takt ruft `signal()` einmal je neuer, frischer abgeschlossener Kerze (Schluss höchstens 2 min vor jetzt) mit den letzten `rueckblick` Kerzen; `rev.signale()` bildet das für Tests nach.
- **Zeitbarriere `max_halte_s`:** Der Takt schließt jede Strategieposition per Ticket (Grund ZEITBARRIERE), sobald jetzt − Eröffnung ≥ `max_halte_s`, auch bei Sperren; `None` = nur SL/TP. Im Backtest greift sie beim ersten H1-Schritt, an dem die Bedingung erfüllt ist, nach SL/TP der Kerze dieses Schritts.

**Signaltreue (künftige Schnittstelle, F-07):** `kit.backtest.paritaet.vergleich(takt, direkt)` vergleicht zwei Ereignislisten als Multimengen (Reihenfolge egal, Mehrfache zählen) und liefert `{takt, direkt, gleich, nur_takt, nur_direkt, quote}` mit `quote` = gleich / max(takt, direkt) (1,0 bei zwei leeren Listen) und höchstens 20 Beispielen je `nur_…`. Heute nutzt die Signal-Parität im Backtest diese Funktion; ab F-07 vergleicht sie die Demo-Live-Signale mit dem täglichen Schatten-Backtest.

## 7. Konfiguration und Tore

Siehe [KONFIGURATION.md](KONFIGURATION.md). Die Tor-Schwellen stehen in `config/tore.toml`. Ihr SHA-256 ist in `kit/gates/__init__.py` gepinnt; eine abweichende Datei stoppt den Bot fail-closed.

## 8. Retcodes

`kit/daten/retcodes.json`: 41 MT5-Codes, je Aktion mit Klasse (DONE, PARTIAL, PLACED, NOT_EXECUTED, REJECT_FINAL, UNKNOWN, NOOP_OK, RECONCILE), Wiederholungsregel und Sperrwirkung. Der Inhalt ist identisch mit `referenz/registers/retcodes.json`. Bewusste Abweichungen zur Referenz stehen in `kit_tests/differenz_v4/ABWEICHUNGEN.md`.

## 9. VPS-Skripte und Austausch

- `deploy/windows-vps/*.ps1`: siehe [deploy/windows-vps/README.md](../deploy/windows-vps/README.md). Konfiguration in `vps.config.psd1`.
- Austauschordner `C:\KI-Trading\austausch\`, alle 15 min neu geschrieben: `status_<modus>.txt`, `tor_t_<modus>.txt`. Einzige Quelle für Agent und Monitoring auf dem VPS.
- Herzschlag: HTTPS-GET an die URL in `herzschlag_url.txt`, solange der Status „läuft“ meldet.

## 10. Agent-Wächter (Claude Code Hook)

`.claude/settings.json` ruft vor **jedem** Werkzeugaufruf `py -3.11 -B -I tools/agent_waechter.py` auf. Das Ereignis kommt als JSON auf stdin. Exit 0 erlaubt, Exit 2 verweigert; jede Ausnahme verweigert ebenfalls. Nur der Betreiber ändert Wächter, Einstellungen und Hooks. Details: [SICHERHEIT.md](SICHERHEIT.md).
