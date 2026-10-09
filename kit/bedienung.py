"""Bedienung (F-03): Takt starten, Kill-Dateien, Entsperren mit PIN, Installieren, Sichern, Tor-T-Stand, Skripte, Trockenlauf.

Grenzen: `entsperren` und `pin_setzen` sind Betreiberfunktionen (die CLI verlangt eine interaktive Konsole, der Agent ist per Hook
gesperrt). Lesen neben dem laufenden Bot geschieht nur über journal.lesen(nur_lesen=True) – nie über Schreibpfade.
"""
from __future__ import annotations

import datetime as dt
import getpass
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

from kit import live_guard, paths, umzug
from kit.gates import ROOT, tore, zertifikat
from kit.gates.tor_t import auswerten, mechanik_hash
from kit.report.bericht import tor_t_markdown
from kit.report.redact import redigieren
from kit.state import pin as pinmod
from kit.state import sperren as sp
from kit.state.journal import Journal, JournalFehler
from kit.state.journal import lesen as journal_lesen
from kit.state.store import Schreibsperre, StateStore, ZustandFehler, stop_setzen, stop_stufe

UTC = dt.UTC
SCHREIB_MODI = ("probe", "demo")


class BedienFehler(RuntimeError):
    """Bedienschritt nicht erlaubt oder nicht möglich (klare Meldung an den Betreiber)."""


def _ablage(modus: str) -> Path:
    if modus == "live":
        live_guard.live_pruefen()
    return paths.ablage(modus)


# ---------------------------------------------------------------------------------------------------- Kill-Dateien
def stop(modus: str, *, stufe: int = 0, beenden: bool = False, k1_aufheben: bool = False) -> str:
    ablage = _ablage(modus)
    ablage.mkdir(parents=True, exist_ok=True)
    if beenden:
        (ablage / "BEENDEN").write_text("BEENDEN\n", encoding="utf-8")
        return "BEENDEN gesetzt – der Bot beendet sich im nächsten Takt (Positionen behalten Server-SL/TP)."
    if k1_aufheben:
        aktuell = stop_stufe(ablage)
        if aktuell >= 2:
            raise BedienFehler(f"STOP-Datei steht auf K{aktuell} – K2/K3 hebt nur der Betreiber mit PIN auf (kit entsperren).")
        stop_setzen(ablage, 0)
        return "K1 aufgehoben (STOP-Datei entfernt)."
    if stufe not in (1, 2, 3):
        raise BedienFehler("Stufe 1, 2 oder 3 angeben.")
    stop_setzen(ablage, max(stufe, stop_stufe(ablage)))
    return f"STOP-Datei K{max(stufe, stop_stufe(ablage))} gesetzt – wirksam im nächsten Takt (≤ 1 s)."


# ---------------------------------------------------------------------------------------------------- Betreiber: PIN, Entsperren
def nur_betreiber() -> None:
    """PIN-Befehle nur in einer interaktiven Konsole des Betreibers – nie in einer Agentensitzung, nie ohne Terminal."""
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        raise BedienFehler("Dieser Befehl ist dem Betreiber vorbehalten und läuft nie in einer Agentensitzung.")
    if not sys.stdin.isatty():
        raise BedienFehler("Nur interaktiv in der eigenen Konsole des Betreibers.")


def _pin_eingabe(text: str) -> str:
    nur_betreiber()
    return getpass.getpass(text)


def pin_setzen() -> str:
    umzug.pruefen()                                # sonst läge die PIN in der neuen Ablage und blockierte den Umzug
    frei = paths.kit_home() / "freigaben"
    alt = _pin_eingabe("Bisherige PIN: ") if pinmod.gesetzt(frei) else None
    neu = _pin_eingabe(f"Neue PIN (mind. {pinmod.MIN_LAENGE} Zeichen): ")
    if neu != _pin_eingabe("Neue PIN wiederholen: "):
        raise BedienFehler("Die Eingaben stimmen nicht überein.")
    pinmod.setzen(frei, neu, alt=alt)
    return "PIN gespeichert (nur als scrypt-Hash)."


