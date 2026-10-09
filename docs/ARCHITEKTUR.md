# Architektur

Wie das System aufgebaut ist und warum. Für Formate und Aufrufe siehe [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md), für Einstellungen [KONFIGURATION.md](KONFIGURATION.md), für den Betrieb [BETRIEB.md](BETRIEB.md).

## 1. Was das Projekt ist

**KI-Trading MT5** ist ein schlanker, sicherheitsorientierter Handelsbot für MetaTrader 5. Er handelt ausschließlich auf einem **Demokonto**. Er soll in Stufen zeigen:

1. dass seine Technik fehlerfrei arbeitet (**Tor T**),
2. ob eine vorab festgelegte Strategie im Backtest ≥ 85 % Gewinntrades schafft (**Tor 85**),
3. ob sie im Demo-Live-Betrieb ≥ 95 % hält (**Tor 95**).

Danach kann der Betreiber, und nur er, über Echtgeld entscheiden. Ein laufender Stopp greift, wenn die rollierende Trefferquote ≤ 50 % sinkt (**Tor 50**). Plan und Entscheidungen: [`FAST_TRACK_PLAN.md`](FAST_TRACK_PLAN.md), [`bot/ENTSCHEIDUNGEN.md`](bot/ENTSCHEIDUNGEN.md).

Ehrliche Einordnung: Es gibt bisher keinen belegten Handelsvorteil. Der Demo-Betrieb beweist die Mechanik, nicht den Gewinn.

**Rolle von „KI“:** Claude (Claude Code) ist Entwicklungs- und Auswertungsagent. Im Geldpfad entscheidet ausschließlich deterministischer Code. Ein späterer Meta-Filter (Plan F-05) wird offline trainiert und als eingefrorene Parameter geladen. Kein Sprachmodell trifft Handelsentscheidungen.

## 2. Grundsätze (gelten für jede Erweiterung)

| Grundsatz | Umsetzung |
|---|---|
| **Nur DEMO** | Demo-Prüfung vor **jeder** Sendung (Kontomodus DEMO, Hedging, Algo-Trading erlaubt, Kontoabdruck in der Allowlist) und Gegenprobe danach; der Live-Pfad ist hart gesperrt (`live_guard.live_pruefen()` wirft immer) |
| **Fail-closed** | Alles Unklare sperrt: unbekannter Retcode → UNBEKANNT, fehlender Zustand → Sperre, unlesbare STOP-Datei → K1, unbekanntes Werkzeug → Wächter verweigert |
| **Journal vor Netz** | Jede Orderoperation wird mit `fsync` als GEPLANT/GESENDET ins Journal geschrieben, **bevor** sie an MT5 geht. Das Journal ist die Wahrheit, mit Hashkette. |
| **Nie blind neu senden** | Unklarer Ausgang → UNBEKANNT; Klärung über `magic` + Symbol + Zeitfenster; Negativnachweis erst nach 60 s |
| **Abbau nie blockiert** | Sperren verhindern nur Risikozunahme; Schutz-SL, Schließen und K3 laufen immer |
| **Geld in Decimal** | Werte nur an der MT5-Grenze in `float` umgewandelt |
| **Einfachste Variante** | Keine Datenbank, kein Server, keine Container im Geldpfad; Dateien + ein Prozess |
| **Mechanik eingefroren** | Der Geldpfad (`mechanik_hash`, 38 Dateien) ändert sich nur bewusst; jede Änderung startet die Technik-Messung neu |

## 3. Systemübersicht

```
                 ┌────────────────────── Windows-VPS (Zielbild; Bot ruht seit 09.10.2026) ─────────────────────┐
                 │  Benutzer kitbot (Desktop-Sitzung)                                                         │
 Broker-Server ◄─┼─► MT5-Terminal (terminal64.exe /portable) ◄── MetaTrader5-Python-API (IPC) ──► Bot "kit"   │
   (DEMO)        │                                                                             │  Takt 1 s     │
                 │                                       %USERPROFILE%\KI-Trading-Bot\ ◄────────┘  Journal,      │
                 │                                       (Journal, Zustand, Sperren, PIN, Schlüssel)  Zustand  │
                 │  Aufgaben: Autostart-Hülle, Tagessicherung ──► C:\KI-Trading\sicherung                    │
                 │            Status-Export (redigiert) ───────► C:\KI-Trading\austausch ──► Herzschlag-Ping  │
                 │  Benutzer kitdev: Claude Code + Repo-Checkout (liest nur austausch)                       │
                 └──────────────────────────────────────────────────────────────────────────────────────────────┘
 GitHub privat (volle Historie) ──git──► Bot-Checkout (nur lesen) ──kit installieren──► unveränderliche Kopie app\<tag>
 GitHub öffentlich (bereinigter Spiegel, eine Momentaufnahme je Lauf, erzeugt von tools/publish.py)
```

Das Bild zeigt das Zielbild auf dem Windows-VPS. Tatsächlich lief der Bot (T-DAUER) auf dem Laptop; seit der Entscheidung ENDE (09.10.2026) wird er nicht weiterbetrieben, der Betreiber beendet ihn; auf dem VPS lief noch kein Bot. Dort arbeitet vorerst nur `kitdev` (Entwicklung); `kitbot`, MT5 und die Aufgaben kommen erst bei einer Wiederaufnahme dazu.

