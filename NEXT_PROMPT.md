# NEXT_PROMPT – Lauf F-05f (Wiederaufnahme auf dem Windows-VPS)

**Das Projekt ruht** (Entscheidung ENDE, 09.10.2026). Tor T ist zertifiziert, einen Handelsvorteil gibt es nicht. Weiterentwickelt wird auf dem
Windows-VPS als Benutzer `kitdev`. Diesen Prompt erst verwenden, wenn du dort weiterarbeiten willst. Vorher erledigst du selbst:

1. **Laptop abschließen** (`docs/INSTALLATION_VPS.md` §0a):
   - T-DAUER außerhalb des Probe-Fensters beenden (Freitag nach 20:05 oder am Wochenende).
   - Die nur lokalen Daten offline sichern: `.venv-311\Scripts\python.exe -m kit sichern --ziel <Offline-Ordner> --mit-schluessel`,
     dazu den Kerzenbestand `entwicklung.sqlite` und die Sperrliste.
   - Danach auf dem Laptop nicht mehr committen.
2. **VPS einrichten**, Weg „nur Entwicklung“: §1–§3 mit `30_software.ps1 -OhneMt5` und ohne Autologon, dann §6 als `kitdev` (`60_agent.ps1`).
   Dazu gehören die Git- und GitHub-CLI-Anmeldung mit demselben Fine-grained-Token (§6: Contents und Workflows schreiben, keine Administration,
   gh per Token statt Browser) und die Sperrliste (für jeden Commit nötig, nicht nur für den Spiegel). §4–§5 (Bot) nicht ausführen.
3. **Claude Code** als `kitdev` in `%USERPROFILE%\ki-trading` starten, den Prompt einfügen und **SPIEGEL**, **ZIEL** und **MECHANIK-OK** ausfüllen.
   Es muss kein Markt offen sein. Bleibt ZIEL leer, macht der Agent nur die Startprüfung und sagt dir, was noch fehlt.

