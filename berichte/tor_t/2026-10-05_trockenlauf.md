# Trockenlauf F-03 – 7 Tage im 1-Sekunden-Takt (05.10.2026)

**Ergebnis: bestanden** – 0 Defekte, Replay = Laufzeitstand, keine Sperre, keine Meldung.

| Punkt | Wert |
|---|---|
| Zeitraum (simuliert) | Mi 07.10.2026 05:00 UTC bis Mi 14.10.2026 05:00 UTC (5 Handelstage + Wochenende) |
| Takte | 604.800 (1 s) |
| Weg | echter Adaptercode (`kit/broker/mt5_real.py`) über die MT5-Attrappe auf dem SIM-Terminal, Serverzeit UTC+3 |
| Betrieb | Probe-Mechanik (3 Symbole) und Attrappen-Strategie gleichzeitig, ein Prozessneustart nach 2,3 Tagen |
| Rollover | 2026-10-07 ×3 mit offener Position; 2026-10-08 ×1 mit offener Position; 2026-10-09 ×1 mit offener Position; 2026-10-12 ×1; 2026-10-13 ×1 |
| mechanik_hash | `9017eec4ea4f46472371ff9ad392a1ca055546d25bdc7bca6f5b0c2641b992b0` (Fenster ab dem ersten Start) |
| Gesendete Orderoperationen | 3.001 (Eröffnen 1003, Schließen 999, Ändern 999) |
| Fehlerfrei | 3.001 = 100.00% |
| Absicht → Operation | 100.00% |
| Null-Toleranz-Defekte | 0 |
| Strategie-Trades (Attrappe) | 4 |
| Replay aus dem Journal = Laufzeit | ja |
| Abgleichdifferenzen | 0 |

Einordnung: Der Trockenlauf belegt die Mechanik gegen einen simulierten Broker (Zufallspfad, Attrappen-Strategie). Er ersetzt weder die Demo-Messung (T-PROBE/T-DAUER, F-03b) noch sagt er etwas über Gewinn. Das Tor-T-Urteil „BESTANDEN“ gilt hier nur für den SIM; das Tor T selbst wird auf dem Demokonto gemessen. Keine Anlageberatung, keine Gewinnzusage.
