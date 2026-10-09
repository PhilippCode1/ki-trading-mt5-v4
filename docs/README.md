# Dokumentation – Übersicht

Einstieg für alle, die das Projekt übernehmen, betreiben oder weiterentwickeln. Reihenfolge zum Einlesen: 1 → 2 → 3, dann nach Bedarf. Alles hier ist öffentlich, außer den mit *(privat)* markierten Einträgen. **Stand:** Das Projekt ruht seit 09.10.2026 (Lauf F-05e); weiterentwickelt wird auf dem Windows-VPS. Einzelheiten in `HANDOFF.md`.

| # | Dokument | Für wen | Inhalt |
|---|---|---|---|
| 1 | [ARCHITEKTUR.md](ARCHITEKTUR.md) | alle | Was das Projekt ist, Grundsätze, Komponenten, Takt, Backtest und Trade-Test, Zielbetrieb, Release-Modell, Repo-Struktur |
| 2 | [INSTALLATION_VPS.md](INSTALLATION_VPS.md) | Betreiber | Windows-VPS Schritt für Schritt: Entwicklungsplatz (`kitdev`), optional Demo-Bot (`kitbot`) und Umzug vom Laptop, Abnahme, Probleme |
| 3 | [BETRIEB.md](BETRIEB.md) | Betreiber | täglicher Blick, Start/Stopp, neue Version, Updates, Sicherung, Überwachung |
| – | [bot/NOTFALL.md](bot/NOTFALL.md) | Betreiber | Kill-Stufen, Algo-Trading-Knopf, Entsperren mit PIN, Kontowechsel |
| 4 | [WARTUNG.md](WARTUNG.md) | Betreiber, Agent | Kalender, Platz, Wiederherstellungsprobe, Zugangsdaten, Abhängigkeiten |
| 5 | [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) | Entwickler | MT5-Adapter, Auftragskennung, CLI + Exit-Codes, Steuerdateien, Dateiformate (Ablage, Forschung), Strategie-Protokoll und F-04-Strategien |
| 6 | [KONFIGURATION.md](KONFIGURATION.md) | Entwickler, Betreiber | `kit_demo.toml`, `tore.toml`, `trade_test.toml`, Kostenprofil, VPS-Konfiguration, Umgebungsvariablen |
| 7 | [ENTWICKLUNG.md](ENTWICKLUNG.md) | Entwickler | Arbeitsplatz, Tests, Laufablauf, Konventionen, Erweitern (Strategie, Befehl, Mechanik, Tore) |
| 8 | [SICHERHEIT.md](SICHERHEIT.md) | alle | Bedrohungsmodell, Schutzschichten, offene Punkte, Vorfall |
| 9 | [BEWERTUNG.md](BEWERTUNG.md) | Entscheider | kritische Selbstbewertung: gut, fehlt, anders umsetzen |
| 10 | [VPS_IDEEN.md](VPS_IDEEN.md) | Betreiber | priorisierte Ideen für den VPS-Betrieb |
| – | [FAST_TRACK_PLAN.md](FAST_TRACK_PLAN.md) | alle | der maßgebliche Plan F-1 (Tore, Läufe, Regeln); öffentliche Kurzfassung [PLAN_OEFFENTLICH.md](PLAN_OEFFENTLICH.md) |
| – | [bot/ENTSCHEIDUNGEN.md](bot/ENTSCHEIDUNGEN.md) | alle | verbindliche Entscheidungen des Betreibers D1–D9, V1–V10 |
| – | [bot/ENTSCHEIDUNG_V9.md](bot/ENTSCHEIDUNG_V9.md) | Betreiber | Entscheidungsvorlage nach drei Forschungsrunden ohne Kandidat (Fakten, Optionen, Empfehlung); entschieden am 09.10.2026: A |
| – | [bot/ENTSCHEIDUNG_NACH_T.md](bot/ENTSCHEIDUNG_NACH_T.md) | Betreiber | Entscheidungsvorlage nach dem Tor-T-Zertifikat (Ende / Datensammlung ohne Tor / neue Idee); entschieden am 09.10.2026: ENDE |
| – | [bot/PROMPTS.md](bot/PROMPTS.md) | Betreiber | Vorlagen der Laufprompts, inkl. Wiederaufnahme nach ENDE (F-05f) |
| – | [`../deploy/windows-vps/README.md`](../deploy/windows-vps/README.md) | Betreiber | Reihenfolge der VPS-Skripte |
| – | `../referenz/README.md` | Entwickler | eingefrorene Referenz, nur Orakel für Tests *(privat; öffentlich nur die von den Tests gebrauchten Dateien)* |
| – | `bot/privat/` | Betreiber | Betreibernotizen *(privat)* |

Laufende Stände stehen in der Repo-Wurzel: `HANDOFF.md` (aktueller Stand, offene Punkte), `CHANGELOG.md` (je Lauf), `NEXT_PROMPT.md` (nächster Lauf). Messberichte liegen in `berichte/`.

## Glossar