```text
Lauf F-05f – KI-Trading MT5: Wiederaufnahme auf dem Windows-VPS (Benutzer kitdev).
Stand: Das Handelsprojekt ruht seit F-05e (09.10.2026, Entscheidung ENDE). Tor T ist bestanden und zertifiziert (berichte/tor_t/2026-10-09.md); einen Handelsvorteil gibt es nicht (drei Runden, 20 Versuche); der Holdout ist ungezogen.
Du übernimmst ohne Vorwissen; alles Nötige steht im Repo. Lies README.md → HANDOFF.md → docs/README.md → CLAUDE.md (die harten Grenzen gelten für jede KI), dann docs/bot/ENTSCHEIDUNGEN.md (Abschnitt Änderungen), docs/bot/ENTSCHEIDUNG_NACH_T.md und docs/INSTALLATION_VPS.md §0a und §6.
Arbeitsordner: Repo-Wurzel (%USERPROFILE%\ki-trading), Windows-Benutzer kitdev.
Startprüfung – schlägt ein Punkt fehl: nichts ändern, kein Commit, mir genau sagen, was ich tun muss:
1. echo KIT_WAECHTER_PROBE muss verweigert werden, sonst sofort abbrechen.
2. Benutzername = kitdev (PowerShell: $env:USERNAME); git status sauber; git fetch private; HEAD = private/main.
3. .venv-311, .venv-312 und .venv-forschung vorhanden; fehlt eine, darfst du sie mit powershell -ExecutionPolicy Bypass -File tools\dev.ps1 einrichten bzw. forschung anlegen (nur lokale venvs, keine Repoänderung).
4. powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles grün, ohne den Hinweis „.venv-forschung fehlt“; .venv-311\Scripts\python.exe -m kit forschung pruefen = VERIFIZIERT.
5. .venv-311\Scripts\python.exe -B -c "from kit.gates.tor_t import mechanik_hash; print(mechanik_hash()[:8])" = 4fab5281 (sonst gilt das Tor-T-Zertifikat für diesen Code nicht).
6. Sperrliste und GitHub CLI: .venv-312\Scripts\python.exe -B tools\publish.py pruefen --oeffentlich ohne Befund (prüft die Sperrliste über das Werkzeug, ohne dass du sie liest, und ob gh vorhanden ist). Fehlt die Sperrliste: kein Commit, mich bitten. Fehlt nur gh und SPIEGEL = nein: weiter, nur privat veröffentlichen. Bei SPIEGEL = ja zusätzlich gh auth status angemeldet. Nichts davon selbst anlegen (INSTALLATION_VPS.md §6).
Grenzen: kein MT5; den Bot weder starten noch stoppen; keine Aufgabenplanung; nichts im Profil oder in der Ablage von kitbot; Bot-Status nur aus C:\KI-Trading\austausch, falls vorhanden. Kein Echtgeld, kein Demo-Live; Tor- und Risikowerte bleiben versiegelt (D3–D5); der Holdout bleibt ungezogen; der mechanik_hash ändert sich nur mit MECHANIK-OK = ja.
SPIEGEL: <ja | nein = nur privat veröffentlichen>
ZIEL: <B – Demo-Datensammlung ohne Tor vorregistrieren | C: neue Idee in einem Satz | BOT-VPS – Bot unter kitbot vorbereiten, ohne Start | TECHNIK – offene Technikpunkte | ANDERES: in einem Satz>
MECHANIK-OK: <nein | ja = Geldpfad-Änderungen erlaubt, danach ist eine neue Tor-T-Messung nötig>

Aufgaben:
1. ZIEL leer: nur Startprüfung, kein Commit; Ergebnis berichten und diesen Prompt erneut ausgeben.
2. Ziel mit Datum in docs/bot/ENTSCHEIDUNGEN.md eintragen (Abschnitt Änderungen, „Betreiber im Laufprompt F-05f“).
3. B: docs/bot/prereg/DEMO_DATEN_ENTWURF.md mit SHA (Variante mit Begründung, Regeln, Abbruchkriterien, Messgrößen Signaltreue/Ist-Kosten/Ausführung, Dauer, Kennzeichnung „ohne Tor 85 – führt nie zu Echtgeld“) und Plan der Demo-Live-Bausteine; kein Start.
   C: docs/bot/prereg/F05C_ENTWURF.md (eigene Informationsquelle, Familie, Versuche, Gegenproben, Auswahlregel wie F-04/F-05, ehrliche Einordnung gegen die drei Runden); keine Datensicht (PREREG-OK im Folgeprompt). Die Anleitung zum Kerzenbestand (INSTALLATION_VPS.md §6) immer mitgeben; ob er vorhanden ist, bestätige ich (du prüfst die Ablage nicht).
   BOT-VPS: Checkliste für mich nach docs/INSTALLATION_VPS.md §4–§5; kein Start, keine Aufgabe.
   TECHNIK: Entwurf je offenem Punkt (Ursache, Änderung, Test, Folge für den mechanik_hash); umsetzen nur mit MECHANIK-OK = ja.
   ANDERES: Plan und Übergabe nur in diesem Repo; nichts außerhalb anlegen.
4. Status „Projekt ruht“ in README.md, HANDOFF.md, docs/README.md, der FAST_TRACK_PLAN-Statuszeile und allen Kästen „Projekt ruht“ in docs/ und deploy/windows-vps/README.md durch den neuen Stand ersetzen; NEXT_PROMPT.md aus der passenden Vorlage ableiten.
Abnahme: Startprüfung grün; Ziel eingetragen; mechanik_hash unverändert (außer bei MECHANIK-OK); tools\dev.ps1 alles grün.
Abschluss: .venv-312\Scripts\python.exe -B tools\publish.py lauf --lauf F-05f --titel "Wiederaufnahme auf dem VPS" --oeffentlich (bei SPIEGEL = nein ohne --oeffentlich). Exit 3 = privat erledigt, Spiegel blockiert; Exit 2 oder 4: nicht wiederholen, sondern melden. Bericht auf Deutsch und passender Folgeprompt.
```