**Komponenten und wie sie kommunizieren**

| Komponente | Rolle | Kommunikation |
|---|---|---|
| MT5-Terminal | Verbindung zum Broker, Kurse, Ausführung | Python-Paket `MetaTrader5` (lokale IPC); der Bot startet **nie** selbst ein Terminal und meldet sich nie an |
| Bot `kit` | Takt, Risiko, Orders, Abgleich, Sperren | liest/schreibt nur seine Ablage; spricht nur über den Broker-Adapter mit MT5 |
| Laufzeitablage | Journal (JSONL, Hashkette), Zustand, STOP-/BEENDEN-Dateien, Freigaben (Allowlist, PIN-Hash), Schlüssel, Kerzen (SQLite), Exporte | Dateisystem; Kill-Schalter = Datei anlegen |
| Betreiber | Start/Stopp, PIN, Entsperren, Freigaben | `python -m kit …` in eigener Konsole; STOP-Datei auch ohne Konsole |
| Agent (Claude Code) | Entwickeln, testen, auswerten, veröffentlichen | Repo; Bot nur über die kit-CLI; Wächter-Hook + (VPS) Benutzertrennung |
| GitHub | privat: Wahrheit des Codes; öffentlich: bereinigter Spiegel | `tools/publish.py` |
| Aufgabenplanung (VPS) | Autostart, Neustart mit Pause, Sicherung, Status | `deploy/windows-vps/*.ps1` |

## 4. Paketkarte `kit/`

**Bedienung** (nicht im `mechanik_hash`, darf sich jederzeit ändern – Ausnahme: die F-04-Dateien nach der ersten Datensicht, siehe §5a):

| Modul | Aufgabe |
|---|---|
| `cli.py` | Kommandozeile `python -m kit <befehl>`, Umgebungsprüfung, Betreiber-Schranke (`_interaktiv`); `forschung` (Versuchsprotokoll, Entwicklungsauswertung) |
| `betrieb.py` | Befehle mit Terminal: Rauchtest, Datenabzug, Registrierung, Einzelprobe, Skripte, Takt (`lauf`) |
| `bedienung.py` | Befehle ohne Terminal: Stop-Dateien, PIN, Entsperren, Status, Tor-T-Bericht, Installieren, Starten, Sichern |
| `umzug.py` | Startgate gegen verlorene Altbestände, Umzug, Wiederherstellen aus Sicherung |
| `paths.py` | Laufzeitablage `%USERPROFILE%\KI-Trading-Bot` über die Windows-Shell-API |
| `config.py` | `config/kit_demo.toml` laden (Zugangsdaten-Schlüssel verboten) |
| `backtest/` | Backtest mit demselben Takt (§5a): `kosten` (Kostenprofil, Umrechnung nach EUR), `terminal` (`BacktestTerminal` mit Vorgriffswächter), `runner` (Schrittfolge, `BacktestBot`, Ergebnis), `ausstieg` (schnelle Ausstiegsrechnung), `paritaet` (Signal- und Trade-Parität) |
| `gates/` | Tor-Schwellen (`config/tore.toml`, SHA-256-gepinnt), Tor-T-Auswertung, `mechanik_hash`; `trade_test` (Tor 85: Walk-Forward, Kennzahlen, Zufallsbasis, unabhängige Band-/Budget-Nachrechnung, Auswahl; Verfahren aus `config/trade_test.toml`, SHA-256-gepinnt) |
| `strategy/` | Protokoll `Strategie`/`Signal`, `strategie_hash`; Attrappe für Tests; `rev` (S-REV-01 Rückkehr zum Mittelwert H1, S-REV-02 Fehlausbruch H4), `donchian_ref` (S-BL-01, Referenz BL-TFD1 auf D1, läuft nicht über den Takt), `varianten` (vorregistrierte Variantenliste F-04), `meta_filter` (KI-Meta-Filter F-05: Hülle um eine Basisstrategie, Merkmale, eingefrorene JSON-Modelle, nur Standardbibliothek, §5b), `richtung` (Richtungsmodell F-05b: Kauf- gegen Verkaufsmodell zu denselben Abständen, §5c) |
| `report/` | Redigieren (keine Kontokennungen/Geldbeträge), Tor-T-Bericht |
| `research/` | Datenabzug in SQLite mit Hash je Abzug, Holdout-Sperre; Datenleser `daten.lesen` (nur lesend, Hash- und Holdout-Prüfung); `stats`/`trials` (Kopien aus der Referenz mit SHA-Pin, `HERKUNFT.md`); `protokoll` (Versuchsprotokoll, Runden F-04 und F-05 mit eigener Vorregistrierung, Familien und Code-Liste); `entwicklung` (Entwicklungsauswertung F-04, Bericht); `meta` (Runde 2 F-05: Datensatz, Purge/Embargo, Schwellenregel, Auswertung über den Takt, Bericht – §5b); `richtung` (Runde 3 F-05b – §5c) |

**Mechanik** (im `mechanik_hash`, Liste in `config/tore.toml`):

