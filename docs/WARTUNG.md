# Wartung

Regelmäßige Pflege, damit das System über Monate stabil und reproduzierbar bleibt.

## 1. Kalender

| Rhythmus | Aufgabe | Wer |
|---|---|---|
| täglich | Herzschlag/Status ansehen ([BETRIEB.md](BETRIEB.md) §1) | Betreiber |
| wöchentlich | `kit tor-t --stand`; Platz auf C: (≥ 15 GB frei); `dienst.log` überfliegen | Betreiber (oder Agent über den Austauschordner) |
| Samstag früh | Windows-/MT5-Updates, Neustart, Kontrolle | Betreiber |
| monatlich | Monatscheck-Lauf (Prompt M-xx in `docs/bot/PROMPTS.md`); `git bundle` offline; Sicherungen außer Haus prüfen | Agent + Betreiber |
| vierteljährlich | Wiederherstellungsprobe (§3), Zugangsdaten-Rotation (§4), Abhängigkeits-Update (§5) | Betreiber + Agent |
| bei Ablauf | Demokonto läuft ab → neues Demokonto, `kit konto-registrieren`, neuer Abschnitt im Journal (NOTFALL.md „Kontowechsel“) | Betreiber |

## 2. Platz und Protokolle

- Journale wachsen um einige MB pro Monat (Probe-Mechanik ≈ 1.000 Sätze/Tag); nicht löschen – sie sind die Wahrheit (Sperren, Anker, Tor T).
- `export\` wächst mit jedem `tor-t --stand` (ohne `--ohne-export`) und jedem Rauchtest: ältere Exporte als 90 Tage dürfen gelöscht werden (redigierte Kopien, keine Wahrheit).
- `konsole.log`, `dienst.log`: bei > 50 MB umbenennen (`.alt`), der Bot legt neu an.
- `C:\KI-Trading\sicherung`: räumt die Sicherungsaufgabe selbst auf (30 Tage).

## 3. Wiederherstellungsprobe (vierteljährlich, 15 Minuten)

Als `kitbot`, ohne den laufenden Bot zu stören:
1. Neueste ZIP aus `C:\KI-Trading\sicherung` nehmen.
2. Integrität prüfen: Die Hashkette jedes Journals muss lesbar sein.
```bash
.\.venv-bot\Scripts\python.exe -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); print(z.testzip() or 'ZIP ok', len(z.namelist()), 'Dateien')" C:\KI-Trading\sicherung\<datei>.zip
```
3. Den Wiederherstellungsweg in einer Wegwerf-Umgebung probieren: auf einem Testrechner oder unter einem Test-Benutzer `kit wiederherstellen --aus …`, danach `kit status`.
4. Ergebnis mit Datum in `HANDOFF.md` vermerken (macht der Agent im nächsten Lauf).

## 4. Zugangsdaten rotieren

Alle Passwörter setzt nur der Betreiber; keines steht im Repo.

| Was | Wo | Hinweis |
|---|---|---|
| Windows-Passwörter `kitbot`, `kitdev`, Administrator | Computerverwaltung | nach Änderung bei `kitbot` Autologon neu einrichten |
| GitHub-Token des Bot-Checkouts (nur Lesen) | GitHub → Fine-grained tokens | Ablaufdatum setzen (z. B. 90 Tage); Git-Credential-Manager fragt neu |
| Tailscale | Admin-Konsole | Key-Expiry des VPS bewusst deaktivieren oder erneuern |
| restic/Speicheranbieter | Anbieter | Schlüssel im Passwortmanager |
| PIN | `kit pin-setzen` (alte PIN nötig) | nach Verdacht sofort |

## 5. Abhängigkeiten aktualisieren

- **Entwicklung** (`requirements/dev.in` → `dev.lock.txt`), vierteljährlich:
```bash
uv pip compile requirements/dev.in --universal --generate-hashes -o requirements/dev.lock.txt
```
Danach `tools\dev.ps1 einrichten` und `tools\dev.ps1 alles`. Commit über den normalen Lauf.
- **Bot-Laufzeit** (`requirements/bot-runtime.lock.txt`): Teil des `mechanik_hash`. Nur aktualisieren, wenn nötig, z. B. bei einer neuen `MetaTrader5`-Version für ein neues Terminal-Build. Die Technik-Messung beginnt danach neu. Erst nach dem Tor-T-Zertifikat oder bewusst als neuer Versuch.
```bash
uv pip compile requirements/bot-runtime.in --generate-hashes --python-version 3.11 --python-platform windows -o requirements/bot-runtime.lock.txt
```
- **Python:** Bot auf 3.11, weil das `MetaTrader5`-Wheel 5.0.6090 für cp311 erprobt ist. Ein Wechsel erfolgt nur zusammen mit einem neuen Lock und einer neuen Messung.
- **GitHub Actions:** Die Aktionen sind per Commit-SHA gepinnt. Beim Aktualisieren den neuen SHA aus dem offiziellen Release übernehmen.

## 6. Gesundheit des Repos

```bash
powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles
```
Das führt ruff, kit_tests, Kerntests und den Geheimnis-Scan aus. Zusätzlich prüft die CI bei jedem Push: Linux (Python 3.11 und 3.12), Windows (3.11) und den Scan.
