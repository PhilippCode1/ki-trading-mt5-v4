# Konfiguration

Wo was eingestellt wird, wer es ändern darf und was eine Änderung auslöst.

| Datei | Inhalt | Wer ändert | Folge einer Änderung |
|---|---|---|---|
| `config/kit_demo.toml` | Betrieb: Terminalpfad, Symbole, Handelsfenster, Wächterwerte, Kostenstartwert, Probe-Takt, Meldungen | Agent per Commit (nie Zugangsdaten) | wirkt erst nach **neuer Installation** (`kit installieren --tag …`); gehört zu `CODE_F04` (auch der Backtest liest sie): nach der ersten Datensicht einer Forschungsrunde nur mit `aenderung_nach_sicht` ([ENTWICKLUNG.md](ENTWICKLUNG.md) §5) |
| `config/tore.toml` | Tor-Schwellen, Hebelband, LOSS_LOCK, Tagesbudget, 50-%-Stopp, Tor-T-Mengen, `mechanik`-Dateiliste | **nur Betreiber** (neuer Versuch, Eintrag in `docs/bot/ENTSCHEIDUNGEN.md`) | SHA-256 in `kit/gates/__init__.py` muss mitgeändert werden, sonst startet der Bot nicht |
| `config/trade_test.toml` | Verfahren des Trade-Tests (Tor 85): Walk-Forward, Backtest-Konto, Bootstrap, Zufallsbasis, Kommission der Kostenprofile, Zusatzkriterien, Kennzahlbasis – keine Schwellen | **nur Betreiber** (nach dem ersten Commit eingefroren, der Wächter sperrt Write/Edit; Änderung = neuer Versuch mit neuer Vorregistrierung) | SHA-256 in `kit/gates/trade_test.py` (`TRADE_TEST_SHA256`) muss mitgeändert werden, sonst bricht jede Auswertung ab (`TradeTestVeraendert`); der SHA steht in jeder Vorregistrierung im Versuchsprotokoll |
| `config/kostenprofil/f04_startwerte.json` | **privat** (nicht im Spiegel): Kostenstartwerte F-04 – Kommission gemessen 0 und Gegenprobe 3,25 je Lot und Seite (mit Quelle), Swappunkte (long, short) je Symbol, Dreifachtag, Umrechnungsgebühr | Agent per Commit, nur vor der ersten Datensicht | gehört zu `CODE_F04`: nach der Datensicht nur als neuer Versuch bzw. mit `aenderung_nach_sicht` ([ENTWICKLUNG.md](ENTWICKLUNG.md) §5) |
| `config/kostenprofil/f04_spreadprofil.json` | **privat** (nicht im Spiegel): Spreadprofil je Symbol aus den H1-Kerzen der Datensicht (genutzt nur für S-BL-01: halber Median-Spread je Seite; die gezählten Varianten nehmen im Backtest den Spread je Kerze) | nur `kit forschung kostenprofil`, nie von Hand | SHA-256 steht im DATA_VIEW; passt die Datei nicht mehr dazu, bricht `kit forschung entwicklung` ab |
| `C:\KI-Trading\vps.config.psd1` | VPS: Ordner, Benutzer, Repo-URL, Wartungszeiten, RDP-Schalter | Betreiber (aus der Vorlage `deploy/windows-vps/vps.config.example.psd1`; `20_benutzer.ps1` legt die zentrale Kopie an; nie im Repo) | gilt beim nächsten Skriptlauf bzw. Aufgabenstart |
| `.claude/settings.json` | Wächter-Hook, `permissions.deny` | **nur Betreiber** | ab der nächsten Claude-Sitzung |
| `requirements/*.in` → `*.lock.txt` | Abhängigkeiten (hash-gesperrt) | Agent mit Begründung | `bot-runtime.lock.txt` ist Teil des `mechanik_hash` → neue Technik-Messung |

## `config/kit_demo.toml`