| Paket | Aufgabe |
|---|---|
| `domain/` | Typen (Absicht, Operation, Deal, Position …), Rundung aufs Tickraster, Zeit (UTC/Berlin ohne tzdata) |
| `broker/` | `seam.Terminal`-Protokoll; `mt5_real.Mt5Terminal` (einziger MetaTrader5-Import); `sim` (SIM-Terminal für Tests/Trockenlauf); `readonly` |
| `orders/` | `lifecycle` (Orderlebenszyklus), `reconcile` (Abgleich mit dem Broker), `ids` (Auftragskennung im `magic`), `retcodes` (41 MT5-Codes → Klasse) |
| `state/` | Journal, Zustand, Schreibsperre, STOP-Datei, Sperren, PIN (scrypt) |
| `risk/` | Hebelband 5–15, Tagesbudget 3 %, LOSS_LOCK 25 %, 50-%-Stopp, Größenberechnung mit Kreuzkurs-Gegenprobe, Wächter (Kursalter, Spread, Fenster) |
| `run/` | `loop.Bot` (der Takt), Melder, Trockenlauf mit beschleunigter Uhr |
| `probe/` | Probe-Mechanik für die Technik-Messung, D-Skripte/Killer-Tests |
| `live_guard.py` | Live-Riegel, Demo-Prüfung, Allowlist |

`kit` importiert nie `reference/`, `oracles/`, `tools/` oder `tests/` (geprüft in `kit_tests/test_struktur.py`). Was aus der Referenz gebraucht wird, liegt als gepinnte Kopie in `kit/research/` (Herkunft und SHA-256 in `kit/research/HERKUNFT.md`) oder ist neu geschrieben (`kit/strategy/donchian_ref.py`).

## 5. Ablauf im Takt (`kit/run/loop.py`)

```
jede Sekunde:  STOP/BEENDEN lesen ─► K1 (keine Einstiege) | K2/K3 (dauerhaft, PIN) | Drill
≤ 5 s / Fill:  Demo-Wache ─► Serverversatz (stündlich) ─► Abgleich mit Broker ─► Sperren/Vorfälle
               ─► Schutzaktionen (SL nachziehen, Notschluss) ─► Tagesanker ─► Grenzen (LOSS_LOCK, Tagesstopp, 50 %)
               ─► Technik-Wächter ─► Probe-Mechanik (nur Modus probe)
21:30 Berlin:  Prüfpunkt Hebelband
jede Minute:   Strategie-Signal (abgeschlossene Kerze) ─► Einstiegsprüfung ─► Lebenszyklus
```

**Einstiegsprüfung** (nur bei Risikozunahme), in dieser Reihenfolge:
1. Sperren (BEENDEN, K1–K3, Tagesstopp, Technik-Pause)
2. offene Operation im Symbol
3. Wächter: DEMO, Handel erlaubt, Fenster 08–22 Uhr (freitags bis 20 Uhr), Kursalter ≤ 5 s, Korridor, Spread, Margin
4. SL/TP-Rundung, Stops-Level, Stop ≤ 3× Ziel
5. Tickwert-Gegenprobe
6. Hebelband und Tagesbudget

Eine Ablehnung wird als SIGNAL/ABGELEHNT ins Journal geschrieben.

**Lebenszyklus einer Operation:**

```
GEPLANT ─(fsync)─► check ─► GESENDET ─(fsync)─► send
   ├─ Erfolg mit Ticket+Volumen ─────────────► ERLEDIGT / TEILWEISE
   ├─ NOT_EXECUTED (≤ 3 Versuche, ≤ 30 s) ───► erneut GEPLANT
   ├─ endgültig abgelehnt ───────────────────► ABGELEHNT (+ Zeitsperre 1 h bei Risikozunahme)
   └─ Ausgang unklar ────────────────────────► UNBEKANNT ─► Klärung über magic/Deals ─► nach 60 s Negativnachweis
```

**Neustart:**
1. Zuerst das Journal lesen und den Zustand wiederherstellen; offene GEPLANT/GESENDET werden UNBEKANNT.
2. Dann mit dem Broker abgleichen.
3. Danach wieder handeln.

Fehlende Sperrsätze holt der Bot aus dem Journal nach.

**Kill-Stufen:**
- K1 = keine Einstiege, vorübergehend.
- K2 = keine Einstiege, dauerhaft.
- K3 = K2 plus alle eigenen Positionen flach in ≤ 60 s.

K2 und K3 hebt nur der Betreiber mit PIN auf (`kit entsperren`).

## 5a. Backtest und Trade-Test (F-04)

**Ein Takt für alles** (Plan §4): Der Backtest hat keine eigene Handelslogik. Er lässt den unveränderten Takt `kit.run.loop.Bot` über einem Historien-SIM laufen (`kit/backtest/`, nicht im `mechanik_hash`; Bot, SIM und Risiko werden nur benutzt). `BacktestBot` ergänzt genau drei Dinge:

| Ergänzung | Wirkung |
|---|---|
| Schattenereignisse | LOSS_LOCK und STOP50 sperren nicht, sondern werden als Satz SCHATTEN gebucht; Equity und Handel laufen weiter. Ein neues Ereignis zählt erst, wenn die Bedingung vorher vorbei war. Jede andere Sperre und jeder Vorfall machen den Lauf technisch ungültig (`technik_ok = False`). Tagesstopp, Technik-Pause, Band, Budget und Handelsfenster wirken wie im Betrieb. |
| Einstiegskontext | je gefülltem Einstieg Equity, Tagesbudget, Kurs, SL/TP, Vertrag und offene Positionen – für die unabhängige Band-/Budget-Nachrechnung im Trade-Test |
| Speicherjournal | dieselben Sätze mit derselben Hashkette und Schlüsselprüfung, aber im Arbeitsspeicher statt je Satz in einer Datei (Zehntausende Sätze je Lauf, viele Läufe parallel; das Dateijournal läuft im Backtest ohnehin ohne `fsync`); gleiche Ergebnisse wie mit dem Dateijournal sind getestet |

