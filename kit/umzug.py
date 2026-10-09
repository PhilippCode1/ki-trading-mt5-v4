"""Umzug der Laufzeitdaten aus früheren Ablagen in die feste Ablage im Benutzerprofil – und das Startgate davor.

Frühere Ablagen: %LOCALAPPDATA%\\kit und die aus paketierten Apps umgeleiteten Kopien
%LOCALAPPDATA%\\Packages\\<App>\\LocalCache\\Local\\kit (je nach Prozess sieht man nur eine davon oder eine Zusammenführung).

- **Startgate** (`pruefen`): Solange eine frühere Ablage Altdaten hat, die nicht im Umzugsbuch stehen, starten weder Bot noch
  Terminalbefehle noch PIN/Entsperren. Sonst begänne die neue Ablage leer: dauerhafte Sperren, Anker, Zählfenster und PIN
  wären still weg. `kit stop` bleibt immer frei.
- **Umzugsbuch** `UMZUG.json` im Ziel: jede übernommene Altdatei als „Pfad relativ zur Quelle : SHA-256“. Auch Dateien, die nach
  einem Umzug neu entstehen oder wachsen, öffnen das Tor wieder.
- **Kopieren**: nur Nutzdaten, nie überschreiben, nichts löschen. Jede Datei geht über eine eigene Teil-Datei (exklusiv
  angelegt, fsync, SHA-256) und wird erst danach unter ihrem Namen angelegt – ein Abbruch hinterlässt nie eine halbe Datei
  unter dem Endnamen; der nächste Aufruf setzt fort.
- **Ziel schon belegt** (eigene Nutzdaten): dieser Teil wird nicht kopiert; für probe/demo werden die Sperren übernommen
  (BOT_SPERRE, nachzuholende Auslöser wie beim Botstart, Symbolsperren dauerhaft). Altjournal unlesbar → fail-closed K2.
- **Steuerdateien** (STOP, BEENDEN, LOCK, Protokolle) zählen nie als Nutzdaten. STOP wird nach der Max-Regel zusammengeführt
  (nie gesenkt, Drill-Dateien nicht), BEENDEN nie übernommen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path

from kit import paths
from kit.state import sperren as sp
from kit.state.journal import Journal, JournalFehler
from kit.state.journal import lesen as journal_lesen
from kit.state.store import SchreiberAktiv, Schreibsperre, stop_setzen, stop_stufe

UTC = dt.UTC
TEILE = ("probe", "demo", "freigaben", "geheim", "marktdaten", "export")
MODI = ("probe", "demo")
STEUERDATEIEN = frozenset({"STOP", "STOP.tmp", "BEENDEN", "LOCK", "konsole.log", "MELDUNGEN.txt"})
TEIL_ENDUNG = ".umzug-teil"
MARKE = "UMGEZOGEN.txt"                                 # nur Hinweis in der Quelle; maßgeblich ist das Umzugsbuch im Ziel
BUCH = "UMZUG.json"


class UmzugFehler(RuntimeError):
    """Umzug nicht möglich oder nicht nötig (klare Meldung an den Betreiber)."""


# ---------------------------------------------------------------------------------------------------- Bestand
def alte_ablagen() -> list[Path]:
    """Kandidaten für frühere Ablagen. Unter pytest nur die Ordner aus KIT_ALTE_ABLAGEN – nie die echten."""
    if paths._unter_pytest():                           # nur ein echter pytest-Lauf (Variable allein genügt nicht)
        return [Path(p) for p in os.environ.get("KIT_ALTE_ABLAGEN", "").split(os.pathsep) if p]
    basis = paths.lokale_anwendungsdaten()
    try:
        umgeleitet = sorted((basis / "Packages").glob("*/LocalCache/Local/kit"))
    except OSError:
        umgeleitet = []
    return [basis / "kit", *umgeleitet]


def _nutzdateien(ordner: Path) -> list[Path]:
    try:
        return sorted(p for p in ordner.rglob("*") if p.is_file() and p.name not in STEUERDATEIEN
                      and not p.name.endswith((TEIL_ENDUNG, ".tmp"))) if ordner.is_dir() else []
    except OSError:
        return []


def _drill(stop: Path) -> bool:
    try:
        return b"DRILL" in stop.read_bytes()
    except OSError:
        return False


def _stop_alt(ordner: Path) -> int:
    """STOP-Stufe einer alten Ablage; Drill-Dateien des Bots zählen nicht (keine dauerhafte Absicht)."""
    stop = ordner / "STOP"
    return 0 if not stop.exists() or _drill(stop) else stop_stufe(ordner)


def _altdaten(quelle: Path) -> list[Path]:
    """Was beim Neubeginn verloren ginge: Journale und Zustand je Modus, Freigaben, echte STOP-Dateien."""
    dateien = [p for t in (*MODI, "freigaben") for p in _nutzdateien(quelle / t)]
    return dateien + [quelle / m / "STOP" for m in MODI if _stop_alt(quelle / m)]


def _sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _eintrag(quelle: Path, p: Path) -> str:
    return f"{p.relative_to(quelle).as_posix()}:{_sha256(p)}"


def _buch_lesen(ziel: Path) -> dict:
    try:
        buch = json.loads((ziel / BUCH).read_text(encoding="utf-8"))
        return buch if isinstance(buch, dict) else {}
    except (OSError, ValueError):
        return {}


def _buch_schreiben(ziel: Path, buch: dict) -> None:
    tmp = ziel / (BUCH + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(buch, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ziel / BUCH)


def _alte_marke(quelle: Path, ziel: Path) -> float | None:
    """Umzug vor dem Umzugsbuch (F-03b): Marke in der Quelle, die genau dieses Ziel nennt → ihr Zeitstempel."""
    try:
        if f"nach {ziel} am " in (quelle / MARKE).read_text(encoding="utf-8"):
            return (quelle / MARKE).stat().st_mtime
    except OSError:
        pass
    return None


def _offen(quelle: Path, eintraege: set[str], ziel: Path) -> bool:
    try:
        marke = _alte_marke(quelle, ziel)
        for p in _altdaten(quelle):
            if marke is not None and p.stat().st_mtime < marke:
                continue                                 # vor der Marke dieses Ziels umgezogen (auch vor dem Buch)
            if _eintrag(quelle, p) not in eintraege:
                return True
    except OSError:
        return True                                      # unlesbar: fail-closed offen
    return False


def offene_altbestaende(kandidaten: list[Path] | None = None, ziel: Path | None = None) -> list[Path]:
    """Frühere Ablagen mit Altdaten, die nicht im Umzugsbuch stehen."""
    ziel = Path(ziel) if ziel else paths.kit_home()
    eintraege = set(_buch_lesen(ziel).get("buch", []))
    offen: list[Path] = []
    gesehen: set[Path] = set()
    for k in alte_ablagen() if kandidaten is None else kandidaten:
        try:
            echt = k.resolve()
        except OSError:
            continue
        if echt in gesehen or not k.is_dir():
            continue
        gesehen.add(echt)
        if _offen(k, eintraege, ziel):
            offen.append(k)
    return offen


def offen_anzahl() -> int:
    return len(offene_altbestaende()) + (_buch_lesen(paths.kit_home()).get("status") == "laeuft")


def pruefen() -> None:
    """Startgate (siehe Modulkopf). Wirft paths.AblageFehler mit Anleitung."""
    offen = offene_altbestaende()
    if offen:
        raise paths.AblageFehler(f"Altbestand in {offen[0]} ist noch nicht umgezogen – erst `kit umziehen` ausführen (kopiert, "
                                 "löscht nichts). Sonst gingen dauerhafte Sperren, Anker und PIN verloren.")
    if _buch_lesen(paths.kit_home()).get("status") == "laeuft":
        raise paths.AblageFehler("Ein Umzug wurde abgebrochen – `kit umziehen` erneut ausführen (setzt fort, überschreibt nichts); "
                                 "ist die alte Ablage nicht mehr erreichbar: `kit umziehen --abschliessen`.")


# ---------------------------------------------------------------------------------------------------- Kopieren
def _anlegen(teil: Path, kopie: Path) -> None:
    """Teil-Datei unter dem Endnamen anlegen, nie überschreiben (Windows: rename scheitert am vorhandenen Ziel)."""
    if os.name == "nt":
        os.rename(teil, kopie)
    else:
        os.link(teil, kopie)
        teil.unlink()


def _teil_kopieren(quelle: Path, ziel: Path) -> int:
    n = 0
    for p in _nutzdateien(quelle):
        rel = p.relative_to(quelle)
        kopie = ziel / rel
        soll = _sha256(p)
        if kopie.exists():
            if _sha256(kopie) != soll:
                raise UmzugFehler(f"Ziel enthält schon eine abweichende {quelle.name}/{rel.as_posix()} – nichts überschrieben. "
                                  "Hat sich die alte Ablage seit dem Abbruch geändert? Datei prüfen (Betreiber).")
            n += 1
            continue                                     # Fortsetzen: schon vollständig übernommen
        kopie.parent.mkdir(parents=True, exist_ok=True)
        teil = kopie.with_name(kopie.name + TEIL_ENDUNG)
        teil.unlink(missing_ok=True)                     # eigener Rest eines abgebrochenen Laufs
        with open(p, "rb") as src, open(teil, "xb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
            dst.flush()
            os.fsync(dst.fileno())
        if _sha256(teil) != soll:
            raise UmzugFehler(f"Kopie weicht ab: {quelle.name}/{rel.as_posix()} – erneut ausführen.")
        try:
            _anlegen(teil, kopie)
        except FileExistsError as exc:
            raise UmzugFehler(f"{quelle.name}/{rel.as_posix()} entstand während des Umzugs im Ziel – nichts überschrieben.") from exc
        n += 1
    return n


# ---------------------------------------------------------------------------------------------------- Sperren
def _nachholen(saetze: list[dict]) -> dict[str, dict]:
    """Auslöser ohne Sperrsatz – dieselbe Regel wie Bot.starten (Absturz zwischen Auslöser und Sperre). Grund → Auslösesatz."""
    from kit.run.loop import VORFALL_NULLTOLERANZ
    letzte: dict[str, dict] = {}
    for s in saetze:
        art, code = s["art"], s["code"]
        if art == "DEAL" and code == "STOP_OUT":
            letzte["STOP_OUT"] = s
        elif (art == "ABGLEICH" and code == "DIFFERENZ") or (art == "VORFALL" and code in VORFALL_NULLTOLERANZ):
            letzte["NULLTOLERANZ"] = s
    return {g: s for g, s in letzte.items() if s["seq"] > sp.letzte_entsperrung(saetze, g)}


def _journal(quelle: Path, modus: str) -> list[dict] | None:
    """Altjournal eines Modus; None = unlesbar (gebrochene Kette, abgerissene Zeile, Lesefehler)."""
    try:
        return journal_lesen(quelle / modus / "journal", nur_lesen=True) if (quelle / modus / "journal").exists() else []
    except (JournalFehler, ValueError, OSError):
        return None


def _sperren_uebernehmen(quelle: Path, ziel: Path, modus: str, ab_seq: int, ab_t: float) -> list[str]:
    """Teil `modus` wurde nicht kopiert (Ziel hat ein eigenes Journal): Sperren der alten Ablage ins Ziel-Journal schreiben –
    nur was seit der letzten Übernahme aus dieser Quelle entstand (seq > ab_seq, Zeit > ab_t), damit vom Betreiber schon
    aufgehobene Sperren nicht zurückkommen. Aufheben weiter nur mit PIN. Unlesbares Altjournal → fail-closed NULLTOLERANZ + K2."""
    alt = _journal(quelle, modus)
    if alt is None:
        gruende, symbole = ["NULLTOLERANZ"], {}
    else:
        def neu(s: dict) -> bool:
            return s["seq"] > ab_seq and s["t"] > ab_t
        aktiv = sp.aus_journal(alt)
        menge = {g for g, v in aktiv.items() if neu(v)} | {g for g, s in _nachholen(alt).items() if neu(s)}
        if not ab_seq and not ab_t:                      # erste Übernahme: auch Sperren, die nur im Zustand stehen
            try:
                zustand = json.loads((quelle / modus / "zustand.json").read_text(encoding="utf-8")).get("sperren", [])
                menge |= {g for g in zustand if isinstance(g, str)}
            except (OSError, ValueError, AttributeError):
                pass
        gesetzt = {s["daten"].get("symbol"): s for s in alt if s.get("art") == "SPERRE"}
        symbole = {sym: grund for sym, grund in sp.symbol_sperren(alt, dt.datetime.now(UTC).timestamp()).items()
                   if sym in gesetzt and neu(gesetzt[sym])}
        gruende = sorted(menge)
    if not (gruende or symbole):
        return []
    uebernommen: list[str] = []
    (ziel / modus).mkdir(parents=True, exist_ok=True)
    with Schreibsperre(ziel / modus):
        journal = Journal(ziel / modus / "journal")
        saetze = journal.lesen()
        schon = set(sp.aus_journal(saetze))
        dauerhaft = sp.symbol_sperren(saetze, float("inf"))     # laufende Zeitsperren zählen hier nicht
        for g in gruende:
            if g not in schon:
                text = "Altjournal unlesbar (Umzug) – Bestand prüfen" if alt is None else "aus der alten Ablage übernommen (Umzug)"
                journal.schreiben("BOT_SPERRE", g, f"Sperre {g}: {text}", stufe=sp.stufe([g]))
                uebernommen.append(g)
        for sym, grund in sorted(symbole.items()):      # immer dauerhaft – auch laufende Zeitsperren (fail-closed)
            if sym not in dauerhaft:
                journal.schreiben("SPERRE", "UMZUG", f"Einstiege in {sym} gesperrt: {grund} (aus der alten Ablage übernommen)",
                                  symbol=sym, grund=f"UMZUG {grund}")
                uebernommen.append(f"SYMBOL:{sym}")
        if alt is None and stop_stufe(ziel / modus) < 2:
            stop_setzen(ziel / modus, 2)
            uebernommen.append("STOP-K2")
    return uebernommen


def _stop_zusammenfuehren(quelle: Path, ziel: Path, modus: str, eintraege: set[str], ab_t: float) -> str | None:
    """Echte STOP-Datei der alten Ablage nach der Max-Regel übernehmen – nur einmal je Inhalt (Umzugsbuch) und nur, wenn sie
    nach einer früheren Übernahme entstand; ein vom Betreiber danach entfernter STOP kommt nicht zurück."""
    stop = quelle / modus / "STOP"
    alt = _stop_alt(quelle / modus)
    try:
        if not alt or _eintrag(quelle, stop) in eintraege or stop.stat().st_mtime < ab_t:
            return None
    except OSError:
        return None
    if alt > stop_stufe(ziel / modus):
        (ziel / modus).mkdir(parents=True, exist_ok=True)
        stop_setzen(ziel / modus, alt)
        return f"STOP-K{alt}"
    return None


# ---------------------------------------------------------------------------------------------------- Umziehen
def umziehen(quelle: Path | None = None, ziel: Path | None = None) -> dict:
    """Siehe Modulkopf. Nicht bei laufendem Bot (weder alt noch neu)."""
    ziel = Path(ziel or paths.kit_home())
    offen = offene_altbestaende(ziel=ziel)
    if quelle is None:
        if not offen:
            raise UmzugFehler("Kein offener Altbestand gefunden – nichts umzuziehen.")
        if len(offen) > 1:
            raise UmzugFehler("Mehrere Altbestände: " + "; ".join(map(str, offen)) + " – mit --von <Pfad> einzeln umziehen.")
        quelle = offen[0]
    quelle = Path(quelle)
    if quelle.resolve() == ziel.resolve():
        raise UmzugFehler("Quelle und Ziel sind gleich – nichts umzuziehen.")
    if not offene_altbestaende([quelle], ziel=ziel):
        raise UmzugFehler(f"In {quelle} liegt nichts (mehr) umzuziehen – alle Altdaten stehen im Umzugsbuch oder es gibt keine.")
    ziel.mkdir(parents=True, exist_ok=True)
    try:
        with Schreibsperre(quelle / "schreiber"), Schreibsperre(quelle / "probe"), Schreibsperre(quelle / "demo"), \
                Schreibsperre(ziel / "schreiber"):
            buch = _buch_lesen(ziel)
            fortsetzen = buch.get("status") == "laeuft"
            if fortsetzen and buch.get("von") != str(quelle):
                raise UmzugFehler(f"Abgebrochener Umzug aus {buch.get('von')} – erst diesen fortsetzen (--von) oder, falls nicht "
                                  "mehr erreichbar, kit umziehen --abschliessen.")
            vorhanden = [t for t in TEILE if _nutzdateien(quelle / t)]
            belegt = sorted(buch.get("belegt", [])) if fortsetzen else sorted(t for t in vorhanden if _nutzdateien(ziel / t))
            eintraege = set(buch.get("buch", []))
            _buch_schreiben(ziel, {**buch, "status": "laeuft", "von": str(quelle), "belegt": belegt, "buch": sorted(eintraege)})
            kopiert = {t: _teil_kopieren(quelle / t, ziel / t) for t in vorhanden if t not in belegt}
            sperren: dict[str, list[str]] = {}
            stand = dict(buch.get("stand", {}))          # je Quelle und Modus: bis zu welcher seq schon übernommen
            marke_t = _alte_marke(quelle, ziel) or 0.0
            for m in MODI:
                schluessel = f"{quelle}|{m}"
                liste = _sperren_uebernehmen(quelle, ziel, m, int(stand.get(schluessel, 0)), marke_t) if m in belegt else []
                stop = _stop_zusammenfuehren(quelle, ziel, m, eintraege, marke_t)
                if liste or stop:
                    sperren[m] = liste + ([stop] if stop else [])
                alt = _journal(quelle, m)
                if alt:
                    stand[schluessel] = max(int(stand.get(schluessel, 0)), alt[-1]["seq"])
            eintraege |= {_eintrag(quelle, p) for p in _altdaten(quelle)}
            _buch_schreiben(ziel, {"status": "fertig", "von": str(quelle), "belegt": belegt, "buch": sorted(eintraege),
                                   "stand": stand, "zeit": dt.datetime.now(UTC).isoformat(timespec="seconds")})
    except SchreiberAktiv as exc:
        raise UmzugFehler("In der alten oder neuen Ablage läuft noch ein Bot – erst beenden: einen Bot der neuen Ablage mit "
                          "kit stop --beenden, einen Bot der alten Ablage mit stop.cmd seiner eigenen Installation.") from exc
    except (JournalFehler, OSError) as exc:
        raise UmzugFehler(f"Umzug unterbrochen ({type(exc).__name__}: {exc}) – erneut ausführen, er setzt fort.") from exc
    try:
        (quelle / MARKE).write_text(f"Umgezogen nach {ziel} am {dt.datetime.now(UTC):%Y-%m-%d %H:%M} UTC. Nichts gelöscht."
                                    + (f" Nicht kopiert (Ziel hatte eigene Daten): {', '.join(belegt)}." if belegt else "") + "\n",
                                    encoding="utf-8")
    except OSError:
        pass                                             # nur Hinweis; maßgeblich ist das Umzugsbuch
    return {"von": str(quelle), "nach": str(ziel), "dateien": kopiert, "nicht_kopiert": belegt, "sperren_uebernommen": sperren}


def wiederherstellen(zip_pfad: Path, ziel: Path | None = None) -> dict:
    """Sicherung aus `kit sichern` (ZIP) in die Ablage übernehmen – z. B. beim Umzug auf einen neuen Rechner. Die ZIP wird
    geprüft (nur bekannte Teile, keine absoluten oder ..-Pfade) und nach <Ablage>\\wiederherstellung\\<Zeit> entpackt; danach
    gelten dieselben Regeln wie bei `umziehen`: nie überschreiben, Teile mit eigenen Daten nicht kopieren, Sperren übernehmen.
    Ohne Schlüssel (geheim/) passt die Demo-Allowlist nicht mehr: dann `kit konto-registrieren` erneut (fail-closed)."""
    import zipfile
    ziel = Path(ziel or paths.kit_home())
    zip_pfad = Path(zip_pfad)
    erlaubt = {*TEILE, "sim", "trocken"}
    try:
        with zipfile.ZipFile(zip_pfad) as z:
            namen = z.namelist()
            for n in namen:
                teile = Path(n).parts
                if n.startswith(("/", "\\")) or ":" in n or ".." in teile or not teile or teile[0] not in erlaubt:
                    raise UmzugFehler(f"Unzulässiger Eintrag in der Sicherung: {n!r} – nichts übernommen.")
            entpackt = ziel / "wiederherstellung" / dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            entpackt.mkdir(parents=True)
            z.extractall(entpackt)
    except (OSError, zipfile.BadZipFile) as exc:
        raise UmzugFehler(f"Sicherung nicht lesbar: {exc}") from exc
    erg = umziehen(entpackt, ziel)
    return {**erg, "sicherung": zip_pfad.name, "eintraege": len(namen),
            "hinweis": "" if any(n.startswith("geheim/") for n in namen) else
            "ohne Schlüssel gesichert: Demokonto mit kit konto-registrieren neu eintragen"}


def abschliessen(ziel: Path | None = None) -> dict:
    """Abgebrochener Umzug, dessen Quelle nicht mehr erreichbar ist: fail-closed abschließen. Jeder Modus bekommt K2
    (BOT_SPERRE + STOP) – auch einer, der noch gar nicht kopiert war; aufheben nur der Betreiber mit PIN nach Prüfung."""
    ziel = Path(ziel or paths.kit_home())
    buch = _buch_lesen(ziel)
    if buch.get("status") != "laeuft":
        raise UmzugFehler("Kein abgebrochener Umzug – nichts abzuschließen.")
    gesperrt: list[str] = []
    try:
        with Schreibsperre(ziel / "schreiber"):
            for m in MODI:
                (ziel / m).mkdir(parents=True, exist_ok=True)
                with Schreibsperre(ziel / m):
                    journal = Journal(ziel / m / "journal")
                    if "K2" not in sp.aus_journal(journal.lesen()):
                        journal.schreiben("BOT_SPERRE", "K2", "Sperre K2: Umzug unvollständig abgeschlossen – Bestand prüfen",
                                          stufe=2)
                    stop_setzen(ziel / m, max(2, stop_stufe(ziel / m)))
                gesperrt.append(m)
            _buch_schreiben(ziel, {**buch, "status": "fertig", "unvollstaendig": True,
                                   "zeit": dt.datetime.now(UTC).isoformat(timespec="seconds")})
    except SchreiberAktiv as exc:
        raise UmzugFehler("In der neuen Ablage läuft ein Bot – erst beenden (kit stop --beenden).") from exc
    return {"abgeschlossen": True, "k2_gesetzt": gesperrt}