| Abschnitt | Schlüssel | Wert (Stand) | Bedeutung |
|---|---|---|---|
| `[terminal]` | `pfad` | `C:\KI-Trading\mt5-demo\terminal64.exe` | portables Demo-Terminal auf dem VPS. Bei gesetztem Pfad verbindet `initialize(path=…)` genau dieses Terminal. Das Terminal muss laufen (Start mit `/portable` durch `bot_dienst.ps1`). Leer = Standard-Terminal (Laptop bis F-03b). |
| `[symbole]` | `strategie`, `probe` | 7 FX-Paare: EURUSD, USDJPY, GBPUSD, CHFJPY, CADJPY, AUDUSD, NZDUSD | V7 in ENTSCHEIDUNGEN |
| `[symbol_namen]` | z. B. `EURUSD = "EURUSD.a"` | leer | Broker-Suffixe |
| `[ausfuehrung]` | `deviation` | 20 | erlaubte Abweichung in Points |
| `[daten]` | Entwicklung / Holdout / Zeitrahmen | 2010-01-01 … 2021-06-30 / 2021-07-01 … 2026-06-30 / D1, H4, H1 | V6; Holdout bleibt bis F-06 gesperrt |
| `[zeiten]` | `fenster_von`, `fenster_bis`, `freitag_bis` | 08:00, 22:00, 20:00 (Europe/Berlin) | nur Einstiege; Schutz, Abgleich und Schließen laufen immer |
| `[waechter]` | `kursalter_s`, `korridor_prozent`, `spread_faktor` | 5, 1, 3 | kein Einstieg bei altem Kurs, Fehlkurs oder breitem Spread |
| `[kosten]` | `provision_je_lot_seite` | 3.25 | bleibt 3,25 als vorsichtiger Wert für die Größenrechnung des Takts (Hebelband und Tagesbudget), auch im Backtest. Die tatsächlichen Kosten im Backtest kommen aus dem Kostenprofil (`config/trade_test.toml` [kosten], `config/kostenprofil/`); der erste Demo-Trade zeigte Kommission 0. |
| `[probe]` | `abstand_points`, `sl_enger_points`, `sl_enger_nach_s`, `schliessen_nach_s`, `takt_min` | 300, 100, 20, 60, 10 | Technik-Messung: je Symbol höchstens ein Zyklus pro 10 min |
| `[meldungen]` | `windows` | true | Windows-Benachrichtigung zusätzlich zu `MELDUNGEN.txt` |

Verbotene Schlüssel (der Loader bricht ab): alles mit login, passw, server, konto, account – Zugangsdaten stehen **nie** in Dateien.

## `config/tore.toml` (eingefroren)

| Abschnitt | Werte |
|---|---|
| `[band]` | Boden 5, Deckel 15, Korridor 5,25–14,25, höchstens 1 Strategieposition, Prüfpunkt 21:30 Berlin |
| `[limits]` | Tagesbudget 3 %, LOSS_LOCK 25 %, Stop ≤ 3× Ziel, Margin-Level ≥ 300 % |
| `[stop50]` | Fenster 50 Trades, ab 20 Trades, Quote ≤ 0,50 → K3 |
| `[tor_t]` | ≥ 300 Sendungen (≥ 100 Eröffnen, ≥ 100 Schließen, ≥ 50 Ändern), Quote ≥ 0,95 (Ziel 0,99), UNBEKANNT ≤ 900 s, Kill K1/K2 ≤ 5 s, K3 ≤ 60 s, `mechanik`-Dateiliste |
| `[zaehlregeln]` | Trade = Position bis zur vollständigen Schließung, Ergebnis = alle Deals inkl. Kommission, Swap und Gebühren, Gewinn nur bei Ergebnis > 0 (0 = Verlust), Namensraum STRATEGIE; neuer `strategie_hash` oder Aufhebung der 50-%-Sperre startet das Zählfenster neu |
| `[tor_85]` | OOS-Trades ≥ 200, Quote ≥ 0,85, Holdout ≥ 40 Trades bei ≥ 0,85, Gewinnfaktor ≥ 1,2, Ø Verlust ≤ 3 × Ø Gewinn, Max-Drawdown < 25 %, Erwartungswert-Untergrenze 95 %, Zufallsbasis 1.000 Wiederholungen / 95. Perzentil – ausgewertet von `kit/gates/trade_test.py` (Entwicklung F-04, Holdout F-06) |
| `[tor_95]` | Demo-Live: ≥ 100 Trades, ≥ 3 Monate, Quote ≥ 0,95, Gewinnfaktor ≥ 1,2 (Auswertung F-07) |

## `config/trade_test.toml` (eingefroren)

Verfahrensparameter des Trade-Tests (Tor 85). Schwellen stehen allein in `config/tore.toml` und werden hier nicht gedoppelt; `kit/gates/trade_test.py` prüft die Stimmigkeit beider Dateien (Bootstrap-Perzentil, Zufallsbasis) und bricht sonst ab.