Gezählt wird mit dem Tradebuch des Takts (Zählregeln `config/tore.toml`): Trade = Position bis zur vollständigen Schließung, Ergebnis = alle Deals inkl. Kommission und Swap, R = Ergebnis / geplanter Verlust bis SL inkl. Kommission beider Seiten.

**Schrittfolge je H1-Schluss** (`kit/backtest/runner.py`; jetzt = T + 1 h, T = Kerzenbeginn, vereinigt über alle Symbole):

```
Uhr := jetzt
1. Servertageswechsel in (voriger Schritt, T]  ─► Swap buchen (Rollover lag in einer Lücke, z. B. Wochenende)
2. H1-Kerzen mit Beginn T abspielen            ─► SL/TP nach SIM-Regeln (Lücke = Eröffnungskurs, SL vor TP), Kurs = Schluss
3. Mittelkurse EURUSD/USDJPY ─► Kreuzkurs EURJPY ─► Tickwerte aller Symbole
4. Kerzen des Strategie-Zeitrahmens, wenn nicht H1 (H4), mit Schluss ≤ jetzt in den Speicher
   (Spread = der H1-Kerze mit demselben Schluss, damit e = Fill wie bei H1)
5. Servertageswechsel genau bei jetzt          ─► Swap buchen (in Schritt 2 per SL/TP geschlossene Positionen zahlen nicht)
6. Bot.schritt()                               ─► Schutz/Abgleich, Grenzen, Band-Prüfpunkt, Zeitbarriere, Signal, Einstieg
7. Equity (inkl. schwebender Ergebnisse) in die Kurve
```

**Vorgriffswächter:** `BacktestTerminal` (SIM-Terminal plus Historienkerzen) wirft `VorgriffFehler`, sobald eine Kerze vor ihrem Schluss abgespielt, eingestellt oder über `bars()` geliefert würde; der Lauf bricht ab (fail-closed). Zusätzlich prüft ein Präfix-Test mit ≥ 200 feindlichen Suffixen (`kit_tests/differenz_v4/test_backtest_praefix.py`), dass bis zum Präfixende nichts von späteren Kerzen abhängt ([ENTWICKLUNG.md](ENTWICKLUNG.md) §2 und §5).

**Kostenmodell** (`kit/backtest/kosten.py`, ein Kostenprofil je Lauf):

| Baustein | Regel |
|---|---|
| Spread | je Kerze aus dem Kerzenfeld `spread` (Points); steckt im Kurs: Kauf zum Ask = Bid + Spread, Verkauf zum Bid, Short-SL/TP lösen am Ask aus |
| Kommission | EUR je Lot und Seite, je Deal auf Cent gerundet |
| Swap | Swappunkte (long, short) je Lot und Nacht · Point · Kontraktgröße, in EUR zum Kurs des Rollovers; gebucht beim Servertageswechsel (00:00 Serverzeit; Serverzeit = UTC + 3 h, also 21:00 UTC) für die Nacht des endenden Servertags: Mo, Di, Do, Fr × 1, Mi × 3 (Dreifachtag), Sa/So 0 |
| Umrechnung | EUR je Einheit der Gewinnwährung aus Mittelkursen: USD = 1/EURUSD, JPY = 1/(EURUSD · USDJPY) (Kreuzkurs EURJPY als nicht handelbares Hilfssymbol). Tickwert = Tickgröße · Kontraktgröße · EUR je Einheit (8 Stellen). SL/TP innerhalb einer Kerze rechnen mit dem Tickwert vom Schluss davor. |
| Gegenprobe × f | Spread × f (auf ganze Points aufgerundet), Kommission × f, Swap-Belastungen × f (Gutschriften bleiben) |

F-04 rechnet jede gezählte Variante mit drei Profilen: `HAUPT` (Kommission laut erstem Demo-Trade), `KOSTEN_X1_5` (Hauptprofil × 1,5) und `GEGENPROBE_3_25` (Kommission 3,25 je Lot und Seite). Swappunkte und Umrechnungsgebühr kommen aus den privaten Startwerten, Kommission und Faktor aus `config/trade_test.toml`; eine Umrechnungsgebühr ≠ 0 lehnt der Runner ab (fail-closed). Die Größenrechnung des Takts nutzt weiter den vorsichtigen Wert aus `config/kit_demo.toml` ([KONFIGURATION.md](KONFIGURATION.md)).

**Schnelle Ausstiegsrechnung** (`ausstieg.py`): dieselben Regeln wie SIM und Takt (Lücke, SL vor TP, Zeitbarriere zum aktuellen Kurs, Tickwert, Kommission, Swap) als direkte Rechnung je Position, ohne Takt. Zwangsausstiege des Takts (Band, K3) bildet sie nicht nach. Zwei Verwendungen:
- **Parität** (`paritaet.py`): Signal-Parität = Signale im Journal gegen die Strategie direkt über die Kerzenreihe mit derselben Fensterregel; Trade-Parität = jeder Takt-Trade gegen die direkte Rechnung (Zeit, Kurs, Grund, Ergebnis auf den Cent). Soll jeweils 100 %; Zwangsausstiege werden getrennt ausgewiesen.
- **Zufallsbasis:** je Trade Kauf und Verkauf zur selben Einstiegszeit mit denselben SL-/TP-Abständen; je Wiederholung eine zufällige Richtung je Trade (≥ 1.000 Wiederholungen), daraus das 95. Perzentil der Trefferquote.

