# Entwicklung und Erweiterung

Für alle, die am Code arbeiten, ob Mensch oder Agent. Regeln für den Agenten: [`CLAUDE.md`](../CLAUDE.md).

## 1. Arbeitsplatz einrichten

Voraussetzungen: Windows, Git, Python 3.11 und 3.12 mit `py`-Launcher. Auf dem VPS erledigt das `deploy/windows-vps/60_agent.ps1` (siehe unten); lokal:
```bash
git clone https://github.com/PhilippCode1/ki-trading-mt5-v4-private.git ki-trading
```
Ohne Zugang zum privaten Repo stattdessen den öffentlichen Spiegel (oder einen eigenen Fork davon):
```bash
git clone https://github.com/PhilippCode1/ki-trading-mt5-v4.git ki-trading
```
```bash
cd ki-trading; powershell -ExecutionPolicy Bypass -File tools\dev.ps1 einrichten
```
Das legt `.venv-311` (kit_tests) und `.venv-312` (ruff, Kerntests, Hooks) aus `requirements/dev.lock.txt` an. Außerdem aktiviert es die Git-Hooks und schaltet die Zeilenendenumwandlung ab. `.venv-bot` mit `MetaTrader5` braucht nur, wer echte MT5-Befehle ausführt (Bot-Benutzer). Für Forschung mit Lernmodellen (ab F-05) legt `tools\dev.ps1 forschung` die `.venv-forschung` (Python 3.11, scikit-learn, hash-gesperrt aus `requirements/forschung.lock.txt`) an und führt ihre Tests aus; `kit/` bleibt Standardbibliothek.

