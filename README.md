# KI-Trading MT5

Schlanker, sicherheitsorientierter **MetaTrader-5-Bot** in Python (`kit/`). Er handelt ausschließlich auf einem **Demokonto** und muss sich über messbare Tore qualifizieren:

1. **Tor T:** Die Technik arbeitet einwandfrei.
2. **Tor 85:** Ein Backtest mit Holdout schafft ≥ 85 % Gewinntrades.
3. **Tor 95:** Der Demo-Live-Betrieb hält ≥ 95 % Gewinntrades.

Ein laufender Stopp greift bei ≤ 50 %. Echtgeld schaltet ausschließlich der Betreiber.

**Stand (09.10.2026, Lauf F-05e): Das Projekt ruht.**
- Der Bot ist vollständig gebaut, der erste Demo-Trade lief sauber. **Tor T (Technik) ist bestanden:** 378 Orderoperationen auf Demo,
  100 % fehlerfrei, keine Defekte ([Zertifikat](berichte/tor_t/2026-10-09.md)).
- Backtester (derselbe Takt über Historienkerzen), Kostenmodell und Trade-Test (Tor 85) sind gebaut und geprüft.
- Forschungsrunde 1: Keine der 12 vorregistrierten Ziel/Stop-Varianten erfüllt das 85-%-Tor; sie treffen nicht besser als eine zufällige
  Richtung ([Bericht](berichte/forschung/2026-10-08_entwicklung.md)).
- Forschungsrunde 2 (KI-Meta-Filter, 4 Versuche): kein Kandidat. Der Filter hebt die Trefferquote, aber die zufällige Richtung zu denselben
  Zeitpunkten steigt genauso – er findet Marktphasen, keine Richtung ([Bericht](berichte/forschung/2026-10-09_runde2.md)).
- Forschungsrunde 3 (Richtungsmodell, 4 Versuche, letzte nach V9): kein Kandidat; Richtungsvorsprung gegenüber dem Zufall praktisch null
  ([Bericht](berichte/forschung/2026-10-09_runde3.md)).
- Entscheidung nach V9: A (Pause der Strategieforschung, [Vorlage](docs/bot/ENTSCHEIDUNG_V9.md)); danach wurde Tor T zu Ende gemessen
  und zertifiziert.
- **Entscheidung nach Tor T (09.10.2026): ENDE – das Projekt ruht** ([Vorlage](docs/bot/ENTSCHEIDUNG_NACH_T.md)). Belegt ist die Technik,
  nicht belegt ist ein Handelsvorteil; der Holdout ist ungezogen. Der Bot wird nicht weiterbetrieben (T-DAUER beendet der Betreiber, danach läuft kein Bot). Code, Zertifikat, Berichte und Versuchsprotokoll
  bleiben erhalten. Weiterentwickelt wird auf einem Windows-VPS (Benutzer `kitdev`, [INSTALLATION_VPS.md](docs/INSTALLATION_VPS.md) §0a/§6);
  wieder aufgenommen wird nur mit einer Zielzeile des Betreibers ([`NEXT_PROMPT.md`](NEXT_PROMPT.md), Vorlage F-05f).
- Demo beweist Mechanik, nicht Profit. Keine Anlageberatung, keine Gewinnzusage.

## Übernehmen und weiterarbeiten

In dieser Reihenfolge lesen:
1. [`HANDOFF.md`](HANDOFF.md): aktueller Stand, offene Punkte, Hinweise für den nächsten Bearbeiter
2. [`docs/README.md`](docs/README.md): Index der Dokumentation und Glossar
3. [`CLAUDE.md`](CLAUDE.md): harte Grenzen und Laufablauf (gelten für jeden KI-Agenten, nicht nur Claude)
4. [`NEXT_PROMPT.md`](NEXT_PROMPT.md): der nächste Arbeitsauftrag

Danach den Arbeitsplatz einrichten: lokal mit dem Schnellstart unten oder auf dem Windows-VPS als `kitdev` mit `deploy/windows-vps/60_agent.ps1` ([INSTALLATION_VPS.md](docs/INSTALLATION_VPS.md) §6). Für die Forschungstests einmal `tools\dev.ps1 forschung`, dann mit `tools\dev.ps1 alles` prüfen, dass alles grün ist.

