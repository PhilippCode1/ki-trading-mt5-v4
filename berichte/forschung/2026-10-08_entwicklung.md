# Entwicklungsbericht F-04 (2026-10-08) – Ziel/Stop-Strategien auf der Entwicklungsperiode

Nur Prozent, R, Anzahlen und Trades je Monat. Vorregistrierung `docs/bot/prereg/F04_ENTWURF.md` (SHA-256 `621351dc9f169168…`), Versuchsprotokoll `forschung/versuchsprotokoll.jsonl`. Der Holdout (ab 01.07.2021) wurde nicht gezogen.

## Ergebnis in einem Satz

**Keine der 12 gezählten Varianten erfüllt alle Entwicklungskriterien des 85-%-Tors. Es gibt keinen Holdout-Kandidaten.** Das ist ein gültiges, vorab als wahrscheinlich benanntes Ergebnis (Prereg §1).

Technisch gültig (keine Sperre, kein Vorfall, Parität 100 %): alle Läufe.

## Kriterien je Variante (Hauptprofil, Entwicklung außerhalb der Anpassung)

| Variante | Trades | T/Monat | Quote | Wilson-UG | E[R] | E[R]-UG 95 % | GF | ØV/ØG | Zufall P95 | Max-DD | 50-%-Ereign. | Band/Budget | bestanden |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S-REV-01-k2.0-z0.50-r2 | 2288 | 22,4 | 59,9 % | 57,9 % | -0,102 | -0,128 | 0,76 | 1,96 | 61,5 % | 95,6 % | 51 | ja | **nein** |
| S-REV-01-k2.0-z0.50-r3 | 2626 | 25,8 | 69,2 % | 67,4 % | -0,073 | -0,093 | 0,80 | 2,82 | 71,0 % | 97,0 % | 2 | ja | **nein** |
| S-REV-01-k2.0-z0.75-r2 | 2425 | 23,8 | 60,6 % | 58,7 % | -0,087 | -0,111 | 0,83 | 1,85 | 63,6 % | 97,7 % | 50 | ja | **nein** |
| S-REV-01-k2.0-z0.75-r3 | 3520 | 34,5 | 70,1 % | 68,6 % | -0,049 | -0,065 | 0,87 | 2,70 | 72,0 % | 97,3 % | 4 | ja | **nein** |
| S-REV-01-k2.5-z0.50-r2 | 2423 | 23,8 | 57,8 % | 55,8 % | -0,132 | -0,156 | 0,72 | 1,90 | 60,8 % | 98,2 % | 88 | ja | **nein** |
| S-REV-01-k2.5-z0.50-r3 | 3175 | 31,1 | 67,9 % | 66,3 % | -0,087 | -0,105 | 0,76 | 2,78 | 71,4 % | 98,7 % | 6 | ja | **nein** |
| S-REV-01-k2.5-z0.75-r2 | 3064 | 30,1 | 60,4 % | 58,7 % | -0,087 | -0,109 | 0,79 | 1,94 | 64,1 % | 98,4 % | 82 | ja | **nein** |
| S-REV-01-k2.5-z0.75-r3 | 2531 | 24,8 | 68,9 % | 67,0 % | -0,067 | -0,087 | 0,80 | 2,77 | 72,6 % | 95,1 % | 4 | ja | **nein** |
| S-REV-02-L20-z0.5 | 2063 | 20,2 | 47,7 % | 45,6 % | -0,148 | -0,181 | 0,73 | 1,25 | 52,1 % | 98,2 % | 131 | ja | **nein** |
| S-REV-02-L20-z1.0 | 1902 | 18,7 | 34,4 % | 32,3 % | -0,181 | -0,227 | 0,71 | 0,74 | 39,0 % | 98,6 % | 7 | ja | **nein** |
| S-REV-02-L40-z0.5 | 2335 | 22,9 | 51,2 % | 49,2 % | -0,087 | -0,118 | 0,81 | 1,30 | 54,2 % | 90,3 % | 99 | ja | **nein** |
| S-REV-02-L40-z1.0 | 2035 | 20,0 | 36,7 % | 34,6 % | -0,110 | -0,155 | 0,76 | 0,76 | 39,9 % | 95,3 % | 15 | ja | **nein** |