| Begriff | Bedeutung |
|---|---|
| **kit** | der Bot (Python-Paket `kit/`, Aufruf `python -m kit`) |
| **Ablage** | Laufzeitdaten des Bots unter `%USERPROFILE%\KI-Trading-Bot` (Journal, Zustand, Sperren, PIN, Schlüssel, Kerzen, Exporte, Installationen) |
| **Journal** | Append-only-Protokoll (JSONL, Hashkette) – die Wahrheit des Bots |
| **Takt** | Hauptschleife `kit/run/loop.Bot` (1 s Dateien, ≤ 5 s Schutz, 1 min Handel) |
| **Mechanik / `mechanik_hash`** | die 38 Geldpfad-Dateien und ihr SHA-256; bindet die Technik-Messung |
| **`strategie_hash`** | Hash einer Strategie (Name, Parameter, Quelltext); bindet die Trefferquoten-Tore |
| **Tor T / 85 / 95 / 50** | Technik fehlerfrei / Trade-Test 85 % / Demo-Live 95 % / Stopp bei ≤ 50 % |
| **T-SIM, T-PROBE, T-DAUER** | Technik-Messung in Simulation / beaufsichtigt auf Demo / Dauerlauf auf Demo |
| **Probe** | Namensraum für Technik-Messungen mit kleinstem Volumen (zählt nie für Trefferquoten) |
| **K1 / K2 / K3** | Kill-Stufen: keine Einstiege (vorübergehend) / dauerhaft / dauerhaft + alles flach |
| **LOSS_LOCK** | Sperre bei 25 % Verlust vom Anker; Aufheben nur mit PIN |
| **Hebelband** | erlaubter Buchhebel 5–15 (Einstiegskorridor 5,25–14,25) |
| **UNBEKANNT** | Ausgang einer Sendung unklar; wird geklärt, nie blind neu gesendet |
| **Negativnachweis** | nach 60 s ohne passenden Deal gilt eine UNBEKANNT-Operation als nicht ausgeführt |
| **magic** | MT5-Auftragsnummer; enthält Namensraum und Auftragskennung |
| **Allowlist** | `freigaben\demo_konten.json` – nur dort eingetragene Demokonten (HMAC-Abdruck) dürfen beschrieben werden |
| **Wächter** | Claude-Code-Hook `tools/agent_waechter.py`, verweigert dem Agenten gefährliche Werkzeugaufrufe |
| **Lauf** | Arbeitseinheit mit ID (F-04, M-01 …), endet mit `publish.py lauf` |
| **Spiegel** | bereinigte öffentliche Momentaufnahme des privaten Repos |
| **Referenz** | eingefrorene v4-Implementierung der Konzeptphase unter `referenz/`, nur Orakel |
| **PREREG** | Vorregistrierung einer Strategie vor jeder Datensicht (SHA-256-gebunden) |
| **Holdout** | einmalig auszuwertender Datenzeitraum 07/2021–06/2026 |
| **Versuchsprotokoll** | `forschung/versuchsprotokoll.jsonl` – nur anhängbares Protokoll aller Forschungsversuche mit Hashkette; jede angesehene Variante zählt; Einträge nur über `kit forschung` |
| **KI-Meta-Filter** | Hülle um eine Basisstrategie (F-05): ein Lernmodell schätzt je Signal die Wahrscheinlichkeit „Ziel vor Stop“, gehandelt wird nur über der Schwelle; Training offline mit scikit-learn, im Bot nur eingefrorene JSON-Parameter (Standardbibliothek) |
| **Richtungsmodell** | Runde 3 (F-05b): je Entscheidungspunkt ein Modell für Kauf und eines für Verkauf zu denselben Abständen; gehandelt wird die besser geschätzte Richtung bei ausreichendem Vorsprung – prüft, ob es Richtungsinformation gibt, die über die Zufallsbasis hinausgeht |
| **Purge / Embargo** | Purge: Trainingssignale, deren Label-Ausstieg nach dem Ende der Trainingsmenge liegt, fallen weg; Embargo: die ersten 5 Handelstage jedes Testfensters ohne Trades – beides gegen Informationsfluss aus dem Testfenster ins Training |
| **Walk-Forward / OOS** | rollierende Bewertung: 3 Jahre Anpassung, dann 1 Jahr Test; es zählen nur Trades im Testfenster (OOS = „out of sample“, außerhalb der Anpassung) |
| **Zufallsbasis** | Trefferquote bei zufälliger Richtung mit gleichen Einstiegszeiten, Abständen und kompletter Ausstiegslogik (≥ 1.000 Wiederholungen); die Strategie muss über ihrem 95. Perzentil liegen |
| **Schattenereignis** | LOSS_LOCK oder 50-%-Stopp im Backtest: gebucht statt gesperrt, die Rechnung läuft weiter; im Trade-Test = nicht bestanden, wenn es im OOS-Zeitraum liegt |
| **Parität** | Gleichheit von Takt und unabhängiger Rechnung bei Signalen und Trades (Zeit, Kurs, Grund, Ergebnis auf den Cent), Soll 100 %; später Demo-Live gegen Schatten-Backtest |
| **Kostenprofil** | Kostenannahmen eines Backtests: Spread je Kerze, Kommission je Lot und Seite, Swap mit Dreifachtag, Umrechnung nach EUR; Startwerte privat in `config/kostenprofil/` |