**Trade-Test** (`kit/gates/trade_test.py`, Plan §5 Tor 85): reine Auswertung fertiger Backtests; importiert bewusst weder `kit.risk` noch `kit.run` oder `kit.backtest`. Schwellen allein aus `config/tore.toml`, Verfahren aus `config/trade_test.toml` (beide SHA-256-gepinnt).

Walk-Forward: Entwicklungsperiode 01.01.2010–30.06.2021, Anpassung 3 Jahre, Test 1 Jahr, rollierend → Testfenster 2013, 2014 … 2020 und 01.01.–30.06.2021. Die Varianten haben feste, vorregistrierte Parameter; die Anpassungsjahre dienen nur als Anlauf. Gewertet werden Trades, deren Eröffnung in einem Testfenster liegt (OOS).

| Kriterium (je Variante, OOS, Hauptprofil) | bestanden, wenn |
|---|---|
| Trades | ≥ `min_trades_oos` – die Entwicklung allein (strenger als das Tor, das Entwicklung + Holdout zählt) |
| Quote | Gewinntrades (Ergebnis > 0) ≥ `quote_min` |
| Erwartungswert in R | einseitige 95-%-Untergrenze (iid-Bootstrap) > 0 |
| Gewinnfaktor | ≥ `gewinnfaktor_min` (EUR inkl. Kosten) |
| Ø Verlust / Ø Gewinn | ≤ `verlust_zu_gewinn_max` (EUR, realisiert) |
| Zufallsbasis | Quote > 95. Perzentil der Zufallsbasis |
| Max-Drawdown | < `drawdown_max_prozent` vom laufenden Equity-Hoch |
| 50-%-Stopp | kein 50-%-Ereignis in der OOS-Tradefolge und kein Schattenereignis im OOS-Zeitraum |
| Hebelband und Tagesbudget | je Einstieg eingehalten, unabhängig nachgerechnet: SL/TP auf der richtigen Seite, Lot-Raster, Stop ≤ 3 × Ziel, Band bei Einstieg, TP und SL, Gesamtband, Tagesbudget, „Lot minimal“ nach der Größenregel |
| Technik (ergänzt von `kit/research/entwicklung.py`) | Lauf technisch gültig: keine Sperre, kein Vorfall, alle Trades vollständig, Signal- und Trade-Parität 100 % |

Nicht bewertbar (z. B. keine Trades, Trades ohne Einstiegskontext, Zufallspaare passen nicht zu den Trades) gilt als nicht bestanden. Auswahl (Prereg §5): nur Varianten, die alle Kriterien erfüllen; die höchste Wilson-95-%-Untergrenze gewinnt, bei Gleichstand mehr Trades je Monat. DSR, Teilperioden und Gewinnfaktor bei Kosten × 1,5 werden nur berichtet. Den Holdout prüft erst F-06 mit denselben Bausteinen.

**Versuchsprotokoll-Ablauf** (`kit forschung …`; Formate [SCHNITTSTELLEN.md](SCHNITTSTELLEN.md) §5a):

```
vorab --prereg-ok "…" ─► PREREG_SIGNED je Familie (F04-ZIEL-STOP, F04-REFERENZ, F04-DATEN): Commit, Code-Hashes,
                          mechanik_hash, SHA von Vorregistrierung, tore.toml, trade_test.toml
                          (nur bei sauberem git status, nur vor jeder Datensicht)
kostenprofil          ─► Vorprüfung ─► erste Datensicht: Abzüge lesen (Hash, Holdout), Spreadprofil je Symbol
                          (privat in config/kostenprofil/f04_spreadprofil.json, im Protokoll nur sein SHA) ─► DATA_VIEW
entwicklung           ─► Vorprüfung ─► je Variante TRIAL BEGINN ─► 12 Varianten × 3 Kostenprofile (parallel) + S-BL-01
                          ─► Bewertung, Parität, Zufallsbasis, DSR ─► Bericht berichte/forschung/ ─► je Variante TRIAL ERGEBNIS
pruefen               ─► Kette, Regeln, Code und Mechanik gegen Vorregistrierung, Vollständigkeit
                          ─► VERIFIZIERT, UNVOLLSTAENDIG oder BEFUNDE
```

Die Vorprüfung (`protokoll.vorpruefung`) bricht fail-closed ab, wenn das Protokoll Befunde hat, eine Familie nicht vorregistriert ist, Code (`CODE_F04`) oder `mechanik_hash` vom Signierten abweichen oder der Arbeitsbaum dieser Dateien nicht sauber ist.

Der Holdout wird im ganzen Ablauf nie gezogen oder gelesen. S-BL-01 hat kein Server-TP und läuft deshalb nicht über den Takt, sondern als direkte Rechnung nach BL-TFD1 (nur Vergleich, zählt nie). Nach der ersten Datensicht binden die Code-Hashes der Vorregistrierung alle F-04-Dateien und der `mechanik_hash` die Mechanik; Änderungen daran regelt [ENTWICKLUNG.md](ENTWICKLUNG.md) §5.

