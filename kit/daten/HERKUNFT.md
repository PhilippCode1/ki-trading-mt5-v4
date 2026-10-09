# Herkunft der Daten in kit/daten/

| Datei | Quelle | Stand | SHA-256 |
|---|---|---|---|
| `retcodes.json` | `registers/retcodes.json` (v4, Konzeptphase) | Tag `konzept-c12-wip` | `232840d177ac3bff18e4e8bd9dac73db6a7b026fa47105dce267f013bba68f2c` |

Unverändert kopiert. Abweichende Regel im kit-Code (`kit/orders/retcodes.py`): Rückgabecode `0` gilt nur mit Order- oder Deal-Ticket und Volumen > 0 als Erfolg (am MetaQuotes-Demo-Server beobachtet), sonst UNBEKANNT. Alle 41 Codes sind laut Register belegt, ihre Semantik ist ENTWURF bis zur Prüfung auf dem Demokonto (Killer-Test KT-22).