| Abschnitt | Schlüssel | Wert | Bedeutung |
|---|---|---|---|
| – | `version` | 1 | Formatstand |
| `[walk_forward]` | `anpassung_jahre`, `test_jahre` | 3, 1 | rollierend: 3 Jahre Anpassung, dann 1 Jahr Test; gewertet werden nur Trades mit Eröffnung im Testfenster |
| | `entwicklung_start`, `entwicklung_ende` | 2010-01-01, 2021-06-30 | Entwicklungsperiode (Ende einschließlich); der Holdout 01.07.2021–30.06.2026 bleibt ungezogen |
| `[konto]` | `start_equity`, `hebel`, `waehrung` | "10000", 100, "EUR" | Backtest-Konto (Startkapital, Hebel; das Backtest-Terminal rechnet fest in EUR) |
| | `versatz_s` | 10800 | Serverzeit = UTC + 3 h (Servertag für Tagesanker, Swap und Tagesverluste) |
| `[bootstrap]` | `wiederholungen`, `saat`, `untergrenze_perzentil` | 10000, 4041, "5" | Erwartungswert in R: einseitige 95-%-Untergrenze = 5. Perzentil der iid-Bootstrap-Mittelwerte; muss 100 − `tor_85.erwartung_untergrenze_prozent` sein |
| `[zufall]` | `wiederholungen`, `saat`, `perzentil` | 1000, 4042, "95" | Zufallsbasis (zufällige Richtung je Trade, komplette Ausstiegslogik, gleiche Einstiegszeiten); Wiederholungen ≥ `tor_85.zufall_wiederholungen`, Perzentil = `tor_85.zufall_perzentil` |
| `[kosten]` | `provision_gemessen`, `provision_gegenprobe` | "0", "3.25" | Kommission je Lot und Seite: Hauptprofil laut erstem Demo-Trade, Gegenprobe mit dem Startwert |
| | `kostenfaktor`, `dreifachtag` | "1.5", 2 | Gegenprobe Kosten × 1,5 (Spread, Kommission, Swap-Belastungen); Dreifachswap am Mittwoch (0 = Montag) |
| `[zusatz]` | `nur_berichten`, `dsr_min`, `teilperioden`, `teilperioden_positiv_min`, `gewinnfaktor_kosten_min` | true, "0.95", 4, 3, "1.0" | Plan-Zusatzkriterien (DSR, ≥ 3 von 4 Teilperioden positiv, Gewinnfaktor bei Kosten × 1,5 > 1,0) – nur berichtet, zählen erst mit OK des Betreibers |
| `[kennzahlen]` | `gewinnfaktor_basis`, `verlust_zu_gewinn_basis` | "EUR", "EUR" | Basis der Geldkennzahlen im Tor; R wird zusätzlich berichtet |

Kommission und Dreifachtag nimmt die Auswertung aus dieser Datei, Swappunkte und Umrechnungsgebühr aus `config/kostenprofil/f04_startwerte.json` (privat; eine Umrechnungsgebühr ≠ 0 lehnt der Runner ab). Den Spread liefert jede Kerze selbst.

## Umgebungsvariablen

| Variable | Zweck |
|---|---|
| `KIT_HOME` | **nur unter pytest** – Testablage; außerhalb verboten (Sperren dürfen nicht umgangen werden) |
| `KIT_ALTE_ABLAGEN` | nur unter pytest – Altablagen für Umzugstests |
| `KIT_SPERRLISTE` | Pfad der Sperrliste für `tools/kit_scan.py` (sonst `%LOCALAPPDATA%\kit\sperrliste.txt`) |
| `KIT_PY` | Interpreter für die Git-Hooks (sonst `.venv-312`) |
| `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT` | von Claude Code gesetzt → Betreiberbefehle verweigert |

## Feste Pfade

| Pfad | Woher |
|---|---|
| `%USERPROFILE%\KI-Trading-Bot` | `kit/paths.py` über die Windows-Shell-API (FOLDERID_Profile), nicht über Umgebungsvariablen |
| `C:\KI-Trading\{mt5-demo,sicherung,austausch}` | VPS-Konfiguration |
| Repo-Checkouts | `%USERPROFILE%\ki-trading` je Benutzer (VPS) |