**Grenzen:** H1-Auflösung (innerhalb einer Kerze SL vor TP), Spread aus dem Kerzenfeld, heutige Swapsätze für die Vergangenheit, Zeitbasis: die Abzüge stehen in Serverzeit und werden mit festem Versatz +3 h nach UTC umgerechnet (der Server folgt der New-Yorker Sommerzeit; im Winter liegt das Handelsfenster dadurch 1 h später), Band-Prüfpunkt im Stundentakt (22:00 statt 21:30). Der Entwicklungsbericht führt sie auf.

## 5b. KI-Meta-Filter (F-05)

**Zweck** (Plan §4, Vorregistrierung `docs/bot/prereg/F05_ENTWURF.md`): Ein Lernmodell schätzt je Signal einer Basisstrategie die Wahrscheinlichkeit „Ziel vor Stop“; nur Signale über der Schwelle gehen an den Takt. Es ist kein Sprachmodell im Handelspfad. Der Filter kann nur auswählen, keine neuen Treffer erzeugen.

| Teil | Ort | Umgebung |
|---|---|---|
| Hülle `MetaFilter`, Merkmale, Wahrscheinlichkeit aus JSON (logistische Regression, HistGradientBoosting) | `kit/strategy/meta_filter.py` | Standardbibliothek (Bot) |
| Datensatz, Walk-Forward-Plan mit Purge und Embargo, Schwellenregel, Auswertung, Bericht, Versuchsprotokoll | `kit/research/meta.py` | Standardbibliothek |
| Training, Export nach JSON, Paritätsprüfung | `forschung/meta_training.py` | `.venv-forschung` (scikit-learn, `requirements/forschung.lock.txt`) |
| Aufruf | `forschung/runde2.py` (`python -m forschung.runde2 daten \| entwicklung`) | `.venv-forschung` |
| eingefrorene Modelle | `forschung/modelle/F05/<Variante>.json` | Daten (nie überschrieben) |

**Hülle:** gleiche Symbole, Zeitrahmen und Zeitbarriere wie die Basis, `rueckblick` = max(Basis, 520). Die Basis bekommt genau ihre letzten Kerzen (gleiche Signale, SL und TP wie ohne Hülle). Entscheidungszeit = Schluss der Signalkerze (der Schritt, an dem der Takt einsteigt). Je Testfenster gilt ein Modell mit Schwelle; kein Signal außerhalb aller Fenster, im Embargo (die ersten 5 Handelstage, Mo–Fr ohne 1.1. und 25.12.) und ohne Schwelle; sonst Signal genau dann, wenn p > Schwelle. Jedes Modell trägt seine Trainingsgrenzen (`training`: Anpassungsende, späteste Entscheidung und spätester Label-Ausstieg in Training und Validierung). Die Hülle verweigert fail-closed ein Modell, dessen Daten in sein Testfenster reichen, sowie überlappende Fenster.

**Merkmale** (Prereg §1, nur Kerzen bis zur Signalkerze, Strategie-Zeitrahmen, float; Fenster 520 Kerzen, ATR = Wilder 14 über das Fenster): Abstand zum SMA48 in σ, σ48/ATR, ATR/Schluss, Perzentil der ATR in 250 Kerzen, Spread/ATR, Rendite 24 Kerzen in ATR, Steigung SMA48 über 12 Kerzen in ATR, Lage in der 20er-Spanne, Stunde (Berlin, sin/cos), Wochentag 1-aus-5; S-REV-02 dazu Ausbruchstiefe und Kerzenspanne in ATR.

**Datensatz** (`meta.datensatz`): alle Signale der Basis mit genau der Fensterregel der Hülle im Takt (`paritaet.signal_fenster`, dieselbe Funktion wie die Signal-Parität), auf Kerzen, wie der Takt sie sieht (`meta.takt_kerzen`: Spread des Kostenprofils, H4 mit dem Spread der H1-Kerze desselben Schlusses). Label je Signal = Ergebnis > 0 der direkten Ausstiegsrechnung (Dreifach-Barriere, Hauptprofil, 1 Lot, Einstieg Ask/Bid des Schritts), unabhängig von Konto, Band und Positionsbelegung. Der Datensatz liegt nur lokal in `work/f05/` (abgeleitete Kursdaten, nie veröffentlicht); das Protokoll trägt seinen SHA-256.

**Training je Fenster** (Anpassung 3 Jahre, Test 1 Jahr wie F-04; dazu ein eingefrorenes Holdout-Modell 07/2018–06/2021, nicht ausgewertet):
```
inneres Modell   Training [Anpassungsbeginn, −1 Jahr)   Purge: Label-Ausstieg ≤ Ende der Menge
                 Validierung [−1 Jahr, Testbeginn)      Purge: Label-Ausstieg ≤ Testbeginn
                 → p der Validierung (Standardbibliothek) → Schwelle: kleinste aus {0,50 … 0,90} mit der höchsten
                   Wilson-95-%-Untergrenze, mindestens 20 Signale über der Schwelle; sonst keine Trades im Testfenster
finales Modell   ganze Anpassung [Anpassungsbeginn, Testbeginn), Purge wie oben → JSON mit Trainingsgrenzen
Parität          scikit-learn gegen Standardbibliothek auf allen Zeilen ≤ 1e-9 (sonst Abbruch)
```
Vor dem Schreiben prüft `meta.ausfuehren` je Variante fail-closed: Fenster und Embargo der Modelldatei = registrierter Plan, die vom
Trainer gemeldeten Grenzen und Anzahlen der drei Mengen gegen die Purge-Regel nachgerechnet (`purge_pruefen`), Parität ≤ 1e-9, Modellbindung
der Hülle; erst wenn alle vier Varianten bestehen, werden die Modelldateien geschrieben. Das Training prüft die installierten Versionen
gegen `requirements/forschung.lock.txt`. Die Datensicht rechnet die Datensätze im Speicher, trägt sie ein und schreibt sie erst danach.

