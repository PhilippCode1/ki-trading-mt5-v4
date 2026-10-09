# NOTFALL – Bot sofort anhalten, Positionen schließen, wieder freigeben

Gilt für den Demo-Bot `kit` (Plan F-1). Alle Befehle in **deiner eigenen Konsole** im Ordner `KI_Trading_MT5_v4`:

```bat
.venv-bot\Scripts\python.exe -m kit <befehl>
```

Alle Laufzeitdaten liegen in **`%USERPROFILE%\KI-Trading-Bot`** (z. B. `C:\Users\<Name>\KI-Trading-Bot`). Bis 05.10.2026 lagen sie in `%LOCALAPPDATA%\kit`. Programme, die aus der Claude-Desktop-App heraus starten, schreiben dorthin aber nur in einen umgeleiteten Paket-Cache. Deine Konsole und der Bot hätten dann verschiedene Dateien gesehen.

Meldet ein Befehl **„erst kit umziehen“**, liegt in einer alten Ablage noch ein Journal, eine Freigabe oder eine STOP-Datei, die nicht im Umzugsbuch steht. Dann `kit umziehen` ausführen:
- Der Befehl kopiert nur, überschreibt nie und löscht nichts.
- Hat die neue Ablage schon eigene Daten, übernimmt er die Sperren ins neue Journal. Ist das alte Journal unlesbar, setzt er vorsichtshalber K2.
- Bricht er ab (z. B. Platte voll), einfach erneut ausführen; er setzt fort.
- Findet er mehrere alte Bestände, nennt er sie. Dann jeden einzeln mit `kit umziehen --von <Pfad>` übernehmen.
- Ist die alte Ablage eines abgebrochenen Umzugs nicht mehr da, schließt `kit umziehen --abschliessen` ihn mit K2 ab; danach prüfen und mit PIN entsperren.

Läuft noch ein Bot aus einer **alten** Installation, beendet ihn nur deren eigene `stop.cmd`. `kit stop` wirkt immer auf die neue Ablage und funktioniert auch vor dem Umzug.

Läuft der Bot aus einer Installation (`KI-Trading-Bot\app\<tag>`), geht alles genauso. Dort liegen auch `start_probe.cmd` und `stop.cmd`.

Ein Bot, den der Agent gestartet hat, läuft ohne Fenster als Teil der Claude-App. Schließt du die App, kann er mit enden; Positionen behalten dabei ihren Server-SL/TP. Für einen Dauerbetrieb unabhängig von der App so vorgehen:
1. `kit stop --beenden` ausführen.
2. Nach wenigen Sekunden `start_probe.cmd` im Installationsordner doppelklicken. Der Bot läuft dann in einem eigenen Fenster, und dort beendet ihn **Strg+C**.

## 1. Sofort: nichts Neues mehr – schnellster Weg

| Was | Wirkung | Aufheben |
|---|---|---|
| Im MT5-Terminal den Knopf **„Algo Trading“** ausschalten | Das Terminal nimmt keine Aufträge mehr an. Der Bot erkennt das beim nächsten Schutztakt (≤ 5 s) und beendet sich. Offene Positionen behalten ihren Server-SL/TP. | Knopf wieder an, Bot neu starten |
| `kit stop --k1` | **K1 – Pause:** keine neuen Einstiege. Schutz, Abgleich und planmäßiges Schließen laufen weiter. Wirksam in ≤ 1 s. | `kit stop --k1-aufheben` |
| `kit stop --k2` | **K2 – Halt:** wie K1, aber dauerhaft (auch nach Neustart) | nur `kit entsperren --grund K2` (PIN) |
| `kit stop --k3` | **K3 – Flach:** alle **eigenen** Positionen (Strategie und Probe) werden per Ticket geschlossen, Ziel ≤ 60 s; danach wie K2. Fremde und manuelle Positionen werden nie angefasst. | nur `kit entsperren --grund K3` (PIN) |
| `kit stop --beenden` oder **Strg+C** im Bot-Fenster | Takt endet geordnet. Positionen bleiben mit Server-SL/TP offen. | Bot neu starten |

Ohne Konsole: Lege die Datei `%USERPROFILE%\KI-Trading-Bot\probe\STOP` an (bzw. `...\demo\STOP`) mit dem Inhalt `K1`, `K2` oder `K3`. Die Kodierung ist egal. Eine unlesbare oder leere STOP-Datei gilt als K1. Eine STOP-Datei mit dem Wort `DRILL` legt nur der Bot selbst für Kill-Übungen an; sie setzt keine dauerhafte Sperre.

## 2. Positionen selbst schließen

Im MT5-Terminal kannst du jede Position jederzeit schließen. Der Bot erkennt den manuellen Eingriff, sperrt Einstiege in diesem Symbol und meldet es. Fremde Positionen fasst er nie an.

## 3. Was der Bot von selbst stoppt

