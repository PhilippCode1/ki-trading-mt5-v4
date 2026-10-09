# Rauchtest Demokonto (05.10.2026, 19:31 Berlin) – redigiert

Nur lesend (`kit rauchtest`, 0 × order_check, 0 × order_send). Keine Kontonummer, kein Server- oder Firmenname, keine Kontostände.

## Terminal und Konto

| Punkt | Wert | Bewertung |
|---|---|---|
| Terminal-Build | 6230, verbunden | ok |
| Kontomodus | **DEMO** | Pflicht erfüllt |
| Positionsführung | **HEDGING** | Pflicht erfüllt (Fremdvolumen verschmilzt nicht) |
| Kontowährung | EUR | wie geplant (V8) |
| Hebel | 1:100 | ≥ 1:30 (V8) |
| Serverversatz | +3 h gegenüber UTC (Uhrabgleich fein gemessen) | ok |
| Knopf „Algo Trading“ | beim Rauchtest **aus**, Einschalten durch den Betreiber steht noch aus | ohne ihn keine Sendung |
| Python-API-Sperre (Option) | aus | ok |
| „Max. Balken im Chart“ | zuerst 100.000, danach vom Betreiber auf „Unbegrenzt“ gestellt (100.000.000) | nötig für H1 ab 2010 |
| Umrechnungskurs EUR/USD, EUR/JPY | lesbar (Tickwert-Gegenprobe möglich) | ok |

## Symbolverträge

| Symbol | Stellen | Tick | Tickwert (EUR je Lot) | Kontrakt | Volumen min/Schritt/max | stops_level | Füllart | Handel | Spread (Points) |
|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 5 | 0.00001 | 0.8925 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 1 |
| USDJPY | 3 | 0.001 | 0.5645 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 2 |
| GBPUSD | 5 | 0.00001 | 0.8925 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 0 |
| CHFJPY | 3 | 0.001 | 0.5645 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 7 |
| CADJPY | 3 | 0.001 | 0.5645 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 6 |
| AUDUSD | 5 | 0.00001 | 0.8925 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 1 |
| NZDUSD | 5 | 0.00001 | 0.8925 | 100.000 | 0.01 / 0.01 / 500 | 0 | FOK | FULL | 1 |

Die Spreads am Montagabend sind sehr eng (0–7 Points). Das spricht für ein Konto mit Rohspread und Kommission. Die Kommission je Lot misst die Einzelprobe (Deal-Gebühren). Bis dahin gilt der Startwert 3,25 je Lot und Seite.

## Erster Demo-Trade (05.10.2026, 22:28 Berlin)

`kit probe einzel --schreiben`: EURUSD, 0,01 Lot, Kauf mit SL und TP im Eröffnungsauftrag, danach SL enger, danach Schließen per Ticket.

| Prüfung | Ergebnis | Erwartung (Vorflug-Recherche) |
|---|---|---|
| Eröffnen | ERLEDIGT, Retcode 10009, 218 ms, Ergebnis mit Order- und Deal-Ticket | – |
| SL und TP auf dem Server | beide wie im Auftrag | – |
| magic erhalten (63 Bit) | ja, Position und beide Deals | magic des Auftrags |
| Kommentar erhalten | ja, 28 Zeichen unverändert | evtl. gekürzt |
| SL enger | ERLEDIGT (10009), neuer SL auf dem Server | – |
| Schließen per Ticket | ERLEDIGT (10009), flach | – |
| Abgleich | 0 Differenzen, 0 Fremde, 0 Schutzaktionen | – |
| Deal-Grund Eröffnen/Schließen | **EXPERT** / **EXPERT** | EXPERT ✓ |
| Positions-ID der Deals | = Positionsticket | ✓ |
| Kommission | 0,00 je Deal | Startwert 3,25 je Lot und Seite war vorsichtig |
| Serverversatz / Uhrabweichung PC↔Server | +3 h / 0,05 s | – |

Jede Messung stimmt mit der Vorflug-Recherche überein; eine Ursachenakte war nicht nötig. Dieses Demokonto berechnet keine Kommission, und die Spreads sind sehr eng. Ein Echtgeldkonto kann anders kosten. F-04 kalibriert das Kostenprofil aus Spreads und Swaps; die Gegenprobe mit Kosten × 1,5 bleibt.

## Folgerungen

- Konto und Verträge passen zum Plan. Alle 7 Symbole sind voll handelbar, `stops_level` 0 erlaubt die Probe-Abstände (300 Points) ohne Anpassung.
- Füllart FOK: Teilausführungen sind nicht zu erwarten. D-07 bleibt begründet NICHT_TESTBAR.
- Offen bis zum ersten Demo-Trade: Deal-Grund (erwartet EXPERT), Erhalt von magic und Kommentar, Kommission, Latenz der Deal-Historie.

Einordnung: Der Rauchtest belegt Erreichbarkeit und Verträge, nicht Ausführung oder Gewinn. Keine Anlageberatung, keine Gewinnzusage.
