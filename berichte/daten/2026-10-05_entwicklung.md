# Datenabzug Entwicklungsperiode (05.10.2026) – nur Kennzahlen

Quelle: MT5-Historie des Demokontos, `kit daten-ziehen` (nur lesend). Zeitraum 01.01.2010–30.06.2021, abgeschlossene Kerzen (Bid). **Korrektur F-04 (08.10.2026):** Die Kerzenzeiten stehen in Serverzeit – der Abzug hat den Serverversatz nicht gemessen und nicht abgezogen (anders als hier zuerst angegeben). Der Server folgt der New-Yorker Sommerzeit (UTC+3 bzw. UTC+2, Wochenöffnung immer Mo 00:00 Serverzeit); die Forschung rechnet beim Lesen mit +3 h nach UTC um.

Je Abzug wird ein SHA-256 gespeichert. Ein Abzug gilt erst, wenn zwei Abrufe denselben Hash liefern. Die Kerzen liegen lokal in `%LOCALAPPDATA%\kit\marktdaten\entwicklung.sqlite` und kommen nie ins Repo. Der **Holdout (ab 01.07.2021) wurde nicht gezogen.**

| Symbol | D1 | H4 | H1 | erster Balken | letzter Balken (H1) | Jahre |
|---|---|---|---|---|---|---|
| EURUSD | 2.984 | 17.871 | 71.257 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| USDJPY | 2.984 | 17.871 | 71.265 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| GBPUSD | 2.984 | 17.871 | 71.260 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| CHFJPY | 2.984 | 17.872 | 71.261 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| CADJPY | 2.978 | 17.842 | 71.211 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| AUDUSD | 2.984 | 17.871 | 71.258 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |
| NZDUSD | 2.984 | 17.871 | 71.243 | 04.01.2010 | 30.06.2021 23:00 | 11,5 |

Status: alle 21 Abzüge **OK**. Keiner ist abgeschnitten, alle haben mehr als 6 Jahre H1.

## Ablauf

1. Erster Lauf mit „Max. Balken“ = 100.000:
   - D1 und H4 wurden gezogen.
   - H1 meldete MAXBARS_ZU_KLEIN. MT5 liefert Historie nur so weit zurück, wie „Max. Balken“ ab heute reicht; ab 2010 sind das rund 108.000 H1-Balken.
   - USDJPY D1 und NZDUSD D1/H4 scheiterten am Terminal („Call failed“, „IPC send failed“), wohl während des Neustarts.
2. Der Betreiber hat „Max. Balken“ auf „Unbegrenzt“ gestellt und MT5 neu gestartet.
3. Zweiter Lauf mit `--fehlende` hat nur das Fehlende gezogen. Ergebnis: alles OK.

Einordnung: Das sind Daten für die vorregistrierte Forschung (F-04, `docs/bot/prereg/F04_ENTWURF.md`), noch keine Auswertung. Keine Anlageberatung, keine Gewinnzusage.
