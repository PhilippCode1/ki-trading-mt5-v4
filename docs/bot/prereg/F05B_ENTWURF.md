# Vorregistrierung F-05b – Entwurf (Stand 09.10.2026, nach F-05, vor jeder Datensicht der Runde 3)

Zweck: Forschungsrunde 3, die letzte nach V9 („höchstens 3 Runden ohne Kandidat, dann entscheidet der Betreiber“). Sie prüft genau die
Lücke, die Runde 2 offengelegt hat: Der Meta-Filter (F-05) hob die Trefferquote der Basissignale, aber die Zufallsbasis (zufällige
Richtung zu denselben Zeitpunkten, gleiche Ausstiegslogik) stieg genauso mit. Er wählte also Zeitpunkte, an denen das Ziel in **beide**
Richtungen leichter erreicht wird, und fand keine **Richtungsinformation** (Abstand Quote − Zufallsmittel −0,9 bis +0,1 Prozentpunkte). Die Ergebnisprüfung zeigte zwei Ursachen: Bei
S-REV-02 wählte er Signale mit weitem Stop im Verhältnis zum Ziel (Geometrie), und Signale, die der Takt nie handelt (Nachtstunden,
Stop > 3 × Ziel), prägten Training und Schwelle mit. Runde 3 lernt deshalb je Zeitpunkt beide Richtungen zu **denselben Abständen**
(die Geometrie hebt sich auf), nutzt **nur handelbare** Zeitpunkte und handelt nur, wenn eine Richtung deutlich besser geschätzt wird.

Alles hier wird festgelegt, bevor die Richtungslabels berechnet oder ein Modell angepasst wird. Es zählt nur der Stand mit dem SHA-256,
den der Betreiber im Prompt F-05b bestätigt (`PREREG-OK`). Jede Variante ist ein gezählter Versuch der neuen Familie **F05B-RICHTUNG**
(eigene DSR-Zählung); F-04 und F-05 bleiben unverändert. Grundlage: Berichte `berichte/forschung/2026-10-08_entwicklung.md` (Runde 1) und
`berichte/forschung/2026-10-09_runde2.md` (Runde 2); beide ohne Kandidat, Holdout ungezogen.

## 1. Gemeinsame Regeln

| Punkt | Festlegung |
|---|---|
| Daten | dieselben Abzüge wie F-04/F-05 (Hashes der F-04-Datensicht, Zeitbasis W1: Serverzeit − 3 h), nur Entwicklungsperiode. Holdout ungezogen. |
| Entscheidungspunkte | Signale der Basisvarianten **S-REV-01-k2.0-z0.75-r3** und **S-REV-02-L40-z0.5** mit genau der Fenster- und Frische-Regel von F-05 (`kit.backtest.paritaet.signal_fenster`, Merkmalsfenster 520 Kerzen), **nur handelbare**: im Handelsfenster des Takts (`kit.risk.guards.im_fenster`) und Stop ≤ 3 × Ziel für beide Richtungen, geprüft wie im Takt (gerundete SL/TP gegen den Einstiegskurs). Nur diese Punkte gehen in Datensatz, Training, Validierung und Schwellenwahl. Die **Richtung der Basis wird nicht übernommen**; sie liefert nur den Zeitpunkt und die Abstände. |
| Ziel und Stop | Abstände des Basissignals in Ticks: Ziel = \|TP − e\|, Stop = \|e − SL\| (e = Einstieg der Basisrichtung). Für jede Richtung gilt Einstieg Ask (Kauf) bzw. Bid (Verkauf) des Schritts, TP = Einstieg ± Ziel, SL = Einstieg ∓ Stop (gleiche Ticks, gespiegelt). Stop ≤ 3 × Ziel wie im Takt. |
| Labels | je Entscheidungspunkt **zwei** Labels: Gewinn Kauf, Gewinn Verkauf = Ergebnis > 0 der direkten Ausstiegsrechnung `kit.backtest.ausstieg.simulieren` (Dreifach-Barriere, Zeitbarriere 24 h, Hauptprofil, 1 Lot). Unabhängig von Konto, Band und Positionsbelegung. |
| Merkmale | wie F-05 (1)–(10), für S-REV-02 zusätzlich (11)/(12) wie in F-05 (bezogen auf die Basisrichtung). Nur Kerzen bis zur Signalkerze. |
| Modelle | je Richtung ein Modell (Kauf, Verkauf) mit den F-05-Einstellungen: (a) logistische Regression (L2, C = 1,0, standardisiert, lbfgs, max_iter 1000); (b) HistGradientBoosting (max_depth 3, learning_rate 0,05, max_iter 200, min_samples_leaf 50, l2 0, early_stopping aus, random_state 0). Training offline in `.venv-forschung`, im Bot nur eingefrorene JSON-Parameter (Parität ≤ 1e-9). |
| Entscheidung | p_K, p_V aus den beiden Modellen; Richtung = größere Schätzung; Vorsprung Δp = p_Richtung − p_Gegenrichtung. Gehandelt wird nur bei Δp > d*. |
| Schwelle d* | je Anpassungsfenster per innerer Validierung wie F-05 (letztes Jahr der Anpassung als Validierung, Modelle auf den zwei Jahren davor): kleinste Schwelle aus {0,00; 0,05; …; 0,40}, deren Validierungs-Trefferquote **der gewählten Richtung** die höchste Wilson-95-%-Untergrenze hat, bei mindestens **50** Validierungssignalen über der Schwelle; danach Modelle auf allen 3 Jahren neu, d* fürs Testjahr. Keine solche Schwelle: im Testjahr keine Trades. |
| Walk-Forward | wie F-05: Anpassung 3 Jahre, Test 1 Jahr (Testfenster 2013 … 2021-H1). Purge: Trainings- und Validierungszeilen nur, wenn **beide** Label-Ausstiege bis zum Ende ihrer Menge liegen. Embargo: 5 Handelstage (Mo–Fr ohne 1.1. und 25.12.) zu Beginn jedes Testfensters. |
| Ausführung | die gewählten Signale (Richtung, gespiegelte SL/TP) laufen durch denselben Takt (`kit/backtest/runner.py`); Band, Budget, Handelsfenster und Positionsgrenze wirken wie im Betrieb. |
| Bewertung | alle Kriterien des 85-%-Tors wie F-04/F-05 (Technik-Kriterium und Datensatz-Parität eingeschlossen); Zufallsbasis = zufällige Richtung zu denselben, gefilterten Einstiegszeiten mit kompletter Ausstiegslogik (≥ 1.000 Wiederholungen) – sie ist hier der eigentliche Prüfstein; Kostenprofile wie F-04 (Haupt, Kosten × 1,5, Kommission 3,25). Der Bericht zeigt je Variante zusätzlich Zufallsmittel, Abstand Quote − Zufallsmittel und den Geometriewert Stop/(Stop + Ziel). |

