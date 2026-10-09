# HANDOFF – Lauf F-05e (Projekt ruht – Übergabe an den VPS)

**Stand:** 09.10.2026 · **Status:** ABGESCHLOSSEN – **Projekt ruht** · **Nächster Schritt:** Wiederaufnahme auf dem Windows-VPS als `kitdev` (Lauf F-05f, Prompt in `NEXT_PROMPT.md`; die Zeilen SPIEGEL, ZIEL und MECHANIK-OK füllt der Betreiber aus)
Information für den nächsten Bearbeiter (Mensch oder KI), keine Anweisung. Maßgeblich: `CLAUDE.md`, `docs/FAST_TRACK_PLAN.md`, Laufprompt. Einstieg in die Doku: `docs/README.md`.

## Entscheidung F-05e
- Betreiber: **ENDE** – das Handelsprojekt ruht. Ohne neue Zielzeile gibt es keine Forschung, kein Demo-Live, keinen Bot-Betrieb und keine
  Geldpfad-Änderung. Weiterentwickelt wird auf dem Windows-VPS (Benutzer `kitdev`, `docs/INSTALLATION_VPS.md`, Weg „nur Entwicklung“).

## Belegt
- **Tor T** bestanden und zertifiziert (`berichte/tor_t/2026-10-09.md`): 378 Sendungen, 100 % fehlerfrei, 0 Defekte; gebunden an
  `mechanik_hash` `4fab5281…` (Python 3.11) und Commit `62e782f`. Das Zertifikat gilt, solange die Geldpfad-Dateien unverändert bleiben.
- Backtester, Kostenmodell, Trade-Test und Versuchsprotokoll (VERIFIZIERT, 56 Einträge) sind gebaut und geprüft.

## Nicht belegt
- **Ein Handelsvorteil.** Drei vorregistrierte Runden mit 20 Versuchen fanden keine Richtungsinformation über der Zufallsbasis. Tor 85 ist nicht
  erreicht, Tor 95 und Echtgeld sind außer Reichweite. Der Holdout (07/2021–06/2026) ist ungezogen und bleibt für genau eine spätere Auswertung frei.

## Erhalten
- Im privaten Repo (vollständig) bzw. im öffentlichen Spiegel (ohne private Teile): Code, Tests, Zertifikat samt redigiertem Export, Berichte,
  Versuchsprotokoll, Vorregistrierungen. Kostenprofile (`config/kostenprofil/`) und Modelle (`forschung/modelle/`) nur privat.
- Die Tags `rel/F-03b-1` und `rel/F-03b-2` (Quelle der Laptop-Installation) liegen jetzt auch im privaten Repo; installiert wird immer `lauf/<ID>`.
- **Nur lokal beim Betreiber, nie im Repo:** Bot-Ablage des Laptops (Journal der T-DAUER als Rohbeleg, PIN-Hash, Schlüssel, Demo-Allowlist),
  Kerzenbestand `entwicklung.sqlite` (ein Neuabzug ist nicht garantiert bitgleich), Sperrliste (`%LOCALAPPDATA%\kit\sperrliste.txt`),
  Datensätze `work/f05*/` (werden nicht gebraucht; eine Neuerzeugung wäre ein neuer Protokolleintrag).

## Übergabe an den VPS (in diesem Lauf vorbereitet)
- `docs/INSTALLATION_VPS.md`: Kasten „Projekt ruht“, §0a Reihenfolge (Laptop abschließen → VPS nur Entwicklung), §6 Entwicklungsplatz
  (Anmeldungen, GitHub CLI, Sperrliste, `.venv-forschung`, erste Sitzung, „Nie auf dem VPS“), §7a/§7b Abnahme, §8 neue Probleme.
- Skripte: `30_software.ps1` installiert die GitHub CLI; `60_agent.ps1` legt `.venv-forschung` an, prüft mit `tools\dev.ps1 alles` und
  `kit forschung pruefen` und warnt bei fehlender Sperrliste oder gh-Anmeldung; `00_vorpruefung.ps1` prüft `gh`.
