# KI-Trading MT5 – Fast-Track zum Demo-Bot (öffentliche Kurzfassung)

Stand 04.10.2026. Bereinigte Fassung des privaten Plans F-1 (ohne Betreiber-, Sicherheits- und Finanzdetails).

## Ziel
Ein schlanker, sicherer MetaTrader-5-Bot (`kit/`) in Python, der zunächst ausschließlich auf einem **Demokonto** handelt. Freigaben folgen messbaren Toren; Echtgeld schaltet nie die Software oder ein KI-Agent, sondern nur der Betreiber.

## Bausteine
- **Geldpfad** (deterministisch, Decimal): Journal vor dem Senden, Klärung unbekannter Orderzustände ohne Blind-Wiederholung, Server-Stop-Loss und -Take-Profit im Eröffnungsauftrag, Abgleich Journal ↔ Broker, Kill-Stufen K1–K3.
- **Demo-Wächter:** jede Sendung nur bei Kontomodus DEMO und eigenem Demo-Terminal; Live-Pfad hart gesperrt.
- **Risiko:** Hebelband mit Prüfpunkten, Tagesbudget, Verlustsperre, höchstens eine offene Strategieposition.
- **Forschung:** Geld-Backtester mit derselben Takt-Logik wie der Bot, vorregistrierte Strategien, Versuchsprotokoll, einmaliger Holdout; optional ein vorregistrierter, offline trainierter Meta-Filter (Laufzeit nur Standardbibliothek). Kein Sprachmodell trifft Handelsentscheidungen.

## Tore
| Tor | Bedingung (Kurzfassung) |
|---|---|
| Technik | ≥ 300 gesendete Orderoperationen, ≥ 95 % fehlerfrei, Null-Toleranz (z. B. keine Position > 30 s ohne Stop-Loss, keine Sendung auf Nicht-Demo-Konten) |
| Trade-Test | ≥ 85 % Gewinntrades bei ≥ 200 Trades außerhalb der Anpassung + einmaliger Holdout; parallel: Erwartungswert > 0 (Bootstrap-Untergrenze), Gewinnfaktor ≥ 1,2, Stop ≤ 3× Ziel, Trefferquote über einer Zufallsbasis mit identischer Ausstiegslogik |
| Demo-Live | ≥ 100 Trades und ≥ 3 Monate mit ≥ 95 % Gewinntrades plus Parallel-Schutz → Grundlage für eine Entscheidung des Betreibers |
| Stopp | Trefferquote der letzten 50 Trades (ab 20) ≤ 50 % → alles schließen, Sperre |

## Ehrliche Einordnung
Bei Ziel/Stop 1:3 ergibt Zufall etwa 75 % Treffer; 85 % entsprechen ≈ +0,13 R, 95 % ≈ +0,27 R je Trade (R = Stop-Abstand, vor Kosten). Eine Strategie mit wahren 85 % besteht beide Stichproben-Hürden nur in etwa einem von drei Fällen. Wahrscheinlichster Ausgang: technisch einwandfreier Demo-Betrieb ohne belegten Vorteil. **Keine Anlageberatung, keine Gewinnzusage.**

## Laufplan
F-00 Neustart · F-00b Veröffentlichung/CI · F-01 Geldpfad-Kern auf SIM · F-02 MT5-Anschluss + erster Demo-Trade · F-03/F-03b Bot-Code + Technik-Messung · F-04 Backtester + Trade-Test · F-05 Meta-Filter · F-06 Holdout · F-07 Demo-Live-Start.