| Auslöser | Reaktion | Aufheben |
|---|---|---|
| Konto ist nicht DEMO (REAL/Wettbewerb) | 0 Sendungen, Sperre `NICHT_DEMO`, Prozessende | PIN, nach Prüfung des Terminals |
| Konto nicht registriert / Algo Trading aus | 0 Sendungen, Prozessende | Konto registrieren bzw. Knopf an, neu starten |
| Konto ist ein Netting-Konto | 0 Sendungen, Prozessende (Fremdvolumen würde mit eigenen Positionen verschmelzen) | Hedging-Demokonto verwenden |
| Equity ≤ 75 % des Startankers | `LOSS_LOCK`: K3 + Sperre | PIN |
| Trefferquote der letzten 50 Strategie-Trades (ab 20) ≤ 50 % | `STOP50`: K3 + Sperre | PIN (Zählfenster beginnt neu) |
| Tagesverlust ≥ 3 % (ab Servertag-Anker) | keine Einstiege bis zum nächsten Servertag | automatisch |
| Stop-out beim Broker | `STOP_OUT`: K2 + Meldung | PIN |
| Technikfehler: Position > 30 s ohne SL, widerlegter Negativnachweis, eigene Position ohne Journal, Abgleichdifferenz, Ausgang > 15 min unbekannt | `NULLTOLERANZ`: K2 + Meldung | PIN, nach Ursachenklärung |
| ≥ 3 abgelehnte Sendungen in den letzten 20 | 30 Minuten keine Einstiege + Meldung | automatisch |
| Terminal 10× hintereinander nicht erreichbar | Prozessende (Server-SL/TP schützen) | Terminal prüfen, neu starten |

Meldungen stehen in `%USERPROFILE%\KI-Trading-Bot\<modus>\MELDUNGEN.txt`. Bei Warnungen und Alarmen kommt zusätzlich eine Windows-Benachrichtigung. `kit status` zeigt den Zustand, die Sperren und die letzten Meldungen.

## 4. Wieder freigeben (nur du, mit PIN)

1. **Einmalig:** `kit pin-setzen` (mindestens 10 Zeichen). Die PIN wird nur als scrypt-Hash gespeichert. Gib sie nie im Chat ein. Nach 5 falschen Eingaben ist die PIN-Eingabe 1 Stunde gesperrt.
2. Den Bot beenden. Entsperren geht nur, wenn er nicht läuft.
3. Ursache prüfen: `kit status`, `MELDUNGEN.txt` und die Positionen im Terminal.
4. `kit entsperren --grund <K2|K3|LOSS_LOCK|STOP50|STOP_OUT|NULLTOLERANZ|NICHT_DEMO|ALLE>`
5. Bot neu starten.

Fehlt die Zustandsdatei, obwohl ein Journal existiert, startet der Bot nicht. Gelöschte Dateien heben keine Sperre auf. `kit entsperren --grund ZUSTAND` baut den Zustand aus dem Journal neu auf; alle Sperren bleiben dabei bestehen.

`entsperren` und `pin-setzen` verweigern sich in einer Agentensitzung und ohne interaktive Konsole. Der Agent darf sie nie ausführen.

## 5. Kontowechsel

1. Bot beenden.
2. Im Terminal das neue **Demokonto** anmelden. Das machst nur du.
3. `kit konto-registrieren`
4. Bot neu starten.

Der Verlust-Anker gilt pro Modus und Journal. Nach dem Aufheben von LOSS_LOCK setzt der Bot beim nächsten Start einen neuen Anker auf die dann aktuelle Equity. Für einen sauberen Neuanfang mit neuem Konto vorher `kit sichern --ziel <Ordner>` ausführen und mit dem Agenten einen neuen Abschnitt vereinbaren.

## 6. Was der Agent darf – und was nicht

- **Solange das Projekt ruht** (seit F-05e) startet und stoppt der Agent den Bot nicht und führt weder `installieren` noch `umziehen` aus; auf dem VPS fasst er nichts unter `kitbot` an. Das Folgende gilt erst wieder mit ausdrücklicher Freigabe im Laufprompt und nur auf einem Einzelrechner.
- **Er darf:** den Bot auf DEMO starten und stoppen, `kit stop --k1/--k2/--k3/--beenden` setzen, `status`, `tor-t --stand`, `trockenlauf` und `installieren` ausführen sowie `umziehen`. `sichern` führt der Agent nie aus: Die Tagessicherung läuft als Aufgabe des Bot-Benutzers, mit Schlüsseln nur durch dich interaktiv.
- **Er darf nie:** entsperren, eine PIN setzen, Live schalten, sich anmelden, Zugangsdaten eingeben, Geld bewegen oder Dateien unter `%USERPROFILE%\KI-Trading-Bot\{demo,live,probe,freigaben,geheim,marktdaten,app}` direkt lesen oder ändern. Der Wächter sperrt das (Patch `docs/bot/waechter_patch.diff` seit F-04 im Repo); `kit installieren` prüft diesen Schutz vor jeder Installation.

Einordnung: Demo-Ergebnisse belegen die Technik, nicht einen Gewinn. Keine Anlageberatung, keine Gewinnzusage.
