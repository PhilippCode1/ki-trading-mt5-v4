# Vorregistrierung F-05 – Entwurf (Stand 08.10.2026, nach F-04, vor jeder Datensicht der Runde 2)

Zweck: Forschungsrunde 2 mit dem **KI-Meta-Filter** aus Plan F-1 §4 („ein Lernmodell schätzt je Signal die Wahrscheinlichkeit
„Ziel vor Stop“; nur Signale über der Schwelle werden gehandelt“). Alles hier wird festgelegt, **bevor** irgendein Merkmal oder Modell auf
den Kursen gerechnet wird. Es zählt nur der Stand mit dem SHA-256, den der Betreiber im Prompt F-05 bestätigt (`PREREG-OK`). Jede Variante
ist ein gezählter Versuch der neuen Familie **F05-META** (eigene DSR-Zählung); F-04 bleibt unverändert.

Grundlage ist der F-04-Bericht `berichte/forschung/2026-10-08_entwicklung.md` (Runde 1, 12 gezählte Versuche, Holdout ungezogen).
Die Runde-2-Entscheidungen hängen von ihm ab; das ist zulässig, weil jede neue Variante als neuer Versuch zählt (Prereg F-04 §5).

## 1. Gemeinsame Regeln

| Punkt | Festlegung |
|---|---|
| Daten | dieselben Abzüge wie F-04 (Hashes der F-04-Datensicht, Zeitbasis wie F-04 W1: Serverzeit − 3 h), nur Entwicklungsperiode. Holdout ungezogen. |
| Basis-Signale | Signale der F-04-Strategien mit unveränderten Parametern; ausgeführt wird wie in F-04 über den Takt im **Hauptprofil**. Zwei Basisvarianten: je Strategie (S-REV-01, S-REV-02) die F-04-Variante mit der höchsten Wilson-95-%-Untergrenze der Trefferquote im Hauptprofil (OOS), bei Gleichstand mehr Trades je Monat: **S-REV-01-k2.0-z0.75-r3 (Wilson-Untergrenze 68,6 %)** und **S-REV-02-L40-z0.5 (49,2 %)**. |
| Label | je **Signal** der Basisvariante (alle Signale, nicht nur die ausgeführten – unabhängig von Kontostand, Band und Positionsbelegung): Gewinn = Ergebnis der direkten Ausstiegsrechnung `kit.backtest.ausstieg.simulieren` > 0 (Dreifach-Barriere TP, SL, Zeitbarriere 24 h; Einstieg Ask/Bid der Signalkerze; Hauptprofil; 1 Lot; dieselben Regeln wie der Takt, Parität in F-04 = 100 %). |
| Merkmale (nur Kerzen bis zur Signalkerze t, Strategie-Zeitrahmen, float) | (1) Abstand Schluss zum SMA(48) in σ; (2) σ(48)/ATR(14); (3) ATR(14)/Schluss; (4) Perzentil der ATR(14) in den letzten 250 Kerzen; (5) Spread der Signalkerze / ATR(14); (6) Rendite der letzten 24 Kerzen in ATR; (7) Steigung SMA(48) über 12 Kerzen in ATR; (8) Lage des Schlusses in der Spanne der letzten 20 Kerzen (0–1); (9) Stunde der Signalkerze (Berlin, sin/cos); (10) Wochentag (Mo–Fr, 1-aus-5). S-REV-02 zusätzlich: (11) Ausbruchstiefe (Extrem − Spannengrenze)/ATR; (12) Kerzenspanne/ATR. Keine Merkmale aus Kerzen nach t, keine Ergebnisse anderer Trades. |
| Modelle | (a) logistische Regression: L2, C = 1,0, Merkmale auf dem Anpassungsfenster standardisiert, lbfgs, max_iter 1000; (b) HistGradientBoosting: max_depth 3, learning_rate 0,05, max_iter 200, min_samples_leaf 50, l2_regularization 0, early_stopping aus, random_state 0. Training offline in `.venv-forschung` (scikit-learn hash-gesperrt); im Bot nur eingefrorene JSON-Parameter mit Standardbibliothek (Parität ≤ 1e-9). |
| Walk-Forward | wie F-04: Anpassung 3 Jahre, Test 1 Jahr, rollierend (Testfenster 2013 … 2021-H1). **Purge:** Trainings-Signale, deren Label-Ausstieg (Dreifach-Barriere) nach dem Anpassungsende liegt, fallen weg. **Embargo:** 5 Handelstage nach dem Anpassungsende ohne Testtrades. |
| Schwelle | je Anpassungsfenster per innerer Validierung (letztes Jahr der Anpassung als Validierung, Modell auf den zwei Jahren davor): kleinste Schwelle p* aus {0,50; 0,55; …; 0,90}, deren Validierungs-Trefferquote die höchste Wilson-95-%-Untergrenze hat, bei mindestens 20 Validierungssignalen über der Schwelle; danach Modell auf allen 3 Jahren neu, Schwelle p* fürs Testjahr. Gibt es keine solche Schwelle: im Testjahr keine Trades (zählt als „nicht bewertbar“, wenn insgesamt < 200). |
| Ausführung | gefilterte Signale laufen durch denselben Takt (`kit/backtest/runner.py`): Ein abgelehntes Signal ist kein Trade; Positionsfolge, Band und Budget ergeben sich neu. |
| Bewertung | alle Kriterien des 85-%-Tors wie F-04 (`kit/gates/trade_test.py`, Technik-Kriterium eingeschlossen); Zufallsbasis mit den gefilterten Einstiegszeiten und kompletter Ausstiegslogik (≥ 1.000 Wiederholungen); Kostenprofile wie F-04 (Haupt, Kosten × 1,5, Kommission 3,25). |

