# Nachweise F-03c auf dem Endstand der Vorflug-Korrekturen (05.10.2026)

Beide Nachweise liefen auf dem Code von `lauf/F-03c` (mechanik_hash `4fab5281ae45e39df25fb2c54065ef50a091e0a321c10afec67d0b40f7be3b93` unter Python 3.11). Sie wiederholen die F-03-Nachweise (`2026-10-05_trockenlauf.md`, `2026-10-05_tsim.md`) nach den Vorflug-Korrekturen.

## Trockenlauf – 7 Tage im 1-Sekunden-Takt

**Ergebnis: bestanden** – 0 Defekte, Replay = Laufzeitstand, keine Sperre, keine Meldung.

| Punkt | Wert |
|---|---|
| Zeitraum (simuliert) | Mi 07.10.2026 05:00 UTC bis Mi 14.10.2026 05:00 UTC (5 Handelstage + Wochenende), ein Neustart |
| Takte | 604.800 |
| Rollover | 2026-10-07 ×3 mit offener Position; 2026-10-08 ×1 mit offener Position; 2026-10-09 ×1 mit offener Position; 2026-10-12 ×1; 2026-10-13 ×1 |
| Gesendete Orderoperationen | 3.001 (Eröffnen 1003, Schließen 999, Ändern 999) |
| Fehlerfrei | 3.001 = 100.00% |
| Null-Toleranz-Defekte | 0 |
| Replay aus dem Journal = Laufzeit | ja |

## T-SIM – 10.000 zufällige Abläufe

**Ergebnis: bestanden** – alle Invarianten in allen 10.000 Abläufen (Laufzeit 18:23 min). Inhalt und Invarianten wie in `2026-10-05_tsim.md`.

Einordnung: Beide Nachweise belegen die Mechanik gegen einen simulierten Broker, nicht das Verhalten eines echten Servers und keinen Gewinn. Keine Anlageberatung, keine Gewinnzusage.