**Auswertung:** je Variante drei Läufe des unveränderten Takts mit der Hülle (Hauptprofil, Kosten × 1,5, Kommission 3,25), Bewertung wie F-04 (alle Kriterien des 85-%-Tors, Zufallsbasis über die gefilterten Einstiege). Technik-Kriterium zusätzlich: Datensatz-Parität (Takt-Signale des Hauptprofils = Entscheidungen der Hülle aus den Datensatz-Merkmalen, 100 %). Vor 2013 hat die Hülle kein Modell; das Konto startet damit 2013 mit dem Startkapital.

**Ablauf:**
```
kit forschung vorab --lauf F-05 --prereg-ok "…"   ─► PREREG_SIGNED F05-META, F05-DATEN (Code-Liste CODE_F05, mechanik_hash)
python -m forschung.runde2 daten                  ─► Vorprüfung ─► Kerzen der F-04-Abzüge (Hash-gebunden, Zeitbasis W1)
                                                     ─► Datensätze work/f05/ ─► DATA_VIEW F05-DATEN (nur Hashes, Anzahlen)
python -m forschung.runde2 entwicklung            ─► Vorprüfung ─► TRIAL BEGINN ×4 ─► Training, Modelle, Parität
                                                     ─► 12 Takt-Läufe ─► Bericht berichte/forschung/<datum>_runde2 ─► TRIAL ERGEBNIS ×4
kit forschung pruefen                             ─► alle Läufe: Kette, Code gegen die eigene Vorregistrierung, Vollständigkeit
```

## 5c. Richtungsmodell (F-05b)

**Zweck** (Vorregistrierung `docs/bot/prereg/F05B_ENTWURF.md`, Runde 3 – die letzte nach V9): Runde 2 zeigte, dass der Meta-Filter
Marktphasen wählt, in denen das Ziel in beide Richtungen leichter erreicht wird, aber keine Richtung. Das Richtungsmodell schätzt je
Entscheidungspunkt beide Richtungen zu **denselben Abständen** (die Geometrie hebt sich auf) und handelt die besser geschätzte, wenn ihr
Vorsprung |p_Kauf − p_Verkauf| größer als d* ist.

| Teil | Ort |
|---|---|
| Hülle `Richtungsfilter`, Spiegeln von SL/TP, Prüfung „handelbar“, kompakte Modellform | `kit/strategy/richtung.py` (Standardbibliothek; Merkmale und Modellrechnung aus `meta_filter`) |
| Datensatz (zwei Labels je Punkt), Purge über beide Ausstiege, Auswertung, Bericht | `kit/research/richtung.py` (Plan, Embargo, Schwellenregel, Kerzen wie im Takt aus `meta`) |
| Training (Kauf- und Verkaufsmodell je Fenster, Schwelle d*), Aufruf | `forschung/richtung_training.py`, `forschung/runde3.py` (`.venv-forschung`) |
| eingefrorene Modelle | `forschung/modelle/F05B/<Variante>.json` (privat, nicht im Spiegel) |

**Handelbar** (nur diese Punkte gehen in Datensatz, Training und Entscheidung): im Handelsfenster des Takts und Stop ≤ 3 × Ziel für beide
Richtungen, geprüft wie im Takt mit auf das Raster gerundeten SL/TP gegen den Einstieg. Das ist nötig, weil einige frühe EURUSD/GBPUSD-Kerzen
eine Stelle mehr als das Raster tragen; dort lehnt der Takt Stop = 3 × Ziel nach der Rundung knapp ab. **Entscheidung** wie §5b
(Fenster, Embargo, Modellbindung beider Modelle), dann Richtung = größere Schätzung, gehandelt bei Vorsprung > d*. **Schwelle d***: kleinste
aus {0,00 … 0,40} mit der höchsten Wilson-Untergrenze der Validierungs-Trefferquote der gewählten Richtung, mindestens 50 Signale.
**Modelldatei:** HGB-Bäume kompakt (Blatt = Wert, innerer Knoten = Merkmal, Schwelle, links, rechts, fehlend_links), verlustfrei;
`meta.ausfuehren`-gleicher Ablauf prüft nach dem Schreiben, dass jedes geladene Modell bitgleich rechnet. Der Bericht zeigt zusätzlich den
Richtungsvorsprung im Datensatz (Quote der gewählten Richtung gegen das Mittel beider Richtungen) und den Geometriewert Stop/(Stop + Ziel).

Ablauf: `kit forschung vorab --lauf F-05b --prereg-ok "…"` → `python -m forschung.runde3 daten` → `python -m forschung.runde3 entwicklung`
→ `kit forschung pruefen`.

