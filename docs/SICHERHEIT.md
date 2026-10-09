# Sicherheit

Bedrohungsmodell, Schutzschichten und Restrisiken. Seit F-03g öffentlich.

## 1. Was geschützt wird – und wovor

| Gut | Bedrohung | Wichtigste Gegenmaßnahme |
|---|---|---|
| Echtgeld | Bot sendet versehentlich an ein Live-Konto | Live-Riegel im Code (wirft immer); Demo-Prüfung vor **jeder** Sendung + Gegenprobe; Allowlist der Demokonten (HMAC); Live nur auf eigenem Rechner/Benutzer ohne Agent (Plan §6.2) |
| Demokonto/Messung | fehlerhafte Orders, Doppel-Fills, verlorene Sperren | Journal vor Netz, UNBEKANNT statt Neusenden, Abgleich, Null-Toleranz-Sperren, Umzugs-Tor, Schreibsperren |
| Sperren (LOSS_LOCK, 50 %, K3) | Aufheben ohne Betreiber | PIN (scrypt) nur interaktiv; nie in Agentensitzungen (`CLAUDECODE`); Wächter verbietet `kit entsperren|pin-setzen|freigeben|live|sichern` |
| Zugangsdaten | Agent oder Skript sieht/speichert Passwörter | Bot meldet sich nie an (`initialize` ohne login); Zugangsdaten-Schlüssel in Config/Journal verboten; Passwörter nur interaktiv durch den Betreiber |
| Repo/Öffentlichkeit | Leak von Geheimnissen, Benutzerpfaden, privaten Hosts | `kit_scan` (Diff + Baum), Sperrliste außerhalb des Repos, Positivliste + Rescan für den Spiegel, Hooks ohne Umgehung |
| VPS | Einbruch über RDP, Fremdsoftware neben dem Geldpfad | Tailscale statt offenem RDP, 2FA, Defender, Firewall, getrennte Benutzer, keine Zusatzdienste im Bot-Benutzer |

## 2. Schutzschichten (von innen nach außen)

1. **Code (hart, nicht umgehbar ohne Codeänderung):** `live_guard`, Demo-Prüfung, Allowlist, Pflicht-SL/TP, Stop ≤ 3× Ziel, Hebelband, Tagesbudget, LOSS_LOCK, 50-%-Stopp, Kill-Stufen, Journal-Hashkette, `tore.toml`-SHA-Pin, `mechanik_hash`-Prüfung vor jedem Start, Umzugs-Tor.
2. **Betriebssystem (VPS):** Bot-Ablage im Profil von `kitbot` → für `kitdev` (Agent) per NTFS unlesbar; Austausch nur über `C:\KI-Trading\austausch` (lesen). Live später unter eigenem Benutzer/Rechner.
3. **Agent-Wächter** (`tools/agent_waechter.py`, PreToolUse-Hook für jeden Werkzeugaufruf, fail-closed) + `permissions.deny` in `.claude/settings.json`: sperrt Bot-Ablage (alt und neu), MetaQuotes-Daten, Betreiberbefehle, eigene MT5-Skripte, Wächter-/Hook-Dateien, Force-Push/`--no-verify`/`git clean`, schreibende `gh`-Befehle, nicht gesperrte Paketinstallationen, Terminal-/Browser-/Planungswerkzeuge. **Nur aktiv, wenn Claude Code im Repo-Ordner gestartet wird** – jede Sitzung prüft das mit `echo KIT_WAECHTER_PROBE`.
4. **Git-Hooks** (`.githooks/`): Diff-Scan + ruff vor dem Commit, Laufkonvention und Vermerkpflicht, Schutz des Spiegels vor direktem Push.
5. **Prozess:** Betreiber-Freigaben nur im Laufprompt (z. B. `PREREG-OK`, `HOLDOUT-OK`, `AUFGABENPLANUNG-OK`), Entscheidungen in `docs/bot/ENTSCHEIDUNGEN.md`.

## 3. Offene Punkte (Stand 09.10.2026)

| Punkt | Wirkung | Erledigt durch |
|---|---|---|
| ~~**Wächter-Patch** `docs/bot/waechter_patch.diff` einspielen~~ – **erledigt seit F-04** | Der Hook schützt die Ablage `%USERPROFILE%\KI-Trading-Bot`, die Freigabe `StructuredOutput` ist enthalten. `kit installieren` prüft den Schutz weiterhin vor jeder Installation. | Betreiber (Patch in F-04 übernommen) |
| Sitzungen im Elternordner | Hook und Deny-Regeln laden nicht | Claude Code immer im Repo-Ordner starten |
| `live_guard.demo_pruefung(terminal_daten_pfad=…)` wird nirgends übergeben | Die Prüfung des Terminal-Datenpfads ist toter Code. Ersatz auf dem VPS: `terminal.pfad` ist gesetzt, und der Adapter prüft den verbundenen Terminalpfad. | Mechanik-Änderung nach dem Tor-T-Zertifikat |

## 4. Restrisiken (ehrlich)

- Der Wächter ist eine Sperrliste für Befehlstexte. Er fängt Versehen ab, aber keine gezielte Umgehung durch einen Agenten, der es darauf anlegt. Die harte Grenze liegt im Code (Demo-Prüfung) und auf dem VPS in den NTFS-Rechten.
- Auf demselben Windows-Benutzer wie der Bot gibt es keine echte Isolation. Deshalb laufen Agent und Bot auf dem VPS unter getrennten Benutzern.
- Ein kompromittierter VPS kann das Demokonto handeln lassen; Echtgeld ist dadurch nicht betroffen, weil Live hart gesperrt und später getrennt ist.
- Seit F-03g sind auch Wächter, Hooks, Wächter-Patch und diese Seite öffentlich. Das ist bewusst: Der Wächter schützt vor Versehen des Agenten und ist keine Geheimhaltung. Die harten Grenzen liegen im Code (Demo-Prüfung, Live-Sperre, PIN) und auf dem VPS in der Benutzertrennung. Zugangsdaten, Kontodaten und Benutzerpfade stehen nie im Repo.

## 5. Verhalten bei einem Sicherheitsvorfall

1. `kit stop --k3` (alles flach) **oder** im MT5 Algo Trading aus.
2. VPS-Zugang sperren: Tailscale-Gerät entfernen, Anbieter-Firewall zu.
3. Zugangsdaten rotieren ([WARTUNG.md](WARTUNG.md) §4), PIN ändern.
4. Journal und `MELDUNGEN.txt` sichern (`kit sichern`), Ursachenakte anlegen.
5. Erst nach Klärung neu starten; Entsperren nur mit PIN.
