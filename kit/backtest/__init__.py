"""Backtest (Plan F-1 §4–§5, Lauf F-04): derselbe Takt (kit.run.loop.Bot) über einem Historien-SIM.

- kosten:    Kostenprofil (Spread aus den Kerzen, Kommission je Lot und Seite, Swap mit Dreifachtag), Umrechnung nach EUR
- terminal:  BacktestTerminal – SIM-Terminal mit wechselnden Tickwerten, Kerzen je Zeitrahmen ohne Vorgriff, Swap-Buchung
- runner:    Schritt je H1-Schluss: Kerzen abspielen (SL/TP) → Umrechnung → Rollover → Bot.schritt(); Sperren als Schatten
- ausstieg:  schnelle Ausstiegsrechnung mit denselben Regeln (Parität, Zufallsbasis)
- paritaet:  Signal- und Trade-Parität (Takt gegen direkte Rechnung; später Demo-Live gegen Schatten-Backtest)

Nicht Teil des mechanik_hash; die Mechanik selbst (Bot, SIM, Risiko) wird nur benutzt, nie verändert.
"""