## 6. Zielbetrieb auf dem Windows-VPS

| Thema | Entscheidung | Begründung |
|---|---|---|
| Rechner | Windows Server, ein VPS für Bot + MT5 (+ Agent) | MT5 und `MetaTrader5` laufen nur unter Windows |
| Sitzung | Benutzer `kitbot` mit Autologon; Bot über Aufgabenplanung bei Anmeldung | MT5 ist eine GUI-Anwendung, das Python-Paket braucht ein laufendes Terminal in derselben Sitzung; Dienste in Sitzung 0 funktionieren dafür nicht |
| Trennung | `kitbot` (Bot) / `kitdev` (Agent) / Administrator; Live später getrennt | NTFS-Profilrechte schützen die Bot-Ablage technisch, nicht nur per Regel |
| Neustart | `bot_dienst.ps1`: Neustart mit Pause nach Fehlern, nie nach einem Sicherheits-Ende (Exit 2) | übersteht Terminal-Updates, Netzwackler und das Wochenende |
| Überwachung | Status-Export alle 15 min, Herzschlag-Ping an externen Dienst | auf einem VPS sieht niemand Windows-Benachrichtigungen |
| Sicherung | täglich lokal (30 Tage) + außer Haus | Journal = Wahrheit (Anker, Sperren, Tor T) |
| Zusatzdienste | außerhalb des Geldpfads, bevorzugt auf einem Linux-Begleiter | siehe [VPS_IDEEN.md](VPS_IDEEN.md) |

## 7. Release-Modell

1. Der Agent entwickelt im Repo, Tests grün, `tools/publish.py lauf` → Commit `<Lauf-ID>: …` + Tag `lauf/<ID>` → privates GitHub, danach der bereinigte öffentliche Spiegel.
2. Der Bot läuft **nie aus dem Arbeitsordner**, sondern aus `kit installieren --tag <tag>`: `git archive` von `kit/`, `config/`, `requirements/` nach `%USERPROFILE%\KI-Trading-Bot\app\<tag>`. Die Kopie ist unveränderlich; vor jedem Start wird ihr `mechanik_hash` gegen `INSTALLATION.json` geprüft.
3. Tor T wird je `mechanik_hash` gezählt. Neue Bedienfunktionen (gleicher Hash) setzen die Messung fort, ein geänderter Geldpfad beginnt sie neu.

## 8. Repo-Struktur

| Pfad | Inhalt | Status |
|---|---|---|
| `kit/` | der Bot | lebend |
| `kit_tests/` | Tests des Bots (pytest, hypothesis); `differenz_v4/` vergleicht mit der eingefrorenen Referenz und ihren Orakeln; `backtest_hilfen.py` erzeugt synthetische Kerzen; `daten/` feste Prüfproben (z. B. Modell-Parität scikit-learn) | lebend |
| `config/` | `kit_demo.toml` (Betrieb), `tore.toml` (Schwellen, eingefroren, SHA-gepinnt), `trade_test.toml` (Verfahren Tor 85, eingefroren, SHA-gepinnt in `kit/gates/trade_test.py`), `kostenprofil/` (Kostenstartwerte und Spreadprofil der Datensicht, privat, nicht im Spiegel) | lebend / eingefroren / privat |
| `deploy/windows-vps/` | Einrichtungs- und Betriebsskripte für den VPS | lebend |
| `docs/` | diese Dokumentation; `docs/bot/` Betriebsentscheidungen, Notfall, Rauchtest, Prompts, Vorregistrierungen | lebend |
| `berichte/` | redigierte Messberichte (Tor T, Daten); `berichte/forschung/` Entwicklungsberichte (nur Prozent, R, Anzahlen, Trades je Monat) | lebend |
| `forschung/` | `versuchsprotokoll.jsonl` – Versuchsprotokoll der Forschung (Hashkette, Einträge nur über kit-Code; entsteht mit dem ersten `kit forschung vorab`); `meta_training.py`, `runde2.py` – Training und Aufruf der Runde 2 (scikit-learn, nur `.venv-forschung`); `modelle/` – eingefrorene Modelle | lebend; Protokoll nur anhängen |
| `tools/` | `publish.py` (Veröffentlichung), `kit_scan.py` (Geheimnis-Scan), `kerntests.py`, `agent_waechter.py` (Hook, nur Betreiber), `dev.ps1`, `repo_regeln.json` | lebend |
| `requirements/` | hash-gesperrte Lockfiles (Bot-Laufzeit: Teil des `mechanik_hash`; `forschung.lock.txt` nur für `.venv-forschung`) | lebend |
| `referenz/` | eingefrorene v4-Referenz der Konzeptphase (51 Module, 17 Orakel, 24 Register, 35 Kerntest-Module, Spezifikationen) – nur als Orakel in Tests, nie vom Bot importiert (`referenz/README.md`, privat; im Spiegel nur die von Tests gebrauchten Dateien) | eingefroren, genutzt |
| `.githooks/`, `.claude/`, `.github/` | Git-Hooks, Agent-Wächter-Einstellungen (nur Betreiber), CI | lebend |

Die Konzeptphase (C-01 … C-12) ist vollständig in den Git-Tags `konzept-c11-gruen` (letzter grüner Stand) und `konzept-c12-wip` gesichert. Wiederherstellen: `git worktree add ..\v4_konzept konzept-c12-wip`.
