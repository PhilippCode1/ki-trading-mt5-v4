# Bewusste Abweichungen des kit-Geldpfads von der v4-Referenz

| Nr | v4 (Konzept) | kit (Fast-Track) | Grund |
|---|---|---|---|
| A1 | SL-/TP-Ausführung des Brokers ohne eigenen Versuch = FOREIGN_ACTIVITY → Integritätssperre, Freigabe nur mit Mitsignatur RF | Server-SL/TP einer eigenen Position (eigener magic) = normaler eigener Ausstieg, kein Halt | Solo-Betreiber (D6); sonst stünde der Bot nach dem ersten Stop dauerhaft |
| A2 | Rückgabecode 0 nicht in der Matrix → UNKNOWN | Code 0 mit Order-/Deal-Ticket und Volumen > 0 = DONE, sonst UNKNOWN | am MetaQuotes-Demo-Server als Erfolg beobachtet (Altprojekt mt5-trading-ai) |
| A3 | R5 Fencing über Writer/Epoche (T15-04, T15-05, T15-14) | Ein-Schreiber-Sperre über Betriebssystem-Lock (`kit/state/store.py:Schreibsperre`) | ein Konto, ein Prozess; der Lock wird bei Prozessende frei |
| A4 | NOT_EXECUTED (z. B. Requote) → sofort NOT_EXECUTED, Reservierung frei | höchstens 3 Versuche in 30 s nach erneuter Prüfung, dann ABGELEHNT | Retry-Regel „NEUER_VERSUCH_NACH_PTC“ der Matrix; Ergebnis von T15-11 bleibt gleich (dauerhafte Ablehnung) |
| A5 | Auftragszuordnung über Kommentar/attempt_id | Auftragskennung als Digest im magic (Präfix + Namensraum) | magic wird vom Server nicht umgeschrieben, der Kommentar schon |
| A6 | Stop-out = BROKER_CLOSEOUT mit Prüfwartezeit (3 Monate) | Stop-out → K2 + Meldung, Betreiber entscheidet | Solo-Betreiber; schweres Ereignis bleibt sichtbar und sperrt Einstiege |

Die übrigen T15-Szenarien (R1–R4, R6, R7) laufen unverändert gegen die Orakel-Erwartungen (`test_t15_unbekannt.py`); das Positionsbuch wird gegen T-14 geprüft (`test_t14_buch.py`); die Retcode-Matrix ist bis auf A2 identisch (`test_retcode_matrix.py`).