Erfüllt je Kriterium (Anzahl Varianten von 12):

| trades | quote | erwartung_r | gewinnfaktor | verlust_zu_gewinn | zufallsbasis | drawdown | stop50 | band_budget | technik |
|---|---|---|---|---|---|---|---|---|---|
| 12 | 0 | 0 | 0 | 12 | 0 | 0 | 0 | 12 | 12 |

Schwellen (config/tore.toml [tor_85]): ≥ 200 Trades (das Tor zählt Entwicklung + Holdout gemeinsam; hier die Entwicklung allein), Quote ≥ 85 %, E[R]-Untergrenze > 0, Gewinnfaktor ≥ 1,2, Ø Verlust ≤ 3 × Ø Gewinn, Quote > 95. Perzentil der Zufallsbasis, Max-Drawdown < 25 %, kein 50-%-Ereignis (Folge oder Schatten-Sperre), Band, Budget und Stop ≤ 3 × Ziel beim Einstieg eingehalten, Lauf technisch gültig. „n. b.“ = nicht bewertbar = nicht bestanden. Gewinnfaktor und Ø Verlust/Ø Gewinn in EUR (Ø Verlust nur über Ergebnisse < 0), E[R] je Trade = Ergebnis / geplanter Verlust bis SL zu den Kosten des Laufs.

## Band-Wirkung und Quote Signal → Trade

| Variante | Signale | Trades | Signal→Trade | Hebel min/Ø/max | Fill − e (Ticks Ø/max) | Ablehnungen (häufigste) |
|---|---|---|---|---|---|---|
| S-REV-01-k2.0-z0.50-r2 | 15215 | 2288 | 15,0 % | 5,27/7,30/13,95 | 0,0/0 | BAND_UNTERGRENZE 6220, AUSSERHALB_FENSTER 4428, MAX_STRATEGIEPOSITIONEN 1153, TAGESBUDGET 711, BAND_OBERGRENZE 361 |
| S-REV-01-k2.0-z0.50-r3 | 15215 | 2626 | 17,3 % | 5,26/7,00/13,90 | 0,0/0 | AUSSERHALB_FENSTER 4429, BAND_UNTERGRENZE 4265, MAX_STRATEGIEPOSITIONEN 1705, TAGESBUDGET 1620, BAND_OBERGRENZE 311 |
| S-REV-01-k2.0-z0.75-r2 | 15215 | 2425 | 15,9 % | 5,26/6,93/14,08 | 0,0/0 | AUSSERHALB_FENSTER 4427, BAND_UNTERGRENZE 4216, MAX_STRATEGIEPOSITIONEN 2096, TAGESBUDGET 1739, BAND_OBERGRENZE 255 |
| S-REV-01-k2.0-z0.75-r3 | 15215 | 3520 | 23,1 % | 5,27/6,17/10,53 | 0,0/0 | AUSSERHALB_FENSTER 4426, MAX_STRATEGIEPOSITIONEN 4215, TAGESBUDGET 2789, STOP_ZU_ZIEL 211, SPREAD_HOCH 48 |
| S-REV-01-k2.5-z0.50-r2 | 7962 | 2423 | 30,4 % | 5,27/6,99/13,99 | 0,0/0 | BAND_UNTERGRENZE 2182, AUSSERHALB_FENSTER 1911, MAX_STRATEGIEPOSITIONEN 962, TAGESBUDGET 395, BAND_OBERGRENZE 63 |
| S-REV-01-k2.5-z0.50-r3 | 7962 | 3175 | 39,9 % | 5,26/6,55/13,95 | 0,0/0 | AUSSERHALB_FENSTER 1911, MAX_STRATEGIEPOSITIONEN 1577, TAGESBUDGET 908, BAND_UNTERGRENZE 222, STOP_ZU_ZIEL 123 |
| S-REV-01-k2.5-z0.75-r2 | 7962 | 3064 | 38,5 % | 5,26/6,55/13,89 | 0,0/0 | MAX_STRATEGIEPOSITIONEN 1941, AUSSERHALB_FENSTER 1911, TAGESBUDGET 966, BAND_UNTERGRENZE 31, SPREAD_HOCH 26 |
| S-REV-01-k2.5-z0.75-r3 | 7962 | 2531 | 31,8 % | 5,26/5,67/7,90 | 0,0/0 | MAX_STRATEGIEPOSITIONEN 2129, AUSSERHALB_FENSTER 1911, TAGESBUDGET 1242, STOP_ZU_ZIEL 123, SPREAD_HOCH 26 |
| S-REV-02-L20-z0.5 | 10901 | 2063 | 18,9 % | 5,27/6,92/14,01 | 0,0/0 | AUSSERHALB_FENSTER 4410, MAX_STRATEGIEPOSITIONEN 1506, BAND_UNTERGRENZE 1415, TAGESBUDGET 810, STOP_ZU_ZIEL 582 |
| S-REV-02-L20-z1.0 | 10901 | 1902 | 17,4 % | 5,31/6,93/14,12 | 0,0/0 | AUSSERHALB_FENSTER 4407, MAX_STRATEGIEPOSITIONEN 1853, BAND_UNTERGRENZE 1364, TAGESBUDGET 1172, BAND_OBERGRENZE 80 |
| S-REV-02-L40-z0.5 | 7650 | 2336 | 30,5 % | 5,28/6,25/10,16 | 0,0/0 | AUSSERHALB_FENSTER 3025, MAX_STRATEGIEPOSITIONEN 1305, TAGESBUDGET 534, STOP_ZU_ZIEL 401, SPREAD_HOCH 43 |
| S-REV-02-L40-z1.0 | 7650 | 2036 | 26,6 % | 5,28/6,39/10,74 | 0,0/0 | AUSSERHALB_FENSTER 3021, MAX_STRATEGIEPOSITIONEN 1593, TAGESBUDGET 916, SPREAD_HOCH 43, TAGESSTOPP 21 |