def entsperren(modus: str, grund: str) -> str:
    """Nur Betreiber: PIN interaktiv prüfen, Bot darf nicht laufen (Schreibsperre), BOT_ENTSPERRT ins Journal, Zustand neu."""
    umzug.pruefen()                                # Sperren der alten Ablage erst übernehmen, dann aufheben
    pinmod.pruefen(paths.kit_home() / "freigaben", _pin_eingabe("PIN: "))
    ablage = _ablage(modus)
    with Schreibsperre(ablage):
        journal = Journal(ablage / "journal")
        saetze = journal.lesen()
        store = StateStore(ablage)
        try:
            zustand = store.laden(journal_vorhanden=bool(saetze))
        except ZustandFehler:
            zustand = {}
        aktiv = set(sp.aus_journal(saetze)) | set(zustand.get("sperren", []))
        aktiv |= {f"SYMBOL:{sym}" for sym in sp.symbol_sperren(saetze, _jetzt(saetze))}
        ziele = aktiv if grund == "ALLE" else ({grund} & aktiv)
        if grund not in ("ALLE", "ZUSTAND") and not ziele:
            raise BedienFehler(f"Sperre {grund} ist nicht aktiv (aktiv: {', '.join(sorted(aktiv)) or 'keine'}).")
        for g in sorted(ziele):                          # je Sperre ein Satz – nie ein Sammelsatz (Anker/Zählfenster bleiben)
            journal.schreiben("BOT_ENTSPERRT", g, f"Sperre {g} durch den Betreiber aufgehoben (PIN)")
        if grund == "ALLE" or ziele & {"K2", "K3"}:
            stop_setzen(ablage, 0)
        rest = sorted(g for g in aktiv - ziele if not g.startswith("SYMBOL:"))
        store.speichern({**zustand, "sperren": rest, "modus": modus})
    return f"Aufgehoben: {', '.join(sorted(ziele)) or '–'}; weiter aktiv: {', '.join(rest) or 'keine'}."