## 2. Varianten

2 Basisvarianten × 2 Modelle = **4 Versuche** (Familie F05-META). Jede weitere Variante nach einer Datensicht ist ein neuer Versuch mit
neuer Vorregistrierung.

## 3. Lecktest und Gegenproben (Pflicht vor der Datensicht)

- Präfix-Invarianz der Merkmale (Muster t09, ≥ 200 Suffixe).
- Lecktest: ein absichtlich zukünftiges Merkmal (z. B. Rendite der nächsten 6 Kerzen) muss die Validierungsgüte deutlich heben und den
  Lecktest rot machen.
- Purge/Embargo-Test: kein Trainings-Signal (samt Label-Ausstieg) überlappt ein Testfenster.
- Laufzeit-Parität: Wahrscheinlichkeit aus den JSON-Parametern (Standardbibliothek) = scikit-learn ≤ 1e-9.

## 4. Auswahlregel

Wie Prereg F-04 §5: zulässig sind nur Varianten, die **alle** Entwicklungskriterien des 85-%-Tors erfüllen; unter ihnen die höchste
Wilson-95-%-Untergrenze, bei Gleichstand mehr Trades je Monat. Erfüllt keine alles, gibt es keinen Holdout-Kandidaten (Folgelauf F-05b,
höchstens 3 Runden nach V9, danach entscheidet der Betreiber).

## 5. Ehrliche Vorab-Einordnung

F-04 ergab für alle 12 Varianten **keinen Vorteil gegenüber der Zufallsrichtung** (Trefferquote je Variante knapp unter dem Zufallsmittel; beste Basis S-REV-01-k2.0-z0.75-r3: 70,1 % gegen 70,9 %, Erwartungswert in R negativ). Ein Meta-Filter kann nur auswählen, nicht neue Treffer erzeugen: Für das 85-%-Tor müsste er aus ~3.500 Entwicklungs-Trades eine Teilmenge von ≥ 200 Trades mit ≥ 85 % Treffern und positivem Erwartungswert finden, die auch über der Zufallsbasis liegt. Bei Signalen ohne Vorteil ist das sehr unwahrscheinlich; der wahrscheinlichste Ausgang ist wieder „kein Kandidat“. Danach bleibt höchstens Runde 3 (V9), dann entscheidet der Betreiber (weiter forschen / Demo-Live bewusst ohne Tor als Datensammlung / Pause).

## 6. Grenzen

Kein Blick auf Merkmale oder Modellgüte vor `PREREG-OK`. Keine Holdout-Daten. Kein Sprachmodell im Handelspfad. Takt, Risikoregeln und
`mechanik_hash` bleiben unverändert. Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.
