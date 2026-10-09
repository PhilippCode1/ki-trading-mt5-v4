# Kritische Selbstbewertung (Stand F-03f, 06.10.2026)

Ehrliche Einschätzung des technischen Stands. Grundlage sind sechs unabhängige Bestandsaufnahmen und drei Review-Runden. Nur privat.

## 1. Gut – beibehalten

| Bereich | Warum gut |
|---|---|
| **Geldpfad-Design** | Journal vor Netz mit Hashkette und `fsync`, UNBEKANNT statt Neusenden, Negativnachweis, Abgleich mit Broker nach jedem Neustart, Abbau nie durch Sperren blockiert – das sind die Fehlerklassen, an denen Retail-Bots typischerweise scheitern |
| **Demo-Vorrang** | Demo-Prüfung vor jeder Sendung + Gegenprobe, Allowlist per HMAC, Live hart gesperrt; mehrfach per Test und Mutation abgesichert |
| **Testtiefe** | 342 kit-Tests (inkl. hypothesis), T-SIM mit 10.000 Abläufen, Trockenlauf über 7 Tage, Differenztests gegen die unabhängige v4-Referenz (4.405 Kerntests) |
| **Echte MT5-Semantik geprüft** | Deal-Gründe, magic-Erhalt, Retcodes bei `order_check`, Serverversatz – vor dem ersten Trade recherchiert, live bestätigt |
| **Unveränderliche Installation** | Bot läuft aus `app\<tag>` mit `mechanik_hash`-Prüfung; Tor T ist an den Hash gebunden – Messung und Code sind untrennbar |
| **Veröffentlichung** | `publish.py`: Scan, Tests, Commit-Konvention, privater Push, bereinigter Spiegel mit Positivliste und Rescan – fail-closed |
| **Reproduzierbarkeit** | hash-gesperrte Lockfiles, gepinnte GitHub-Actions, `.gitattributes` gegen Zeilenenden-Umwandlung (sonst würde der SHA-Pin von `tore.toml` brechen) |

## 2. Veraltet oder unnötig – in F-03f bereinigt

- Konzeptphase (838 Dateien: Evidenz, 140 ADRs, Validator, 22 Generatoren, 119 Konzepttests, Konzeptdoku, Fremdanbindungen, ungenutzte Referenzmodule) aus dem Arbeitsbaum entfernt, vollständig in den Tags erhalten. Getrackte Dateien: 1.115 → 307.
- Eingefrorene Referenz geschlossen nach `referenz/` (143 Dateien, bytegleich, in sich geschlossen), Repo-Wurzel nur noch lebend.
- Veraltete Aussagen (README-Status F-00, `%LOCALAPPDATA%`-Pfade, Prompt-Dopplung, Laufzeitpfad des Kerntests) korrigiert; drei ruff-Dateilisten durch `ruff check .` ersetzt.
- Neu: Wiederherstellen aus Sicherung, Autostart-Hülle mit Neustart-Regeln, Tagessicherung ohne Konsole, Status-Export, Herzschlag, Windows-CI, `tools/dev.ps1`, VPS-Skripte, vollständige Doku.

## 3. Was noch fehlt (nach Wichtigkeit)

| Fehlt | Warum wichtig | Wann |
|---|---|---|
| Backtester, Kostenmodell, Trade-Test (Tor 85) | ohne sie keine Aussage über eine Strategie | F-04 |
| Strategien + Meta-Filter | Kern des Ziels | F-04/F-05 |
| Auswertung Tor 95 / Demo-Live-Gate, Statusseite | Abschluss der Prompt-Kette | F-07 |
| Push-Benachrichtigungen (ntfy/Telegram-Weiterleiter für `MELDUNGEN.txt`) | Alarm ohne RDP | nach dem VPS-Start |
| Terminal-Build im START-Satz, sitzungsfeste Terminalprüfung | Nachvollziehbarkeit bei MT5-Updates, mehrere Benutzer auf einem VPS | Mechanik-Änderung nach dem Tor-T-Zertifikat |
| Log-Rotation für `konsole.log`/`dienst.log` | Platz über Monate | klein, Bedienbereich |
| `kit sichern` ohne Marktdaten | große, reproduzierbare Datei; aber Forschungsergebnisse hängen am Daten-Hash | bewusst so; Datei separat sichern |

## 4. Was grundsätzlich anders umgesetzt werden sollte

| Heute | Besser | Begründung |
|---|---|---|
| Agent-Schutz vor allem über den Regex-Wächter | **Betriebssystem-Trennung** (eigene Windows-Benutzer, NTFS) – auf dem VPS umgesetzt; Wächter bleibt zweite Schicht | Eine Sperrliste für Befehlstexte ist nie vollständig (drei Review-Runden fanden immer neue Schreibweisen) |
| Melder (Windows-Toast) im Geldpfad | eigener Weiterleiter-Prozess außerhalb der Mechanik | Erweiterungen ohne `mechanik_hash`-Wechsel |
| `start_*.cmd` mit absolutem Pfad zum Repo-`.venv-bot` | Installation bringt eigene Umgebung mit oder liest den Interpreter aus `INSTALLATION.json` | Löschen/Verschieben des Repos legt sonst den Bot lahm |
| drei Entwicklungs-venvs (`.venv-311/312/313`) | eine `.venv` auf Python 3.11 (= Bot-Version) | einfacher; braucht Anpassung der Hooks (nur Betreiber) und von `publish.py` |
| `publish.py pruefen` staged und holt | echter Trockenlauf ohne Seiteneffekte | Erwartung „nur prüfen“ |
| Vermerkprüfung in `publish.py` ignoriert Löschungen (`--diff-filter=ACMR`), der Hook nicht | gleiche Regel an beiden Stellen | sonst Abbruch erst im Hook |
| Toter Parameter `terminal_daten_pfad`, ungelesene Schwellen (`ohne_sl_max_s`, `probe_ohne_untergrenze`), wirkungslose `deviation`-Einstellung | entfernen oder verdrahten | Konfiguration soll nichts versprechen, was der Code nicht tut |
| Kerntests prüfen eine eingefrorene Referenz (4.405 Tests) | auf die von `kit_tests/differenz_v4` und F-04 genutzten Orakel beschränken | weniger Laufzeit; der SHA-Pin der Orakel-Kopien schützt bereits vor Änderungen |

## 5. Wirtschaftliche Einordnung (unverändert gültig)

- Es gibt **keinen belegten Handelsvorteil**. Der Demo-Betrieb beweist Mechanik, nicht Profit.
- Mit Ziel/Stop 1:3 liefert Zufall schon ~75 % Treffer. Deshalb verlangen die Tore zusätzlich einen positiven Erwartungswert nach Kosten, einen Gewinnfaktor ≥ 1,2, eine realisierte Stop/Ziel-Grenze und eine Trefferquote über der Zufallsbasis.
- 85 % auf ≥ 200 Out-of-Sample-Trades sind nur mit einem echten Vorteil erreichbar. 95 % im Demo-Live sind sehr ambitioniert: Eine Strategie mit wahren 93 % besteht das 95-%-Tor nur in ≈ 29 % der Fälle.
- Keine Anlageberatung, keine Gewinnzusage.