# ---------------------------------------------------------------------------------------------------- Status und Tor T
def status(modus: str) -> dict:
    ablage = _ablage(modus)
    saetze = journal_lesen(ablage / "journal", nur_lesen=True) if (ablage / "journal").exists() else []
    starts = [s for s in saetze if s["art"] == "START"]
    enden = [s for s in saetze if s["art"] == "ENDE"]
    try:
        zustand = json.loads((ablage / "zustand.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        zustand = {}
    return redigieren({"modus": modus, "saetze": len(saetze), "sperren": sorted(set(sp.aus_journal(saetze)) | set(zustand.get("sperren", []))),
                       "stop_datei": stop_stufe(ablage), "letzter_start": starts[-1]["t"] if starts else None,
                       "letztes_ende": (enden[-1]["code"], enden[-1]["t"]) if enden else None,
                       "laeuft_vermutlich": bool(starts) and (not enden or enden[-1]["seq"] < starts[-1]["seq"]),
                       "symbol_sperren": sp.symbol_sperren(saetze, _jetzt(saetze)),
                       "pin_gesetzt": pinmod.gesetzt(paths.kit_home() / "freigaben"),
                       "demokonten_registriert": len(live_guard.allowlist_laden(paths.kit_home() / "freigaben")),
                       "umzug_offen": umzug.offen_anzahl(),
                       "meldungen": _letzte_meldungen(ablage)})


def _jetzt(saetze: list[dict]) -> float:
    return max(saetze[-1]["t"] if saetze else 0.0, time.time())


def _letzte_meldungen(ablage: Path, n: int = 10) -> list[str]:
    try:
        return (ablage / "MELDUNGEN.txt").read_text(encoding="utf-8").splitlines()[-n:]
    except OSError:
        return []


def tor_t_stand(modus: str = "probe", *, wanduhr: bool = False) -> dict:
    """wanduhr: UNBEKANNT-Dauer bis jetzt messen statt bis zum letzten Journalsatz (Zertifikat)."""
    ablage = _ablage(modus)
    saetze = journal_lesen(ablage / "journal", nur_lesen=True) if (ablage / "journal").exists() else []
    t = tore()
    jetzt = _jetzt(saetze) if wanduhr else (saetze[-1]["t"] if saetze else dt.datetime.now(UTC).timestamp())
    return redigieren(auswerten(saetze, t["tor_t"], mechanik=mechanik_hash(), jetzt=jetzt))


def export(name: str, daten: object, *, markdown: str | None = None) -> Path:
    ordner = paths.kit_home() / "export"
    ordner.mkdir(parents=True, exist_ok=True)
    stempel = f"{dt.datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    pfad = ordner / f"{name}-{stempel}.json"
    pfad.write_text(json.dumps(redigieren(daten), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if markdown is not None:
        pfad.with_suffix(".md").write_text(markdown, encoding="utf-8")
    return pfad


def tor_t_bericht(modus: str = "probe", *, wanduhr: bool = False) -> tuple[dict, Path]:
    stand = tor_t_stand(modus, wanduhr=wanduhr)
    return stand, export(f"tor_t-{modus}", stand, markdown=tor_t_markdown(stand))


def tor_t_zertifikat(modus: str = "probe", *, repo: Path = ROOT) -> tuple[dict, Path, Path]:
    """Frischer redigierter Export, daraus bei BESTANDEN das Zertifikat berichte/tor_t/<datum>.json (nur auf sauberem Commit)."""
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        offen = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BedienFehler("git nicht verfügbar – kein Zertifikat.") from exc
    if offen:
        raise BedienFehler("Arbeitsbaum nicht sauber – das Zertifikat bindet einen Commit; erst committen.")
    pfade = [m.removesuffix("/**") for m in tore()["tor_t"]["mechanik"]]
    ignoriert = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--ignored", "--", *pfade], capture_output=True, text=True,
                               check=False).stdout.splitlines()
    if [z for z in ignoriert if "__pycache__" not in z]:
        raise BedienFehler("Im Geldpfad liegen Dateien außerhalb von git – der mechanik_hash wäre aus dem Commit nicht nachrechenbar.")
    stand, pfad = tor_t_bericht(modus, wanduhr=True)
    try:
        json_pfad, md_pfad = zertifikat.erstellen(pfad, datum=f"{dt.date.today():%Y-%m-%d}", commit=commit, modus=modus, root=repo)
    except zertifikat.ZertifikatFehler as exc:
        raise BedienFehler(str(exc)) from exc
    return stand, json_pfad, md_pfad


# ---------------------------------------------------------------------------------------------------- Installieren, Sichern
def installieren(tag: str, *, repo: Path = ROOT) -> Path:
    """Getaggten Stand nach <Ablage>\\app\\<tag> auspacken (unveränderlich) und Startdateien anlegen."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,60}", tag):
        raise BedienFehler("Ungültiger Tag-Name.")
    if not waechter_eingetragen(repo):
        raise BedienFehler("Agent-Wächter fehlt in .claude/settings.json des Repos – keine Installation.")
    luecke = waechter_luecke(repo)
    if luecke:
        raise BedienFehler(f"Agent-Wächter schützt die Laufzeitablage nicht ({luecke}) – erst docs/bot/waechter_patch.diff "
                           "einspielen (nur Betreiber), dann installieren.")
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"], capture_output=True,
                                text=True, check=True).stdout.strip()
        tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", tag, "kit", "config", "requirements"],
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BedienFehler(f"Tag {tag} nicht gefunden oder git nicht verfügbar.") from exc
    ziel = paths.kit_home() / "app" / tag.replace("/", "_")
    if ziel.exists():
        raise BedienFehler(f"{ziel.name} ist schon installiert (Installationen sind unveränderlich).")
    ziel.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as arch:
        arch.extractall(ziel, filter="data")
    python = Path(sys.executable)
    (ziel / "INSTALLATION.json").write_text(json.dumps({"tag": tag, "commit": commit, "mechanik_hash": mechanik_hash(ziel),
                                                        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
                                                        "installiert": dt.datetime.now(UTC).isoformat(timespec="seconds")},
                                                       indent=1), encoding="utf-8")
    for modus in SCHREIB_MODI:
        (ziel / f"start_{modus}.cmd").write_text(
            f'@echo off\r\ncd /d "%~dp0"\r\n"{python}" -B -E -s -m kit lauf --modus {modus} --schreiben %*\r\n', encoding="utf-8")
    (ziel / "stop.cmd").write_text(f'@echo off\r\ncd /d "%~dp0"\r\n"{python}" -B -E -s -m kit stop --beenden %*\r\n', encoding="utf-8")
    return ziel


def waechter_eingetragen(root: Path) -> bool:
    try:
        return "agent_waechter.py" in json.dumps(json.loads((Path(root) / ".claude" / "settings.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False


def waechter_luecke(root: Path) -> str | None:
    """Fragt den Wächter des Repos (als eigener Prozess, wie der Hook) nach Zugriffen auf die Laufzeitablage. Er muss jeden davon
    verweigern (Exit 2); sonst Kurzbeschreibung der Lücke. kit importiert tools/ nie."""
    heim = paths.kit_home()
    proben = (("Read", {"file_path": str(heim / "demo" / "zustand.json")}),
              ("Edit", {"file_path": str(heim / "freigaben" / "demo_konten.json"), "old_string": "a", "new_string": "b"}),
              ("Glob", {"path": str(heim), "pattern": "**/*.jsonl"}),
              ("Bash", {"command": f'type "{heim / "geheim" / "hmac.key"}"'}))
    waechter = Path(root) / "tools" / "agent_waechter.py"
    for werkzeug, eingabe in proben:
        ereignis = json.dumps({"tool_name": werkzeug, "tool_input": eingabe}).encode("utf-8")
        try:
            code = subprocess.run([sys.executable, "-B", "-I", str(waechter)], input=ereignis, capture_output=True, timeout=30,
                                  check=False).returncode
        except (OSError, subprocess.SubprocessError):
            return "Wächter nicht ausführbar"
        if code != 2:
            return f"{werkzeug} auf die Ablage erlaubt"
    return None


def _starts(ablage: Path) -> list[dict] | None:
    try:
        saetze = journal_lesen(ablage / "journal", nur_lesen=True) if (ablage / "journal").exists() else []
    except (OSError, ValueError, JournalFehler):
        return None
    return [s for s in saetze if s["art"] == "START"]


def _neuer_start(ablage: Path, vorher: set[int], ab: float, mechanik: str | None) -> bool:
    """START dieses Starts: neu seit dem Aufruf (seq), zeitlich danach (Toleranz 120 s Server- gegen PC-Uhr), Mechanik der
    Installation."""
    return any(s["seq"] not in vorher and s["t"] >= ab - 120 and s.get("daten", {}).get("mechanik_hash") == mechanik
               for s in _starts(ablage) or [])


def starten(tag: str, modus: str = "probe", *, dauer_min: float | None = None, popen=subprocess.Popen,
            warte=time.sleep, pruef_s: float = 5.0, start_frist_s: float = 150.0) -> int:
    """Installierte Kopie losgelöst im Benutzerkontext starten (kein Dienst, keine Aufgabenplanung). Vorher Integritätsprüfung:
    mechanik_hash der Installation = Wert bei der Installation. Ausgabe nach <ablage>/konsole.log. „Gestartet“ erst, wenn der
    Bot seinen START ins Journal geschrieben hat (Versatzmessung und Demo-Prüfung bestanden). Rückgabe: Prozess-ID."""
    if modus not in SCHREIB_MODI:
        raise BedienFehler(f"Modus {modus} ist nicht startbar.")
    umzug.pruefen()
    app = paths.kit_home() / "app" / tag.replace("/", "_")
    try:
        info = json.loads((app / "INSTALLATION.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BedienFehler(f"{tag} ist nicht installiert (kit installieren --tag {tag}).") from exc
    if mechanik_hash(app) != info.get("mechanik_hash"):
        raise BedienFehler("Installation verändert (mechanik_hash weicht ab) – nicht gestartet.")
    ablage = _ablage(modus)
    ablage.mkdir(parents=True, exist_ok=True)
    befehl = [sys.executable, "-B", "-E", "-s", "-m", "kit", "lauf", "--modus", modus, "--schreiben"]
    if dauer_min:
        befehl += ["--dauer-min", str(dauer_min)]
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    log_pfad = ablage / "konsole.log"
    beginn = log_pfad.stat().st_size if log_pfad.exists() else 0
    ab, vorher = time.time(), {s["seq"] for s in _starts(ablage) or []}
    with open(log_pfad, "ab") as log:
        proc = popen(befehl, cwd=app, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
    gewartet = 0.0
    while True:                                          # nicht „gestartet“ melden, solange kein START im Journal steht
        warte(pruef_s)
        gewartet += pruef_s
        if proc.poll() is not None:
            try:
                ende = log_pfad.read_bytes()[beginn:].decode("utf-8", errors="replace").splitlines()[-20:]
            except OSError:
                ende = []
            raise BedienFehler(f"Bot sofort beendet (Exit {proc.poll()}):\n  " + "\n  ".join(ende))
        if _neuer_start(ablage, vorher, ab, info.get("mechanik_hash")):
            return int(proc.pid)
        if gewartet >= start_frist_s:
            raise BedienFehler(f"Bot-Prozess {proc.pid} läuft, hat aber nach {gewartet:.0f} s noch keinen START geschrieben – "
                               f"kit status --modus {modus} prüfen, notfalls kit stop --beenden --modus {modus}.")


def sichern(ziel: Path, *, mit_schluessel: bool = False) -> Path:
    """Journale, Zustände, Freigaben und Exporte als ZIP (ohne app/ und Marktdaten; Schlüssel nur auf Wunsch)."""
    heim = paths.kit_home()
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    datei = ziel / f"kit-sicherung-{dt.datetime.now(UTC):%Y%m%dT%H%M%SZ}.zip"
    ordner = ["sim", "trocken", "probe", "demo", "freigaben", "export"] + (["geheim"] if mit_schluessel else [])
    with zipfile.ZipFile(datei, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in ordner:
            for p in sorted((heim / name).rglob("*")) if (heim / name).exists() else []:
                if p.is_file() and p.name != "LOCK" and (mit_schluessel or p.name not in ("pin.json", "pin_fehler.json")):
                    z.write(p, p.relative_to(heim).as_posix())
    return datei
