# Entscheidungsvorlage nach V9 (Stand 09.10.2026, nach drei Forschungsrunden)

> **Entschieden am 09.10.2026 (Lauf F-05c): A – Pause der Strategieforschung.** Eingetragen in `docs/bot/ENTSCHEIDUNGEN.md`.
> Nächster Schritt: Tor-T-Zertifikat, sobald T-DAUER die Mindestzahlen erreicht (Lauf F-05d). Diese Vorlage bleibt als Grundlage unverändert.

V9 (`docs/bot/ENTSCHEIDUNGEN.md`): höchstens drei Forschungsrunden ohne Kandidat, danach entscheidet der Betreiber –
**weiter forschen / Demo-Live bewusst ohne Tor als Datensammlung / Pause**. Diese Vorlage fasst die Fakten zusammen und gibt die
Empfehlung des Agenten. Sie ist keine Anlageberatung und keine Gewinnzusage; die Entscheidung trifft allein der Betreiber.

## 1. Ergebnis der drei Runden

Alle Zahlen: Entwicklungsdaten 2013 bis 2021-H1 außerhalb der Anpassung, Hauptprofil, derselbe Takt wie im Betrieb, Holdout ungezogen.
„Zufall“ = Trefferquote einer zufälligen Richtung zu denselben Einstiegszeiten mit derselben Ausstiegslogik (Mittel aus 1.000 Wiederholungen).

| Runde | Lauf | Ansatz | Versuche | Trefferquote | Zufall | Quote − Zufall | E[R] je Trade | Ergebnis |
|---|---|---|---|---|---|---|---|---|
| 1 | F-04 | Ziel/Stop-Strategien S-REV-01 (H1), S-REV-02 (H4) | 12 | 34–70 % | jeweils knapp darüber | −0,1 bis −2,9 | −0,05 bis −0,18 R | kein Kandidat |
| 2 | F-05 | KI-Meta-Filter (logistische Regression, HistGradientBoosting) | 4 | 72,0 / 71,9 / 57,9 / 62,8 % | 72,9 / 72,3 / 57,8 / 63,5 % | −0,9 bis +0,1 | −0,03 bis −0,04 R | kein Kandidat |
| 3 | F-05b | Richtungsmodell (Kauf gegen Verkauf, nur handelbare Punkte) | 4 | 70,9 / 70,9 / 53,7 / 53,6 % | 71,8 / 71,4 / 53,1 / 52,9 % | −0,9 bis +0,7 | −0,035 bis −0,053 R | kein Kandidat |

Berichte: `berichte/forschung/2026-10-08_entwicklung.md`, `2026-10-09_runde2.md`, `2026-10-09_runde3.md`. Versuchsprotokoll: 20 gezählte
Versuche, `kit forschung pruefen` = VERIFIZIERT. Technik in allen Läufen gültig (Signal- und Trade-Parität 100 %; in den Runden 2 und 3 zusätzlich Datensatz-Parität 100 % im Haupt- und 3,25-Profil).

**Kernbefund:** Keiner der Ansätze erkennt eine Richtung besser als der Zufall. Runde 2 fand Marktphasen, in denen das Ziel in beide
Richtungen leichter erreicht wird; Runde 3 prüfte Richtung direkt und fand einen Vorsprung von −0,5 bis +0,1 Punkten.

## 2. Was das 85-%-Tor verlangt

Mit Stop ≤ 3 × Ziel (D4, V1) trifft eine zufällige Richtung bei S-REV-01 nach Kosten bereits rund 71–73 % (Runde 2: 72,3–72,9 %, Runde 3: 71,4–71,8 %). Für ≥ 85 % mit positivem
Erwartungswert und einer Quote über dem 95. Perzentil der Zufallsbasis braucht es rund **12 Prozentpunkte echten Richtungsvorsprung**
(bei S-REV-02 über 30 Punkte). Gemessen wurde in allen drei Runden praktisch null. Das Tor ist so gebaut, dass es nur ein Verfahren mit
deutlichem, belegtem Vorteil passiert – das ist gewollt (D3, D4) und schützt vor Echtgeld ohne Vorteil.

## 3. Optionen

| Option | Was passiert | Nutzen | Kosten und Risiken |
|---|---|---|---|
| **A – Pause der Strategieforschung** | Keine weitere Forschungsrunde. Die Technik-Messung T-DAUER läuft weiter bis Tor T (≥ 300 Sendungen); danach Tor-T-Auswertung und Zertifikat. Danach erneute Entscheidung mit neuer Idee oder Abschluss. | Die Technik (Orderweg, Sperren, Kill-Stufen) ist dann belegt; nichts geht verloren; keine weitere Forschung ohne Aussicht. | Kein Demo-Handel mit einer Strategie. |
| **B – Demo-Live bewusst ohne Tor (Datensammlung)** | Nach Tor T handelt der Bot eine vorregistrierte Variante auf Demo, ausdrücklich ohne bestandenes 85-%-Tor, nur um Betriebsdaten (Signaltreue, Ist-Kosten, Ausführung) zu sammeln. | Echte Ausführungsdaten; prüft den Betrieb unter Last. | Erwartungswert negativ (−0,03 bis −0,05 R je Trade): Das Demokonto verliert erwartbar; 50-%-Regel und LOSS_LOCK greifen früher oder später. Das 95-%-Tor ist so nicht erreichbar, Echtgeld bleibt ausgeschlossen. |
| **C – Weiter forschen mit neuer Idee** | Eine grundsätzlich andere Hypothese (nicht noch ein Filter auf denselben Signalen), neue Vorregistrierung, eigene Familie; V9 wird bewusst überschritten. | Chance auf einen echten Vorteil, falls die neue Idee einen anderen Ursprung hat. | Nach drei Runden ohne jede Richtungsinformation ist die Aussicht gering; jede Runde kostet einen Lauf. Ohne belegte neue Quelle eines Vorteils nicht sinnvoll. |

Nicht Teil der Optionen: Tor- oder Risikowerte ändern (D3–D5, versiegelt). Das darf nur der Betreiber, und eine Änderung nach drei
Datensichten würde die Aussagekraft jedes späteren Tests stark schwächen.

## 4. Empfehlung des Agenten

**Option A.** Begründung: Drei vorregistrierte Runden mit zusammen 20 Versuchen zeigen übereinstimmend keine Richtungsinformation;
eine vierte Runde mit ähnlichen Mitteln hat eine sehr geringe Aussicht. Die Technik-Messung läuft bereits und ist für jeden späteren Weg
nötig (D9). Nach dem Tor-T-Zertifikat kann der Betreiber ohne Zeitdruck über eine neue Idee (C) oder eine bewusste Datensammlung (B)
entscheiden.

## 5. So entscheidest du

Im Prompt F-05c (`NEXT_PROMPT.md`) die Zeile `ENTSCHEIDUNG-V9:` ausfüllen: `A`, `B` oder `C: <Idee in einem Satz>`. Der Agent trägt die
Entscheidung in `docs/bot/ENTSCHEIDUNGEN.md` ein und setzt sie um (A: Status und Tor-T-Stand; B: Vorbereitung, Start erst nach Tor T;
C: neue Vorregistrierung als Entwurf, keine Datensicht ohne dein PREREG-OK).
