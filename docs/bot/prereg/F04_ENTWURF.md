# Vorregistrierung F-04 – Entwurf (Stand 05.10.2026, vor jeder Datensicht)

Zweck: Alle Strategien, Parameter, Varianten und Zählregeln für die erste Forschungsrunde (Lauf F-04) werden festgelegt, **bevor** irgendein Kursverlauf angesehen wird. Jede Variante zählt als Versuch und geht mit in die Mehrfachtest-Korrektur (DSR). Es zählt nur der Stand mit dem SHA-256, den der Betreiber im Prompt F-04 bestätigt (`PREREG-OK`).

## 1. Gemeinsame Regeln

| Punkt | Festlegung |
|---|---|
| Daten | Entwicklungsperiode 01.01.2010 (bzw. frühester Balken) bis 30.06.2021, MT5-Historie des Demokontos (`kit daten-ziehen`). Der Holdout (01.07.2021–30.06.2026) bleibt ungezogen. |
| Universum | EURUSD, USDJPY, GBPUSD, CHFJPY, CADJPY, AUDUSD, NZDUSD (V7). Ein Symbol fällt nur heraus, wenn `daten-ziehen` dort nicht OK meldet. Der Ausschluss wird vor der Auswertung dokumentiert. |
| Kerzen | Nur abgeschlossene Kerzen (Bid). Signal am Schluss der Kerze t, Ausführung zum nächsten Kurs (Ask für Kauf, Bid für Verkauf) plus Kostenmodell. |
| Ausstieg | Server-SL **und** Server-TP im Eröffnungsauftrag (Pflicht). Zusätzlich gilt je Strategie eine Zeitbarriere (Schließen per Ticket). Keine Nachführung, kein Aufstocken, kein Martingale/Grid. |
| Stop zu Ziel | Geplanter Stop-Abstand ≤ 3 × Ziel-Abstand (D4/V1). Ein Signal, das das verletzt, entfällt. |
| Größe | Takt-Regeln aus `config/tore.toml`: kleinstes Volumen im Korridor 5,25–14,25 (inkl. Kurs = TP ≥ 5,25 und Kurs = SL ≤ 14,25), höchstens eine Strategieposition, Tagesbudget 3 %. Ein Signal ohne zulässige Größe entfällt; es wird gezählt (Quote Signal → Trade). |
| Handelsfenster | 08:00–22:00 Europe/Berlin, Mo–Fr, freitags bis 20:00. Wächter wie im Bot: Spread ≤ 3 × Median, Fehlkurs-Korridor 1 %. |
| Kosten | Kommission 3,25 EUR je Lot und Seite (Startwert `registers/cost_truth.json`, mit dem Rauchtest kalibriert), Spread aus den Kerzen, Swap aus dem Rauchtest (Dreifachtag Mittwoch). Gegenprobe mit Kosten × 1,5 wird berichtet. |
| Zählregeln | wie `config/tore.toml` [zaehlregeln]: Trade = Position von der Eröffnung bis zur vollständigen Schließung; Ergebnis = Summe aller Deals inkl. Kosten; Gewinn nur, wenn > 0. |
| Bewertung | Walk-Forward über die Entwicklungsperiode: Anpassung 3 Jahre, Test 1 Jahr, rollierend. Es zählen nur Trades außerhalb der Anpassung. Alle Kriterien des 85-%-Tors werden je Variante berichtet (`config/tore.toml` [tor_85]). |

**Ehrliche Vorab-Einordnung.** Bei Stop/Ziel = r trifft eine Zufallsrichtung ohne Kosten etwa r/(1+r): bei r = 2 rund 67 %, bei r = 3 rund 75 %. Für 85 % braucht es einen echten Vorteil gegenüber dieser Basis. Die Zufallsbasis wird je Variante mit identischer Ausstiegslogik gemessen (≥ 1.000 Wiederholungen). Wahrscheinlichster Ausgang: kein Kandidat erfüllt alle Kriterien. Das ist ein gültiges Ergebnis.

## 2. S-REV-01 – Rückkehr zum Mittelwert (H1)

