---
name: kit-lauf
description: Start- und Abschlussroutine eines Fast-Track-Laufs im Projekt KI-Trading MT5 (Wächter-Probe, Prüfungen, Tests, CHANGELOG/HANDOFF/NEXT_PROMPT, Veröffentlichung mit tools/publish.py). Zu Beginn und am Ende jedes Laufs F-xx, M-xx oder L-xx verwenden.
---

# Laufroutine KI-Trading MT5 (Plan F-1)

Maßgeblich bleiben `CLAUDE.md` und `docs/FAST_TRACK_PLAN.md`. Alles für den Betreiber auf Deutsch.

## Start
1. `echo KIT_WAECHTER_PROBE` ausführen – muss vom Wächter verweigert werden. Wird es ausgeführt: Sitzung läuft nicht im v4-Ordner bzw. ohne Hook → Betreiber melden (außer er hat ausdrücklich autonome Fortsetzung ohne Hook angeordnet; dann im HANDOFF vermerken und die Grenzen aus `CLAUDE.md` selbst strikt einhalten).
2. `git status --porcelain` leer; `git fetch private`; `git rev-parse HEAD private/main` gleich. Im Fork ohne Remote `private`: nur `git status` sauber (Ablauf `docs/ENTWICKLUNG.md` §3).
3. `HANDOFF.md`, oberster Abschnitt in `CHANGELOG.md`, Laufprompt lesen; Freigabezeilen `<…>` prüfen.
4. `.venv-311\Scripts\python.exe -m kit pruefen` (ab F-02 Pflicht ohne FEHLER vor jedem Schreibmodus).

## Arbeit
- Einfachste Variante, die die Abnahme erfüllt. `kit/` importiert nie `referenz/` (reference, oracles, validation), `tools/`, `tests/`.
- Tests laufend: `powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles` (ruff, kit_tests, Kerntests, Scan).
- Doku mitpflegen: `docs/` (Übersicht `docs/README.md`) – Architektur, Schnittstellen, Konfiguration, Betrieb müssen zum Code passen.
- Demo-Teile nur Mo–Fr bei offenem Markt und nur mit `trade_mode == DEMO`.

## Abschluss
1. `CHANGELOG.md`: neuer Abschnitt oben `## <ID> – <Datum> – <Titel>` mit Stichpunkten.
2. `HANDOFF.md` neu (≤ 80 Zeilen: Ergebnis, Prüfstand, offen, nur Betreiber, Risiken).
3. `NEXT_PROMPT.md`: genau ein Folgeprompt aus `docs/bot/PROMPTS.md`, an den echten Stand angepasst.
4. `.venv-312\Scripts\python.exe -B tools/publish.py lauf --lauf <ID> --titel "<Titel>" --oeffentlich` (bei Änderung eingefrorener Pfade zusätzlich `--vermerk "Grund"`). Exit 0 = privat + Spiegel aktuell; 3 = privat ok, Spiegel blockiert (Befunde beheben, `publish.py oeffentlich --lauf <ID>`); 1 = Tor blockiert (nichts gepusht).
   Im Fork stattdessen: Commit `<ID>: …`, `git tag -a lauf/<ID> -m "<ID>"`, `git push --follow-tags`.
5. Abschlussbericht auf Deutsch: Ergebnis, Tests, Commit/Tag, Stand privat/öffentlich, Aufgaben des Betreibers, Folgeprompt als Codeblock.