## Kosten-Gegenproben

Hauptprofil = Kommission 0 (erster Demo-Trade). „Kosten × 1,5“ verschärft Spread und Swap-Belastungen des Hauptprofils; seine Kommission bleibt 0 (0 × 1,5). Die Kommission prüft die eigene Gegenprobe mit 3,25 je Lot und Seite (Startwert cost_truth).

| Variante | Quote (Haupt) | Quote (Kosten × 1,5) | GF (Kosten × 1,5) | Quote (Kommission 3,25) | E[R] (Kommission 3,25) | GF (Kommission 3,25) | bestanden (3,25) |
|---|---|---|---|---|---|---|---|
| S-REV-01-k2.0-z0.50-r2 | 59,9 % | 59,9 % | 0,76 | 61,8 % | -0,120 | 0,70 | nein |
| S-REV-01-k2.0-z0.50-r3 | 69,2 % | 68,4 % | 0,77 | 70,4 % | -0,093 | 0,74 | nein |
| S-REV-01-k2.0-z0.75-r2 | 60,6 % | 59,8 % | 0,81 | 60,9 % | -0,116 | 0,78 | nein |
| S-REV-01-k2.0-z0.75-r3 | 70,1 % | 69,7 % | 0,84 | 70,5 % | -0,071 | 0,82 | nein |
| S-REV-01-k2.5-z0.50-r2 | 57,8 % | 55,6 % | 0,67 | 58,2 % | -0,166 | 0,64 | nein |
| S-REV-01-k2.5-z0.50-r3 | 67,9 % | 65,8 % | 0,70 | 68,2 % | -0,112 | 0,69 | nein |
| S-REV-01-k2.5-z0.75-r2 | 60,4 % | 58,9 % | 0,74 | 60,2 % | -0,120 | 0,72 | nein |
| S-REV-01-k2.5-z0.75-r3 | 68,9 % | 67,5 % | 0,75 | 68,2 % | -0,098 | 0,72 | nein |
| S-REV-02-L20-z0.5 | 47,7 % | 44,2 % | 0,70 | 46,2 % | -0,190 | 0,68 | nein |
| S-REV-02-L20-z1.0 | 34,4 % | 30,6 % | 0,64 | 31,3 % | -0,271 | 0,63 | nein |
| S-REV-02-L40-z0.5 | 51,2 % | 47,3 % | 0,71 | 48,7 % | -0,150 | 0,72 | nein |
| S-REV-02-L40-z1.0 | 36,7 % | 33,4 % | 0,70 | 35,0 % | -0,175 | 0,68 | nein |