| Parameter | Wert / Raster | Bedeutung |
|---|---|---|
| Zeitrahmen | H1 | |
| n (Mittel/Streuung) | 48 | SMA und Standardabweichung der Schlusskurse über 48 Kerzen |
| k (Überdehnung) | **{2,0; 2,5}** | Einstieg Long, wenn der Schluss erstmals unter SMA − k·σ fällt (vorige Kerze noch darüber). Short spiegelbildlich. |
| ATR | Wilder, 14 Kerzen | |
| Ziel z_tp | **{0,50; 0,75}** × ATR | TP = Einstieg ± z_tp·ATR |
| Stop/Ziel r | **{2; 3}** | SL = Einstieg ∓ r·z_tp·ATR |
| Zeitbarriere | 24 Kerzen (24 h) | danach Schließen per Ticket |
| Varianten | 2 × 2 × 2 = **8 Versuche** | |

## 3. S-REV-02 – Fehlausbruch zurück in die Spanne (H4)

| Parameter | Wert / Raster | Bedeutung |
|---|---|---|
| Zeitrahmen | H4 | |
| Spanne L | **{20; 40}** Kerzen | Hoch/Tief der L Kerzen vor t |
| Signal | | Short, wenn das Hoch von t über dem Spannenhoch liegt, der Schluss von t aber wieder darunter (Fehlausbruch). Long spiegelbildlich. |
| ATR | Wilder, 14 Kerzen (H4) | |
| Ziel z_tp | **{0,5; 1,0}** × ATR | |
| SL | Extrem der Kerze t ± 0,1·ATR, höchstens 3 × Ziel-Abstand | sonst entfällt das Signal |
| Zeitbarriere | 6 Kerzen (24 h) | |
| Varianten | 2 × 2 = **4 Versuche** | |

## 4. S-BL-01 – Referenz BL-TFD1 (unverändert, eigene Versuchsfamilie)

Die Semantik bleibt exakt wie in `reference/research/baseline.py`: D1, Einstieg bei Kanalkreuzung, entry_n 55, trail_n 20, atr_n 20, stop_k 2,0, full_bar. Der Signalvergleich läuft gegen `oracles/tfd1_oracle.py`. S-BL-01 ist nur Vergleich und Plausibilitätsanker: Es hat kein Server-TP und erfüllt damit D4 nicht. Es **zählt nie** für das 85-%-Tor und wird nie im Bot gehandelt. **1 Versuch** (eigene Familie).

## 5. Versuchsprotokoll und Auswahl

- `forschung/versuchsprotokoll.jsonl`, nur anhängen, Hashkette. Je Versuch: Commit, Daten-Hash je Symbol/Zeitrahmen, Kostenprofil, Schwellen-Hash (`config/tore.toml`), SHA-256 dieses Dokuments, Parameter, Ergebnisse.
- Gezählte Versuche in Runde 1: 8 + 4 = **12** (Familie Ziel/Stop) und 1 (Familie Referenz). Jede weitere Variante nach einer Datensicht ist ein neuer Versuch mit neuer Vorregistrierung.
- **Auswahlregel** (für F-05/F-06): zulässig sind nur Varianten, die **alle** Entwicklungskriterien des 85-%-Tors erfüllen. Unter ihnen gewinnt die höchste Wilson-95-%-Untergrenze der Trefferquote, bei Gleichstand die Variante mit mehr Trades pro Monat. Erfüllt keine Variante alles, gibt es keinen Holdout-Kandidaten.
- Berichtet werden: Trades, Trades je Monat, Trefferquote mit Wilson-Intervall, Erwartungswert in R mit 95-%-Bootstrap-Untergrenze, Gewinnfaktor, realisiertes Ø-Verlust/Ø-Gewinn, Max-Drawdown vom Hoch, 50-%-Ereignisse, Zufallsbasis (95. Perzentil), Quote Signal → Trade (Band/Budget), DSR mit allen Versuchen, Teilperioden, Kosten × 1,5.

## 6. Grenzen

Kein Blick auf Kurse vor `PREREG-OK`. Keine Holdout-Daten. Kein Sprachmodell im Handelspfad. Strategiecode kommt nach `kit/strategy/`. Der Takt, die Risikoregeln und der `mechanik_hash` bleiben unverändert.

Einordnung: Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.