**Auf dem Windows-VPS** (als `kitdev`; solange das Projekt ruht, nur Entwicklung): `deploy/windows-vps/60_agent.ps1` klont das private Repo nach `%USERPROFILE%\ki-trading`, benennt `origin` in `private` um, setzt Hooks und Agent-Identität und legt `.venv-311`, `.venv-312` und `.venv-forschung` an. Danach richtest nur du als `kitdev` in einer eigenen PowerShell ein: die Git-Anmeldung (fine-grained Token nur für das private Repo und den öffentlichen Spiegel: Contents und Workflows lesen/schreiben, Metadata lesen, keine Administration), die GitHub CLI mit `gh auth login` → *Paste an authentication token* mit demselben Token (keine Browser-Anmeldung) und die Sperrliste unter `%LOCALAPPDATA%\kit\sperrliste.txt` (offline übertragen; der Agent darf sie weder lesen noch schreiben). Den Kerzenbestand braucht nur neue Forschung, und zwar in `%USERPROFILE%\KI-Trading-Bot\marktdaten\` von `kitdev`, nie bei `kitbot`. Einzelheiten: [INSTALLATION_VPS.md](INSTALLATION_VPS.md) §6. Dort gilt außerdem:
- Claude Code nur als `kitdev` und nur in der Repo-Wurzel starten, sonst greift der Wächter-Hook nicht.
- `python` liegt nicht im PATH; `kit`-Befehle immer mit `.venv-311\Scripts\python.exe -m kit …`.
- `kit status` und `kit tor-t` zeigen als `kitdev` nur die eigene, leere Ablage. Einen Bot-Stand gibt es nur in `C:\KI-Trading\austausch` (solange das Projekt ruht: kein Bot).

## 2. Tests und Prüfungen

| Befehl | Was | Dauer |
|---|---|---|
| `tools\dev.ps1 test` | kit_tests (~565 Tests, einige `privat`; SIM-Attrappe statt MT5, Backtests nur auf synthetischen Kerzen) | ~3–4 min |
| `tools\dev.ps1 kern` | Kerntests der eingefrorenen Referenz (4.362, schnell ohne t09; aktueller Prüfstand in `HANDOFF.md`) | ~50 s |
| `tools\dev.ps1 lint` | `ruff check .` | Sekunden |
| `tools\dev.ps1 scan` | Geheimnis-/Benutzerpfad-Scan über alle versionierten Dateien | Sekunden |
| `tools\dev.ps1 forschung` | `.venv-forschung` anlegen (falls fehlt) und Tests mit scikit-learn (`kit_tests/test_meta_sklearn.py`) | ~1 min |
| `tools\dev.ps1 alles` | alles zusammen – vor jedem Abschluss (Forschungstests, wenn `.venv-forschung` existiert) | ~6 min |
| `.venv-311\Scripts\python.exe -m kit trockenlauf --tage 7` | ganzer Takt gegen die MT5-Attrappe mit beschleunigter Uhr, 0 Defekte erwartet | ~1 min |

In Tests ist `MetaTrader5` gesperrt (`kit_tests/conftest.py`) und `KIT_HOME` zeigt auf einen Temp-Ordner. Die echte Ablage ist unter pytest unerreichbar. Die langsamsten Tests sind Trockenlauf, Präfix-Test des Runners, Zufallsreferenz und Mutation „Kosten aus“ (je etwa 10–35 s).

**Gegenproben seit F-04** (nur synthetische Kerzen aus `kit_tests/backtest_hilfen.py`, keine Marktdaten):

| Datei | prüft |
|---|---|
| `test_backtest.py` | Kosten mit Handrechnung auf den Cent (EURUSD, USDJPY, Dreifachswap), Geldbilanz, Signal- und Trade-Parität 100 % (H1 und H4), Band je Einstieg, Vorgriffswächter, Schattenereignisse, Zufallsreferenz netto ≈ −Kosten, Mutationen „Kosten aus“ und „Lot aufrunden“, Speicher- = Dateijournal |
| `test_trade_test.py` | Konfig-Pin, Walk-Forward-Fenster, Kennzahlen mit Handwerten, Band-Nachrechnung gegen den Takt (hypothesis), jedes Kriterium einzeln verletzt, Auswahl bei Gleichstand, Zusatzkriterien nur berichtet |
| `test_strategien.py` | S-REV-01/02 Handfälle (auch JPY), Raster und Stop/Ziel, Aufruf wie der Takt, Variantenliste, 12 verschiedene `strategie_hash` |
| `test_forschung_protokoll.py`, `test_forschung_kopien.py` | Versuchsprotokoll: nur anhängen, Manipulation erkannt, `vorab` nur committet und vor der Sicht, Code-Abweichung nach der Sicht, `aenderung_nach_sicht`; Pin der Kopien `stats`/`trials` |
| `differenz_v4/test_backtest_praefix.py` | Runner präfix-invariant nach dem t09-Muster (≥ 200 feindliche Suffixe); Mutation Look-ahead wird erkannt |
| `differenz_v4/test_strategie_orakel.py` | S-BL-01 gleich Orakel `tfd1` und trennscharf; Präfix-Invarianz von S-REV-01/02 und S-BL-01 samt Vorgriff-Mutation; *privat:* bitgleich zur Referenz |
| `test_meta_filter.py` (F-05) | Merkmale gegen eine unabhängige Rechnung (Berliner Zeit, Sommer/Winter, Sonntag), Modelle aus JSON per Handrechnung, Entscheidungen der Hülle, Modellbindung (Mutationen: Modell des Folgefensters, Holdout-Modell in 2021-H1), Schwellenregel, Embargo, Purge über den echten Plan (Mutation ohne Purge erkannt), Kerzen wie im Terminal (H1/H4, Kostenfaktor, Lücken), Signal- und Trade-Parität der Hülle im Takt (H1/H4, Mutation „roher H4-Spread“ erkannt), Paritätsprobe scikit-learn ohne scikit-learn |
| `differenz_v4/test_meta_praefix.py` (F-05) | Datensatz-Bauer präfix-invariant (≥ 200 t09-Suffixe: Signal, SL/TP, Einstieg, Merkmale, Labels mit Ausstieg im Präfix); Lecktest: Fensterschnitt bis i+6 wird erkannt |
| `test_meta_sklearn.py` (F-05, nur `.venv-forschung`) | Laufzeit-Parität ≤ 1e-9 (LOGREG, HGB mit fehlenden Werten), Lecktest über die Validierungsgüte (Zukunftsmerkmal: AUC +0,10 oder mehr), Trainingskette unabhängig von Kursen ab Testbeginn, Wiederholbarkeit, Modelldatei passt zur Hülle, Paritätsprobe `kit_tests/daten/meta_paritaet.json` ist echte scikit-learn-Ausgabe |
| `test_richtung.py` (F-05b) | gespiegelte SL/TP per Handrechnung (auch JPY), Stop/Ziel wie im Takt auch unter dem Raster, „handelbar“, Entscheidungen der Hülle, Modellbindung beider Modelle, verlustfreie kompakte Speicherung, Purge über beide Ausstiege (Mutation nur im Trainer), Signal-/Trade-/Datensatz-Parität im Takt (H1/H4), Zufallspfad-Gegenprobe |
| `differenz_v4/test_richtung_praefix.py` (F-05b) | Datensatz-Bauer der Runde 3 präfix-invariant (H1/H4, ≥ 200 t09-Suffixe), Lecktest Fensterschnitt i+6 |
| `test_richtung_sklearn.py` (F-05b, nur `.venv-forschung`) | Trainingskette unabhängig von Kursen ab Testbeginn bei wirksamem Purge, Wiederholbarkeit, Modelldatei verlustfrei und ladbar, Lecktest über die AUC |
| *privat:* `test_forschung_runde3.py` (F-05b) | Ende-zu-Ende Runde 3 mit Trainer-Attrappe |
| *privat:* `test_forschung_runde2.py` (F-05) | Ende-zu-Ende Runde 2 auf synthetischer Datenbank mit fester Modell-Attrappe: Datensicht, Hash-Bindung, BEGINN/ERGEBNIS, Modelle nie überschrieben, Parität Signal/Trade/Datensatz, private Werte nicht im Bericht, keine zweite Auswertung |
| *privat:* `test_forschung_entwicklung.py`, `differenz_v4/test_kosten_referenz.py`, `differenz_v4/test_kostenprofil_startwerte.py`, `differenz_v4/test_forschung_referenz.py` (dazu je ein privater Test in `test_forschung_protokoll.py` und `differenz_v4/test_strategie_orakel.py`) | Ende-zu-Ende auf synthetischer Datenbank, Datenleser (Hash, Holdout); Kosten, Startwerte und Statistik gegen Referenz und Register |

## 3. Arbeitsablauf („Lauf“)

Jede Arbeitseinheit ist ein **Lauf** mit ID: `F-04`, Korrekturen `F-04b`, Monatscheck `M-01`, Live-Vorlage `L-01`.
1. Start: Wächter-Probe (`echo KIT_WAECHTER_PROBE` muss verweigert werden), `git status` sauber, HEAD = `private/main` (nach `git fetch private`), `tools\dev.ps1 alles` grün (inkl. Forschungstests), `.venv-311\Scripts\python.exe -m kit forschung pruefen` = VERIFIZIERT, `HANDOFF.md`, oberster `CHANGELOG.md`-Abschnitt und Laufprompt lesen. Auf dem VPS zusätzlich `gh auth status` angemeldet.
2. Arbeiten, Tests grün halten.
3. Ende: `CHANGELOG.md` (Abschnitt mit Lauf-ID), `HANDOFF.md` (≤ 80 Zeilen) und `NEXT_PROMPT.md` aktualisieren, dann:
```bash
.venv-312\Scripts\python.exe -B tools\publish.py lauf --lauf <ID> --titel "<Titel>" --oeffentlich
```
`publish.py` macht dabei der Reihe nach:
- Caches säubern und Laufdateien prüfen.
- Scan der geänderten Dateien, danach ruff, kit_tests und Kerntests.
- Commit `<ID>: Titel`, Tag `lauf/<ID>`, Push nach `private` mit Prüfung der Remote-SHA.
- Bereinigten Spiegel erzeugen: Positivliste, Ersetzungen aus der Sperrliste, Null-Toleranz-Rescan, eine Momentaufnahme.

Bei Änderungen in `referenz/` zusätzlich `--vermerk "Grund"`.

**Voraussetzungen für `publish.py`:**
- Remote `private` (URL wie in `tools/repo_regeln.json`) und `core.hooksPath=.githooks`.
- Für `--oeffentlich` zusätzlich die Sperrliste unter `%LOCALAPPDATA%\kit\sperrliste.txt`; fehlt sie, bricht `publish.py` mit Exit 1 vor dem Commit ab.
- Eine angemeldete GitHub CLI (`gh auth status`), denn `publish.py` prüft das Spiegelziel mit `gh api`. Fehlt nur der Spiegel nach dem privaten Push, holt ihn `publish.py oeffentlich --lauf <ID>` nach.
- Lauf-IDs nur im Hook-Format, z. B. `F-05f`, `M-01`, `L-01`.

**Arbeiten im eigenen Fork** (ohne Zugang zum privaten Repo): `publish.py` braucht das private Remote und bleibt dem Betreiber vorbehalten. Im Fork gilt stattdessen:
1. Start: `git status` sauber, `HANDOFF.md` und Laufprompt lesen.
2. Ende: `tools\dev.ps1 alles` grün, Laufdateien wie oben, dann:
```bash
git commit -am "<ID>: <Titel>"
```
```bash
git tag -a lauf/<ID> -m "<ID>"
```
```bash
git push --follow-tags
```
Die Hooks gelten auch im Fork (Titelformat, Scan, ruff); gesperrt ist nur der direkte Push auf den Spiegel des Betreibers.

Commit-Regeln (Hooks):
- Titel `^(F-\d{2}[a-z]?|M-\d{2,3}|L-\d{2}): `
- nie `--no-verify`, nie Force-Push auf `private`
- Identität `KI-Trading v4 Agent <agent@localhost.invalid>`

## 4. Code-Konventionen

- Deutsch für Namen, Meldungen und Doku (Betreiber ist deutschsprachig); Fachbegriffe aus MT5 bleiben englisch.
- Geld und Preise als `Decimal`; `float` nur an der MT5-Grenze.
- Fail-closed: Im Zweifel sperren, nie raten; jede neue Ausnahme im Geldpfad muss zu UNBEKANNT/Sperre führen, nicht zu einem Absturz ohne Journal.
- Journal vor Netz: Nichts wird gesendet, was nicht vorher mit `fsync` geplant wurde.
- Nur Standardbibliothek im Bot. Laufzeit-Abhängigkeiten: `MetaTrader5` und dessen `numpy`.
- `kit` importiert nie `referenz`, `tools`, `tests` (Test `test_struktur`). Gebrauchte Referenzmodule werden als Kopie mit SHA-Pin und Herkunftsnachweis übernommen (`kit/research/HERKUNFT.md`, Pin-Test).
- ruff: Zeilenlänge 160, Regeln E, F, W, B, I, UP. Kein Umformatieren bestehender Dateien.

## 5. Erweitern – typische Fälle

### Neue Strategie (F-04 ff.)
Ablauf wie in F-04. Bausteine: [ARCHITEKTUR.md](ARCHITEKTUR.md) §5a, Formate und Konventionen: [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) §5a und §6.
1. **Vorregistrieren**, bevor irgendwelche Kurse angesehen werden: Strategien, Parameterraster, Familien und Auswahlregel in `docs/bot/prereg/<LAUF>_ENTWURF.md`. Der Betreiber gibt per SHA-256 im Laufprompt frei (`PREREG-OK`); der Code pinnt denselben SHA (F-04: `PREREG_SHA` in `kit/research/protokoll.py`). Jede spätere Änderung zählt als neuer Versuch.
2. **Code:** Klasse nach dem Protokoll `kit.strategy.base.Strategie` unter `kit/strategy/`, Varianten in fester Reihenfolge (wie `varianten.py`). Sie liefert nur Signal, SL und TP, nie Größe oder Ausführung.
3. **Tests vor jeder Datensicht**, nur auf synthetischen Kerzen:
   - Handfälle: Long/Short, JPY-Paar, Raster, Stop/Ziel, kein Signal bei zu kurzem Fenster.
   - Präfix-Test nach dem t09-Muster (`referenz/oracles/t09_causal.py`, in Tests als `oracles.t09_causal`): ≥ 200 feindliche Suffixe; alles bis zum Präfixende (Signale samt Ablehnungen, Trades, Equity) bleibt bytegleich – für die Strategie allein und für den Runner.
   - Differenz gegen ein Orakel, falls vorhanden (S-BL-01 gegen `referenz/oracles/tfd1_oracle.py`).
   - Mutationen, die die Tests erkennen müssen: Kosten aus, Look-ahead (Fenster bzw. Kurs eine Kerze voraus), Lot aufrunden.
   - Parität im Runner: Signal- und Trade-Parität 100 %.
4. **Committen** (alle Dateien aus `CODE_F04`, Mechanik laut `config/tore.toml` [tor_t], Vorregistrierung, `config/trade_test.toml`, Kostenstartwerte; `git status` dieser Dateien leer). Dann über die kit-CLI, in dieser Reihenfolge:
```bash
.venv-311\Scripts\python.exe -m kit forschung vorab --prereg-ok "<Freigabezeile aus dem Laufprompt>"
```
```bash
.venv-311\Scripts\python.exe -m kit forschung kostenprofil
```
```bash
.venv-311\Scripts\python.exe -m kit forschung entwicklung
```
```bash
.venv-311\Scripts\python.exe -m kit forschung pruefen
```
`vorab` geht nur vor der ersten Datensicht, `kostenprofil` ist die erste Datensicht (schreibt das private Spreadprofil `config/kostenprofil/f04_spreadprofil.json`), `entwicklung` rechnet alle Varianten (parallel, `--prozesse n`) einmal je Familie, `pruefen` muss VERIFIZIERT melden (sonst UNVOLLSTAENDIG oder BEFUNDE, Exit 6). `kostenprofil` und `entwicklung` laufen nur nach der Vorprüfung (Protokoll ohne Befund, Code und `mechanik_hash` gleich der Vorregistrierung, Arbeitsbaum sauber).

5. **Bericht** `berichte/forschung/<datum>_entwicklung.md` und `.json` sowie `forschung/versuchsprotokoll.jsonl` mitcommitten (der Bericht wird nie überschrieben); Auswahl nur nach der vorregistrierten Regel. Holdout erst in F-06 mit `HOLDOUT-OK`.
6. Demo-Live erst nach bestandenem Tor 85 (F-06/F-07). `strategie_hash` bindet die Zählung. Beides findet vorerst nicht statt: drei Forschungsrunden ohne Vorteil, Holdout unberührt, Projekt ruht seit 09.10.2026.

**Regel nach der ersten Datensicht:** Die Vorregistrierung trägt die SHA-256 aller F-04-Dateien (`CODE_F04` in `kit/research/protokoll.py`: Backtest, Trade-Test, Strategien samt `base.py`, Forschungsmodule, `kit/cli.py`, `kit/config.py`, `kit/paths.py`, `kit/gates/__init__.py`, `kit/gates/tor_t.py`, die Paket-`__init__.py`, `config/tore.toml`, `config/kit_demo.toml`, `config/trade_test.toml`, Kostenstartwerte) und den `mechanik_hash`. Jede Änderung an einer dieser Dateien ändert ihren Hash: `kostenprofil` und `entwicklung` brechen dann in der Vorprüfung ab, `vorab` verweigert, und ein TRIAL mit abweichendem Code meldet `pruefen` als `CODE_ABWEICHUNG`. Eine Änderung der Mechanik (`mechanik_hash`) lässt sich nach der Sicht gar nicht mehr erlauben (`MECHANIK_ABWEICHUNG`). Erlaubt ist nur:
- reine Werkzeugkorrektur: committen, dann `.venv-311\Scripts\python.exe -m kit forschung aenderung --dateien <a,b> --grund "…"` (`aenderung_nach_sicht`: CHANGE_AFTER_VIEW, Familie F04-WERKZEUG);
- Änderung an Strategie, Parametern oder Bewertung: neue Variante = neuer Versuch mit neuer Vorregistrierung.

### Forschungsrunde mit Lernmodell (F-05 ff.)
Bausteine: [ARCHITEKTUR.md](ARCHITEKTUR.md) §5b, Formate [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) §5a.
1. **Vorregistrieren** wie oben (`docs/bot/prereg/<LAUF>_ENTWURF.md`, `PREREG-OK` mit SHA-256). In `kit/research/protokoll.py` eine eigene Runde ergänzen (`runde`: Vorregistrierung, SHA, Familien, Werkzeugfamilie, Code-Liste inkl. Merkmale, Modell, Schwellenregel und `requirements/forschung.*`); frühere Einträge bleiben unverändert.
2. **Code:** Laufzeitteil nur Standardbibliothek in `kit/` (Hülle, Merkmale, Rechnung aus JSON); Training mit scikit-learn außerhalb von `kit/` (`forschung/`), nur in `.venv-forschung`. Neue Pakete nur hash-gesperrt (`uv pip compile … --generate-hashes`, Installation mit `--require-hashes`).
3. **Gegenproben vor der Datensicht:** Präfix-Invarianz am Datensatz-Bauer (nicht nur an der Merkmalsfunktion), Lecktest als Mutation am Fensterschnitt und über die Validierungsgüte, Purge/Embargo über den echten Plan, Modellbindung, Laufzeit-Parität ≤ 1e-9, Signal-Parität der Hülle im Takt, dazu ein unabhängiges Review (Workflow).
4. **Committen**, dann:
```bash
.venv-311\Scripts\python.exe -m kit forschung vorab --lauf F-05 --prereg-ok "<Freigabezeile aus dem Laufprompt>"
```
```bash
.venv-forschung\Scripts\python.exe -m forschung.runde2 daten
```
```bash
.venv-forschung\Scripts\python.exe -m forschung.runde2 entwicklung
```
```bash
.venv-311\Scripts\python.exe -m kit forschung pruefen
```
5. **Bericht, Modelle und Protokoll** mitcommitten (`berichte/forschung/<datum>_runde2.*`, `forschung/modelle/F05/`, `forschung/versuchsprotokoll.jsonl`); der Datensatz unter `work/f05/` bleibt lokal. Werkzeugkorrekturen nach der Sicht: `.venv-311\Scripts\python.exe -m kit forschung aenderung --lauf F-05 --dateien … --grund "…"`.

### Neuer CLI-Befehl / Bedienfunktion
- In `kit/cli.py`, `kit/bedienung.py` oder `kit/betrieb.py`. Diese Dateien liegen nicht im `mechanik_hash`, das Tor-T-Zertifikat bleibt also gültig.
- Aber: `kit/cli.py` gehört zu `CODE_F04`. Nach der ersten Datensicht einer Forschungsrunde gilt die Regel oben (Änderung nur mit `aenderung_nach_sicht`).
- Betreiberbefehle (Freigaben, PIN, Entsperren) prüfen `_interaktiv()` und landen in der Verbotsliste des Wächters (Patch durch den Betreiber).
- Test in `kit_tests/` und eine Zeile in [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) §3.

### Änderung am Geldpfad (Mechanik)
- Betrifft alles unter `kit/{domain,broker,orders,state,risk,run,probe,daten}/`, `kit/live_guard.py` und `requirements/bot-runtime.lock.txt`.
- Der `mechanik_hash` ändert sich. Damit gilt das Tor-T-Zertifikat ([`berichte/tor_t/2026-10-09.md`](../berichte/tor_t/2026-10-09.md), `4fab5281…`) nicht mehr, und es braucht eine neue Tor-T-Messung. Deshalb:
  - nur mit Grund;
  - Ursachenakte bei Defekten (`docs/bot/defekte/D-<nnn>.md`);
  - Regressionstest;
  - neuer Tag, neue Installation;
  - bewusst nach oder zwischen Messungen.
- Zusätzlich: Trockenlauf und T-SIM müssen 0 Defekte zeigen.
- Seit F-04 steht der `mechanik_hash` auch in der Vorregistrierung: Nach der ersten Datensicht einer Forschungsrunde stoppt eine Mechanik-Änderung `kit forschung kostenprofil|entwicklung` (siehe „Regel nach der ersten Datensicht“).

### Neue Tor-Schwelle
Nur der Betreiber, mit einem Eintrag in `docs/bot/ENTSCHEIDUNGEN.md`. `config/tore.toml` und ihr SHA-256 in `kit/gates/__init__.py` werden gemeinsam geändert. Gilt als neuer Versuch.

### Neue Abhängigkeit
Nur von PyPI, eingetragen in `requirements/*.in` und hash-gesperrt neu kompiliert ([WARTUNG.md](WARTUNG.md) §5). Der Wächter erlaubt `pip install` nur aus `requirements/*.lock.txt`.

### Neuer Betriebsbaustein auf dem VPS (Monitoring, Benachrichtigung …)
- Außerhalb des Geldpfads, als eigener Prozess bzw. eigene Aufgabe.
- Liest nur Exporte, den Austauschordner und `MELDUNGEN.txt`; schreibt nie in die Bot-Ablage außer über `kit`-Befehle.
- Skripte in `deploy/windows-vps/` (ASCII, mehrfach ausführbar, `-WhatIf`), Ideen in [VPS_IDEEN.md](VPS_IDEEN.md).

## 6. Öffentlicher Spiegel

`tools/repo_regeln.json` → `spiegel.positivliste` und `spiegel.ausschluss` bestimmen, was öffentlich wird. Seit F-03g ist das fast alles: Bot, alle Tests, Konfiguration, Berichte, Werkzeuge, VPS-Skripte, CI, Hooks, die gesamte Doku und die Wurzeldateien (`CLAUDE.md`, `HANDOFF.md`, `NEXT_PROMPT.md`). **Nie öffentlich:**
- `docs/bot/privat/**`: private Betreibernotizen
- `referenz/` bis auf die Dateien, die `kit_tests/differenz_v4/` und die F-04-Orakel brauchen (das Konzeptarchiv enthält Betreiberdaten)
- Live-Freigaben in `config/` (gibt es noch nicht; vorsorglich ausgeschlossen)
- Kostenprofile `config/kostenprofil/**` (seit F-04: Kostenstartwerte mit Swappunkten, Spreadprofil der Datensicht). Tests, die sie brauchen, sind `privat` markiert; Berichte nennen Swappunkte und Spreadprofil nur als „privat“, das Versuchsprotokoll nur den SHA-256 der Dateien.
- Eingefrorene Modelle `forschung/modelle/**` (seit F-05: Werte aus dem privaten Spread abgeleitet; das Protokoll trägt ihre SHA-256, `kit forschung pruefen` vermisst sie im Spiegel nicht).
- Datensätze der Lernmodell-Runden `work/**` (gitignored, nie committet: abgeleitete Kurswerte).

Der Rescan blockiert bei Begriffen aus der Sperrliste, weiteren gesperrten Begriffen, Euro-Beträgen ab 1.000, Benutzerpfaden (`C:\Users\<Name>` mit echtem Namen) und Zugangsdaten-Mustern. Im Spiegel (Wurzel trägt `PUBLIC_SNAPSHOT.md`) überspringt `kit_tests/conftest.py` die mit `privat` markierten Tests, und `tools/kerntests.py` endet mit einem Hinweis statt eines Fehlers. Neue Tests, die private Dateien brauchen, bekommen `@pytest.mark.privat`.
