# Herkunft der kopierten Forschungsmodule in kit/research/ (F-04)

| Datei | Quelle | Stand | SHA-256 Quelle | SHA-256 Kopie |
|---|---|---|---|---|
| `stats.py` | `referenz/reference/research/stats.py` | Tag `konzept-c12-wip` (bytegleich unter `referenz/`) | `d1cab5a9f49ec6bb8bfce6ec59dd550a9aa54ea4cbc9703f228c5020b1feb3ce` | `9f09695c0d906499e763c594eff163542386a628c0723ca850922e1b883d41d5` |
| `trials.py` | `referenz/reference/research/trials.py` | Tag `konzept-c12-wip` (bytegleich unter `referenz/`) | `aa060dd1be7ff699d65d3e03b7c14dd25572040a1c1f063786849689df9ea6a2` | `dde6589aa7da2e13b5275a4c0b39fcebb6f3d656a7cc81ce8a24769975506459` |

Änderungen gegenüber der Quelle:
- je ein dreizeiliger Kommentarkopf mit Herkunft und Quell-SHA vor dem Modul-Docstring;
- `stats.py`: Importzeile `from reference.research import trials` → `from kit.research import trials` (der Bot importiert nie `referenz/`).
- `trials.py`: ein Name aus dem privaten Kontext (Docstring und Wert in `ACTORS`) neutral durch „Assistenz“/`ASSISTENZ` ersetzt, damit der öffentliche Spiegel ihn nicht enthält (F-04, Werkzeugänderung W2 im Versuchsprotokoll; kein Protokolleintrag nutzt diesen Wert).

Sonst bytegleich. Der Pin-Test (`kit_tests/test_forschung_kopien.py`) vergleicht die Kopien mit der Spalte „SHA-256 Kopie“; ein privater Test zusätzlich mit den Originalen unter `referenz/` (Quelle minus Kopf, Importzeile und Namensersetzung = Kopie).

Genutzt für: Wilson-Intervall, DSR (`stats.dsr` mit `trials.dsr_trials`) und das Versuchsprotokoll `forschung/versuchsprotokoll.jsonl` (`trials.append`/`verify`, Hashkette).