## Zusatzkriterien (nur berichtet, V2: ZUSATZKRITERIEN-OK = nein)

Teilperioden: vier gleich lange Abschnitte der Testzeit; „positiv“ nach dem Nettoergebnis in EUR, in Klammern die R-Summen.

| Variante | DSR (N, N_eff) | Teilperioden positiv (R-Summen) | GF bei Kosten × 1,5 > 1,0 |
|---|---|---|---|
| S-REV-01-k2.0-z0.50-r2 | 0,000 (12, 5,2) | 0/4 (-127,7, -99,0, -6,1, -1,0) | nein |
| S-REV-01-k2.0-z0.50-r3 | 0,000 (12, 5,2) | 0/4 (-59,4, -107,8, -23,5, 0,0) | nein |
| S-REV-01-k2.0-z0.75-r2 | 0,000 (12, 5,2) | 0/4 (-70,1, -112,0, -28,5, 0,0) | nein |
| S-REV-01-k2.0-z0.75-r3 | 0,000 (12, 5,2) | 0/4 (-34,1, -49,3, -33,7, -53,8) | nein |
| S-REV-01-k2.5-z0.50-r2 | 0,000 (12, 5,2) | 0/4 (-93,4, -162,0, -62,4, -1,0) | nein |
| S-REV-01-k2.5-z0.50-r3 | 0,000 (12, 5,2) | 0/4 (-49,1, -86,0, -73,7, -67,1) | nein |
| S-REV-01-k2.5-z0.75-r2 | 0,000 (12, 5,2) | 0/4 (-61,5, -65,6, -80,0, -60,2) | nein |
| S-REV-01-k2.5-z0.75-r3 | 0,000 (12, 5,2) | 0/4 (-41,5, -26,0, -45,1, -57,3) | nein |
| S-REV-02-L20-z0.5 | 0,000 (12, 5,2) | 0/4 (-82,2, -120,3, -80,6, -22,7) | nein |
| S-REV-02-L20-z1.0 | 0,000 (12, 5,2) | 0/4 (-125,8, -113,4, -74,7, -30,5) | nein |
| S-REV-02-L40-z0.5 | 0,000 (12, 5,2) | 0/4 (-69,3, -53,8, -57,0, -22,7) | nein |
| S-REV-02-L40-z1.0 | 0,000 (12, 5,2) | 0/4 (-96,2, -52,4, -44,5, -31,5) | nein |

## Referenz S-BL-01 (BL-TFD1, zählt nie für das Tor, kein Server-TP)

Trades 267, Trades je Monat 2,6, Quote 32,2 %, E[R] 0,026, Gewinnfaktor in R 1,04. Plausibilitätsanker: ein Trendfolger trifft selten und lebt von wenigen großen Gewinnen.

## Technik, Parität, Schatten

Signal-Parität = gleiche Signale / max(Takt, direkt); Trade-Parität über alle Trades ohne Zwangsausstieg (Band/K3). Schattenereignisse über den ganzen Lauf inkl. Anlaufjahre.