**Öffentlich und privat.** Dieses öffentliche Repo ist eine bereinigte Momentaufnahme des privaten Repos des Betreibers (`PUBLIC_SNAPSHOT.md` nennt die Quelle). Es enthält Code, Tests, Werkzeuge, VPS-Skripte und die gesamte Dokumentation. Privat bleiben:
- `docs/bot/privat/`: private Betreibernotizen
- `config/kostenprofil/` (Kostenstartwerte, Spreadprofil) und `forschung/modelle/` (eingefrorene Forschungsmodelle)
- der Großteil von `referenz/`: das eingefrorene Konzeptarchiv mit Betreiberdaten. Öffentlich sind nur die Dateien, die die Differenztests und die Orakel für F-04 brauchen. Die Kerntests der Referenz laufen deshalb nur privat; hier melden sie das und enden ohne Fehler, und mit `privat` markierte Tests werden übersprungen.

Jeder Lauf ersetzt die Momentaufnahme (eine Version ohne Historie). Wer weiterentwickeln will, arbeitet in einem eigenen Fork. Beiträge zurück kommen als Issue oder Patch; der Betreiber übernimmt sie ins private Repo. Für einen eigenen Betrieb in `C:\KI-Trading\vps.config.psd1` die eigene Repo-URL eintragen ([INSTALLATION_VPS.md](docs/INSTALLATION_VPS.md)).

## Schnellstart (Entwicklung)

Voraussetzungen: Windows, Git, Python 3.11 und 3.12 mit `py`-Launcher.
```text
powershell -ExecutionPolicy Bypass -File tools\dev.ps1 einrichten
powershell -ExecutionPolicy Bypass -File tools\dev.ps1 alles
.venv-311\Scripts\python.exe -m kit trockenlauf --tage 7
```
Die Tests brauchen kein MetaTrader 5. Sie nutzen eine SIM-Attrappe des Terminals.

## Aufbau

| Pfad | Inhalt |
|---|---|
| `kit/` | der Bot: Takt, Risiko (Hebelband, Tagesbudget, Sperren), Orderlebenszyklus mit Journal vor Netz, Abgleich, MT5-Adapter, Tore |
| `kit_tests/` | Tests (pytest + hypothesis), inkl. Differenztests gegen die eingefrorene Referenz |
| `config/` | Betriebskonfiguration und eingefrorene Tor-Schwellen |
| `docs/` | Dokumentation – Einstieg [`docs/README.md`](docs/README.md) |
| `berichte/` | redigierte Messberichte (nur %, R, Anzahlen) |
| `tools/` | Veröffentlichung, Geheimnis-Scan, Kerntests, Agent-Wächter, Entwickler-Skript |
| `deploy/windows-vps/` | Einrichtungs- und Betriebsskripte für den Windows-VPS |
| `requirements/` | hash-gesperrte Abhängigkeiten |
| `referenz/` | eingefrorene Referenzimplementierung, nur als Orakel in Tests (öffentlich nur auszugsweise) |

Mehr: [Architektur](docs/ARCHITEKTUR.md) · [Schnittstellen](docs/SCHNITTSTELLEN.md) · [Konfiguration](docs/KONFIGURATION.md) · [Entwicklung](docs/ENTWICKLUNG.md) · [VPS-Installation](docs/INSTALLATION_VPS.md) · [Betrieb](docs/BETRIEB.md) · [Plan](docs/FAST_TRACK_PLAN.md)

## Sicherheit

- Gesendet wird nur auf Konten im Modus DEMO, die in einer lokalen Allowlist stehen. Die Demo-Prüfung läuft vor jeder Sendung. Der Live-Pfad ist hart gesperrt.
- Die Software meldet sich nie an und speichert keine Passwörter. Der Betreiber meldet sich selbst im Terminal an.
- Jede Order wird vor dem Senden ins Journal geschrieben (Hashkette). Unklare Ausgänge werden geklärt, nie blind wiederholt.
- Sperren hebt nur der Betreiber mit PIN auf.
- Keine Zugangsdaten, Kontonummern, Rohdaten oder Benutzerpfade im Repository (Scan vor jedem Commit und vor jeder Veröffentlichung).

**Keine Anlageberatung, keine Gewinnzusage.** Es gibt keinen belegten Handelsvorteil; ein Demo-Betrieb beweist Mechanik, nicht Profit.