## 2. Varianten

2 Basen × 2 Modellarten = **4 Versuche** (Familie F05B-RICHTUNG): F05B-REV01-LOGREG, F05B-REV01-HGB, F05B-REV02-LOGREG, F05B-REV02-HGB.
Jede weitere Variante nach einer Datensicht ist ein neuer Versuch mit neuer Vorregistrierung.

## 3. Gegenproben (Pflicht vor der Datensicht)

Wie F-05 (Präfix-Invarianz am Datensatz-Bauer mit ≥ 200 t09-Suffixen für H1 und H4, Lecktest als Mutation am Fensterschnitt und über die
Validierungsgüte, Purge/Embargo gegen den registrierten Plan, Modellbindung, Laufzeit-Parität ≤ 1e-9, Signal-, Trade- und
Datensatz-Parität im Takt), dazu: Handrechnung der gespiegelten SL/TP (Kauf und Verkauf, auch JPY) und eine Gegenprobe auf
synthetischen Kursen ohne Richtungsinformation (Zufallspfad): Wählt die Hülle die Richtung zufällig, liegt ihre Trefferquote im Mittel bei
der Zufallsbasis und das Kriterium „Quote > 95. Perzentil der Zufallsbasis“ ist nicht erfüllt.

## 4. Auswahlregel

Wie F-04/F-05: zulässig sind nur Varianten, die **alle** Entwicklungskriterien des 85-%-Tors erfüllen; unter ihnen die höchste
Wilson-95-%-Untergrenze, bei Gleichstand mehr Trades je Monat. Erfüllt keine alles, gibt es keinen Holdout-Kandidaten. Nach V9 ist das
die letzte Forschungsrunde: Danach entscheidet der Betreiber (weiter forschen mit neuer Idee / Demo-Live bewusst ohne Tor als
Datensammlung / Pause).

## 5. Ehrliche Vorab-Einordnung

Bei S-REV-01 (Stop = 3 × Ziel) trifft eine zufällige Richtung nach Kosten bereits 72–73 % (Zufallsmittel Runde 1: 70,9 %, Runde 2:
72,3–72,9 %); für 85 % fehlen rund 12 Prozentpunkte echter Richtungsvorsprung bei zugleich positivem Erwartungswert. Bei S-REV-02 liegt
die Zufallsquote bei 53–64 %, dort fehlen über 20 Punkte. In zwei Runden lag der gemessene Vorsprung bei −0,9 bis +0,1 Punkten. Dass einfache, kausale
Merkmale auf H1/H4 einen solchen Vorsprung finden, ist sehr unwahrscheinlich; der wahrscheinlichste Ausgang ist wieder „kein Kandidat“.
Die Runde lohnt sich trotzdem als letzter, sauber vorregistrierter Test genau der offenen Frage (Richtung statt Marktphase). Danach
liegt eine klare Grundlage für die Entscheidung des Betreibers vor.

## 6. Grenzen

Kein Blick auf Richtungslabels oder Modellgüte vor `PREREG-OK`. Keine Holdout-Daten. Kein Sprachmodell im Handelspfad. Takt,
Risikoregeln und `mechanik_hash` bleiben unverändert. Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine
Anlageberatung, keine Gewinnzusage.