| Variante | Profil | Technik gültig | Signal-Parität (gleich; Takt/direkt) | Trade-Parität (geprüft, Zwang) | Schattenereignisse | offen am Ende |
|---|---|---|---|---|---|---|
| S-REV-01-k2.0-z0.50-r2 | Haupt | ja | 100,00 % (20716; 20716/20716) | 100,00 % (4384, 0) | {'STOP50': 62, 'LOSS_LOCK': 5} | 0 |
| S-REV-01-k2.0-z0.50-r3 | Haupt | ja | 100,00 % (20716; 20716/20716) | 100,00 % (4296, 0) | {'LOSS_LOCK': 5, 'STOP50': 1} | 0 |
| S-REV-01-k2.0-z0.75-r2 | Haupt | ja | 100,00 % (20716; 20716/20716) | 100,00 % (3930, 0) | {'LOSS_LOCK': 8, 'STOP50': 38} | 0 |
| S-REV-01-k2.0-z0.75-r3 | Haupt | ja | 100,00 % (20716; 20716/20716) | 100,00 % (4593, 0) | {'LOSS_LOCK': 17, 'STOP50': 2} | 0 |
| S-REV-01-k2.5-z0.50-r2 | Haupt | ja | 100,00 % (10788; 10788/10788) | 100,00 % (3714, 0) | {'STOP50': 65, 'LOSS_LOCK': 1} | 0 |
| S-REV-01-k2.5-z0.50-r3 | Haupt | ja | 100,00 % (10788; 10788/10788) | 100,00 % (4272, 0) | {'STOP50': 6, 'LOSS_LOCK': 10} | 0 |
| S-REV-01-k2.5-z0.75-r2 | Haupt | ja | 100,00 % (10788; 10788/10788) | 100,00 % (4051, 0) | {'STOP50': 46, 'LOSS_LOCK': 6} | 0 |
| S-REV-01-k2.5-z0.75-r3 | Haupt | ja | 100,00 % (10788; 10788/10788) | 100,00 % (3229, 0) | {'LOSS_LOCK': 22, 'STOP50': 2} | 0 |
| S-REV-02-L20-z0.5 | Haupt | ja | 100,00 % (14580; 14580/14580) | 100,00 % (3026, 0) | {'STOP50': 88, 'LOSS_LOCK': 5} | 0 |
| S-REV-02-L20-z1.0 | Haupt | ja | 100,00 % (14580; 14580/14580) | 100,00 % (2747, 0) | {'STOP50': 5, 'LOSS_LOCK': 3} | 0 |
| S-REV-02-L40-z0.5 | Haupt | ja | 100,00 % (10211; 10211/10211) | 100,00 % (3106, 0) | {'STOP50': 60, 'LOSS_LOCK': 5} | 1 |
| S-REV-02-L40-z1.0 | Haupt | ja | 100,00 % (10211; 10211/10211) | 100,00 % (2727, 0) | {'STOP50': 9, 'LOSS_LOCK': 6} | 1 |

## Daten und Kostenprofil

21 Abzüge (7 Symbole × H1/H4/D1), je Abzug Hash geprüft; 0 Kerzen, die über den Holdout-Beginn hinausreichen, verworfen (nie verwendet). Spread je Kerze aus den Daten; das Spreadprofil der Datensicht ist privat (privat (SHA-256 8510f0bc48fff643…)).
Kommission: Hauptprofil 0 je Lot und Seite (erster Demo-Trade), Gegenprobe 3,25 (Startwert cost_truth). Swap: Swappunkte des Startprofils (Stand 2026, privat), Dreifachtag Mittwoch. Die Größe rechnet der Takt wie im Betrieb mit 3,25 je Lot und Seite (config/kit_demo.toml).

## Grenzen dieser Auswertung

- Ausführung auf H1-Kerzen: innerhalb einer Kerze gilt SL vor TP (vorsichtig), Lücken füllen zum Eröffnungskurs; kein Schlupf darüber hinaus.
- Spread je Kerze aus dem MT5-Kerzenfeld; das Feld kann den kleinsten Spread der Stunde zeigen. Die Gegenprobe Kosten × 1,5 deckt das nur teilweise.
- Swapsätze von 2026 für 2010–2021 (damalige Zinsdifferenzen waren anders); Haltedauer höchstens 24 h, also wenige Nächte je Trade.
- Zeitbasis: Der Datenabzug (F-02) hat die Kerzen in Serverzeit gespeichert; der Backtest rechnet sie mit dem festen Versatz +3 h nach UTC um. Der Server folgt der New-Yorker Sommerzeit (Datenprüfung: Wochenöffnung immer Mo 00:00 Serverzeit); im Winter (UTC+2) liegt das Handelsfenster deshalb 1 h später (09–23 Uhr Berlin, freitags bis 21 Uhr), Servermitternacht und Rollover bleiben richtig.
- Das Demokonto berechnet keine Kommission; ein Echtgeldkonto mit Rohspread kostet mehr (siehe Gegenprobe 3,25).
- Der Band-Prüfpunkt 21:30 Berlin läuft im Stundentakt beim ersten Schritt danach (22:00).
- S-REV-02 (H4): Im Backtest trägt die H4-Kerze den Spread der H1-Kerze mit demselben Schluss, damit der erwartete Einstieg e gleich dem Fill ist (Spalte „Fill − e“ = 0). Im Betrieb sieht die Strategie das MT5-Spreadfeld der H4-Kerze; dort kann der Fill um die Spreaddifferenz von e abweichen.
- Zeitbarriere = 24 h Wanduhr (Prereg: „24 Kerzen (24 h)“): Über Wochenende und Feiertage sind das weniger Kerzen; eine Position vom Freitag schließt beim ersten Schritt nach der Pause.
- Eine am Datenende (30.06.2021) noch offene Position zählt nicht (Spalte „offen am Ende“, höchstens 1).
- S-BL-01 (nur Referenz) nimmt den halben Median-Spread der ganzen Entwicklungsperiode als festen Kostensatz.
- Holdout-Grenze in UTC: D1/H4-Kerzen, die vor dem 01.07.2021 00:00 UTC beginnen, aber danach enden, werden verworfen (Spalte im JSON).
- Walk-Forward ohne angepasste Parameter: Die Varianten sind fest vorregistriert; die ersten 3 Jahre zählen nicht (nur Anlauf).

