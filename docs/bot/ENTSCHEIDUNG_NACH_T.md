# Entscheidungsvorlage nach dem Tor-T-Zertifikat (Stand 09.10.2026, Lauf F-05d)

> **Entschieden am 09.10.2026 (Lauf F-05e): ENDE** – das Projekt ruht, weiterentwickelt wird auf dem Windows-VPS. Diese Vorlage bleibt die Grundlage für eine Wiederaufnahme mit B oder C (Prompt F-05f in `docs/bot/PROMPTS.md`).

Nach V9 hat der Betreiber **A** gewählt (Pause der Strategieforschung, T-DAUER bis Tor T). Tor T ist jetzt bestanden und zertifiziert.
Diese Vorlage fasst die Lage zusammen und gibt die Empfehlung des Agenten. Sie ist keine Anlageberatung und keine Gewinnzusage; die
Entscheidung trifft allein der Betreiber.

## 1. Stand

| Punkt | Ergebnis |
|---|---|
| Tor T (Technik) | **BESTANDEN**, Zertifikat `berichte/tor_t/2026-10-09.md`: 378 Sendungen (Eröffnen 125, Schließen 128, Ändern 125), 100 % fehlerfrei, 0 Defekte, Kill-Drills ≈ 1 s; gebunden an `mechanik_hash` `4fab5281…` |
| Tor 85 (Strategie) | **nicht erreicht.** Drei Forschungsrunden, 20 Versuche: keine Richtungsinformation (Quote − Zufall −2,9 bis +0,7 Punkte, E[R] negativ), Holdout ungezogen |
| Tor 95 / Echtgeld | ohne Tor 85 nicht erreichbar |

**Betriebsbeobachtung (kein Defekt):** Der Bot beendete sich zweimal selbst mit der Meldung „Algo Trading/Handel am Terminal nicht
freigegeben“, die er sicherheitshalber so behandelt: am 06.10. um 00:25 (danach ruhte die Messung rund drei Tage) und am 09.10. um 09:55
(Neustart durch den Betreiber um 11:54). Dazu fuhr der Laptop am 09.10. gegen 04:00 selbst herunter. Es gab keine Fehlsendung. Für einen späteren Dauerbetrieb sind deshalb eine stabile Umgebung (VPS, Netzbetrieb, Update-Zeiten) und
gegebenenfalls ein toleranterer Umgang mit kurzen Aussetzern nötig. Letzteres ist eine Änderung am Geldpfad und verlangt eine neue
Messung.

## 2. Optionen

| Option | Was passiert | Nutzen | Kosten und Risiken |
|---|---|---|---|
| **B – Demo-Live ohne Tor als Datensammlung** | Vorregistrierte Variante handelt auf Demo, ausdrücklich ohne bestandenes 85-%-Tor; Messung von Signaltreue, Ist-Kosten, Ausführung | echte Ausführungsdaten über Wochen | Erwartungswert negativ (−0,03 bis −0,05 R je Trade), das Demokonto verliert erwartbar; 50-%-Regel und LOSS_LOCK greifen; braucht Demo-Live-Bausteine (Tor 95-Zähler, Statusseite) und einen dauerhaft laufenden Rechner; **führt nie zu Echtgeld** |
| **C – Weiter forschen mit neuer Idee** | Grundsätzlich andere Hypothese mit eigener Informationsquelle (nicht noch ein Filter auf denselben Kurssignalen); neue Vorregistrierung, keine Datensicht ohne PREREG-OK | einziger Weg, der überhaupt zu Tor 85 führen könnte | Aussicht nach drei Runden ohne jede Richtungsinformation gering; jede Runde kostet einen Lauf |
| **ENDE – Projekt ruhen lassen** | T-DAUER beenden, Stand dokumentieren. Zertifikat, Code, Berichte und Versuchsprotokoll bleiben erhalten; Wiederaufnahme jederzeit mit B oder C | keine laufenden Kosten, kein Rechner im Dauerbetrieb, nichts geht verloren | kein weiterer Erkenntnisgewinn |

Nicht Teil der Optionen: Tor- oder Risikowerte ändern (D3–D5, versiegelt).

## 3. Empfehlung des Agenten

**ENDE (Projekt ruhen lassen).** Die Technik ist belegt und zertifiziert. Einen Handelsvorteil gibt es nicht: Drei vorregistrierte Runden
fanden übereinstimmend keine Richtungsinformation. B sammelt Betriebsdaten für eine Strategie, die das Tor nicht bestehen kann, und führt
nie zu Echtgeld. C lohnt sich nur mit einer wirklich neuen Informationsquelle. Wenn du eine solche Idee hast, ist C der richtige Weg,
auch nach einer Pause.

**T-DAUER:** Die Messung hat ihr Ziel erreicht; weiteres Proben bringt keine neue Erkenntnis und braucht den Laptop im Dauerbetrieb. Du
kannst T-DAUER beenden, unabhängig von der Entscheidung – am besten **außerhalb des Probe-Fensters** (heute, Freitag, nach 20:05 Uhr
oder am Wochenende). `--beenden` lässt eine gerade offene Probe-Position mit ihrem Server-SL/TP stehen; nach Fensterende ist keine mehr
offen. Befehl (eigene PowerShell im Repo-Ordner): `.venv-311\Scripts\python.exe -m kit stop --beenden --modus probe` oder `stop.cmd` im
Installationsordner. Das Zertifikat bleibt gültig, solange der `mechanik_hash` gleich bleibt.

## 4. So entscheidest du

Im Prompt F-05e (`NEXT_PROMPT.md`) die Zeile `ENTSCHEIDUNG-NACH-T:` ausfüllen: `B`, `C: <Idee in einem Satz>` oder `ENDE`.