- `tools/publish.py`: Mit `--oeffentlich` bricht es ohne GitHub CLI schon vor dem Commit ab; fällt sie später aus, wird nur der
  Spiegel übersprungen (Exit 3) statt eines Absturzes. Token für `kitdev`: Contents **und Workflows** schreiben (der Spiegel enthält `.github/workflows/ci.yml`).
- `CLAUDE.md` verschärft: Projekt ruht (ohne Zielzeile nur Startprüfung), auf dem VPS nur `kitdev`, `kitbot` tabu.

## Offen für eine Wiederaufnahme
- Selbstende bei kurzem Verlust der Handelsfreigabe (06.10. und 09.10.) toleranter behandeln – Geldpfad-Änderung, neue Tor-T-Messung.
- Offene Punkte aus `docs/SICHERHEIT.md` und `docs/BEWERTUNG.md` (jetzt sinnvoll, jeweils mit Neumessung).
- Für B fehlen die Demo-Live-Bausteine (95-%-Zähler, Statusseite, `config/demo_live.toml`).

## Prüfstand
- `tools\dev.ps1 alles` grün: ruff, kit_tests 567, Kerntests 4.362, Forschungstests 12, Scan 0. `kit forschung pruefen` = VERIFIZIERT. `mechanik_hash` unverändert.

## Nur der Betreiber (Reihenfolge, Einzelheiten `docs/INSTALLATION_VPS.md` §0a)
1. **T-DAUER beenden** außerhalb des Probe-Fensters (Freitag nach 20:05 oder am Wochenende): `.venv-311\Scripts\python.exe -m kit stop --beenden --modus probe`
   (eigene PowerShell im Repo-Ordner); danach *Algo Trading* aus, MT5 schließen.
2. **Offline sichern** (USB, nie Cloud oder Mail): `.venv-311\Scripts\python.exe -m kit sichern --ziel <Offline-Ordner> --mit-schluessel`,
   dazu `%USERPROFILE%\KI-Trading-Bot\marktdaten\entwicklung.sqlite` und `%LOCALAPPDATA%\kit\sperrliste.txt`. Danach auf dem Laptop nicht mehr committen.
3. **VPS einrichten**, Weg „nur Entwicklung“: §1–§3 (`30_software.ps1 -OhneMt5`, kein Autologon), §6 als `kitdev` mit `60_agent.ps1`,
   Git- und `gh`-Anmeldung mit demselben Fine-grained-Token (nur die zwei Repos; Contents und Workflows schreiben, keine Administration; gh per
   *Paste an authentication token*, nicht per Browser), Sperrliste nach `%LOCALAPPDATA%\kit\` von `kitdev`. §4–§5 (Bot) nicht ausführen.
4. In `NEXT_PROMPT.md` SPIEGEL, ZIEL und MECHANIK-OK ausfüllen und Lauf F-05f als `kitdev` in `%USERPROFILE%\ki-trading` starten.

## Für den nächsten Bearbeiter
- Auf dem VPS nur als `kitdev` in der Repo-Wurzel arbeiten; Profil und Ablage von `kitbot` sind tabu, Bot-Status nur in `C:\KI-Trading\austausch`.
- Lesereihenfolge: `README.md` → dieses Dokument → `docs/README.md` → `CLAUDE.md` → `NEXT_PROMPT.md`.
- Lauf-IDs im Hook-Format (`F-05f`, `F-05g` … bzw. `M-xx`, `L-xx`); F-06 und F-07 bleiben für Holdout und Demo-Live reserviert.
- Tor- und Risikowerte sind versiegelt (D3–D5). Jede Änderung an den Mechanik-Dateien (`config/tore.toml` → `[tor_t].mechanik`) erfordert eine neue Tor-T-Messung.