## Einordnung des Agenten (nach Sicht der Ergebnisse; Tabellen oben unverändert aus `kit forschung entwicklung`)

- **Kein Vorteil gegenüber Zufall.** Jede der 12 Varianten trifft etwas seltener als die zufällige Richtung mit denselben Einstiegszeiten
  und derselben Ausstiegslogik im Mittel (z. B. S-REV-01-k2.0-z0.75-r3: 70,1 % gegen 70,9 % Zufallsmittel, 95. Perzentil 72,0 %;
  S-REV-02-L40-z0.5: 51,2 % gegen 52,7 %). Die Trefferquoten folgen fast nur dem Stop/Ziel-Verhältnis (r = 3 → ~69 %, r = 2 → ~59 %,
  vgl. Vorab-Einordnung r/(1+r)); 85 % liegen weit außer Reichweite.
- **Erwartungswert negativ** (E[R] −0,05 bis −0,18, Gewinnfaktor 0,71–0,87) in allen drei Kostenprofilen; die Kommission 3,25 verschlechtert
  ihn weiter. Das Ergebnis hängt also nicht an einer günstigen Kostenannahme.
- **Band-Wirkung:** Das versiegelte Band erzwingt Hebel ≥ 5,25. Mit negativem Erwartungswert verliert das Konto über die Gesamtperiode
  97–99,6 % (Drawdown vom Hoch), im OOS-Teil 90–99 %. Häufigste Ablehnungen sind BAND_UNTERGRENZE (bei kleinem Konto übersteigt schon das
  kleinste Lot den Deckel bzw. das Ziel unterschreitet beim Kurs = TP die Untergrenze), das Handelsfenster, die eine erlaubte
  Strategieposition und das Tagesbudget; nach dem Absturz sind kaum noch Einstiege möglich (Teilperioden mit R-Summe 0).
- **Tagesbudget:** Der Takt hält die geplante Verlustgrenze ein (Band/Budget-Prüfung je Einstieg ohne Befund); realisierte Tagesverluste
  über 3 % kamen an 0–12 Tagen vor (Lücken über den SL, mehrere Verluste am selben Tag).
- **Technik:** alle 36 Läufe technisch gültig, Signal- und Trade-Parität 100 %, keine echte Sperre; LOSS_LOCK und STOP50 wären mehrfach
  eingetreten (Schattenereignisse).
- **Referenz S-BL-01** (Trendfolger, zählt nie): 267 Trades, 32 % Treffer, E[R] +0,03 – wie erwartet ein seltener Treffer mit großen
  Gewinnen, ohne belastbaren Vorteil.
- **Folgerung:** Kein Holdout-Kandidat. Laut Plan folgt Forschungsrunde 2 (F-05, Meta-Filter, höchstens 3 Runden). Ein Filter müsste die
  Trefferquote von ~70 % auf ≥ 85 % heben und dabei ≥ 200 Trades behalten, obwohl die Signale selbst nicht besser als Zufall sind – das
  ist sehr unwahrscheinlich.

Einordnung: Forschung auf historischen Daten belegt keinen künftigen Gewinn. Keine Anlageberatung, keine Gewinnzusage.
