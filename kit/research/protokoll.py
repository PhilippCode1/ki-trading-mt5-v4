"""Versuchsprotokoll der Forschungsrunden (F-04, F-05): `forschung/versuchsprotokoll.jsonl`, nur anhängen, Hashkette im Format von
kit.research.trials. Jede Runde hat eigene Vorregistrierung (PREREG-SHA), Familien, Werkzeugfamilie und Code-Liste (`runde`);
die Einträge früherer Runden bleiben unverändert und werden weiter gegen ihre eigene Vorregistrierung geprüft.

Format: je Zeile ein Eintrag {"seq", "prev", "body", "hash"} als json.dumps(eintrag, ensure_ascii=False, sort_keys=True);
hash = trials.entry_hash(prev, body), prev des ersten Eintrags = trials.GENESIS. Bestehende Zeilen werden nie neu geschrieben.
Regel: Einträge nur über die kit-CLI anhängen (der Agent-Wächter sperrt Write/Edit dieser Datei).

Ablauf: `vorab` trägt die Vorregistrierung (PREREG-SHA, Commit, Code-Hashes, mechanik_hash) je Familie VOR der ersten Datensicht ein
(nach einer Code-Korrektur vor der Sicht signiert ein erneutes `vorab` neu; nach der Sicht verweigert es); `vorpruefung` stellt vor
jeder Datensicht und Auswertung fail-closed sicher, dass Code, Mechanik und Arbeitsbaum genau dem Signierten entsprechen; danach
`datensicht`/`versuch`; Werkzeugänderungen nach der Sicht nur mit `aenderung_nach_sicht` (Werkzeugfamilie der Runde, z. B.
F04-WERKZEUG, committete Dateien; sie erlaubt neue Hashes nur in ihrer eigenen Runde). `pruefen` liefert alle Befunde der
Konsistenz (leer = verifiziert), `vollstaendigkeit` die fehlenden Pflichteinträge.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

from kit.research import trials

ROOT = Path(__file__).resolve().parents[2]
PFAD = ROOT / "forschung" / "versuchsprotokoll.jsonl"
PREREG_REL = "docs/bot/prereg/F04_ENTWURF.md"
PREREG_PFAD = ROOT / PREREG_REL
PREREG_SHA = "621351dc9f16916806f19423a3067391350dd013bcb7f983216826c504c9250a"
FAMILIEN = ("F04-ZIEL-STOP", "F04-REFERENZ", "F04-DATEN")
WERKZEUG = "F04-WERKZEUG"
SCHWELLEN_REL = "config/tore.toml"
TRADE_TEST_REL = "config/trade_test.toml"
CODE_F04 = (
    "kit/backtest/__init__.py", "kit/backtest/kosten.py", "kit/backtest/terminal.py", "kit/backtest/runner.py",
    "kit/backtest/ausstieg.py", "kit/backtest/paritaet.py", "kit/gates/trade_test.py", "config/trade_test.toml",
    "kit/strategy/base.py", "kit/strategy/rev.py", "kit/strategy/donchian_ref.py", "kit/strategy/varianten.py",
    "kit/research/stats.py", "kit/research/trials.py", "kit/research/protokoll.py", "kit/research/entwicklung.py",
    "kit/research/daten.py", "config/tore.toml", "config/kit_demo.toml", "config/kostenprofil/f04_startwerte.json", "kit/cli.py",
    "kit/__init__.py", "kit/config.py", "kit/paths.py", "kit/gates/__init__.py", "kit/gates/tor_t.py", "kit/research/__init__.py",
    "kit/strategy/__init__.py",
)
LAUF = "F-04"

# Runde 2 (F-05): KI-Meta-Filter, Vorregistrierung docs/bot/prereg/F05_ENTWURF.md (PREREG-OK des Betreibers im Laufprompt F-05).
PREREG_F05_REL = "docs/bot/prereg/F05_ENTWURF.md"
PREREG_F05_SHA = "88bdd6cc9398320b2e9619544f35c81caa82dfd344df78a55bc8ae1e0d983ffb"
FAMILIEN_F05 = ("F05-META", "F05-DATEN")
WERKZEUG_F05 = "F05-WERKZEUG"
CODE_F05 = (
    "kit/backtest/__init__.py", "kit/backtest/kosten.py", "kit/backtest/terminal.py", "kit/backtest/runner.py",
    "kit/backtest/ausstieg.py", "kit/backtest/paritaet.py", "kit/gates/trade_test.py", "config/trade_test.toml",
    "kit/strategy/base.py", "kit/strategy/rev.py", "kit/strategy/donchian_ref.py", "kit/strategy/varianten.py",
    "kit/strategy/meta_filter.py", "kit/research/meta.py",
    "kit/research/stats.py", "kit/research/trials.py", "kit/research/protokoll.py", "kit/research/entwicklung.py",
    "kit/research/daten.py", "config/tore.toml", "config/kit_demo.toml", "config/kostenprofil/f04_startwerte.json", "kit/cli.py",
    "kit/__init__.py", "kit/config.py", "kit/paths.py", "kit/gates/__init__.py", "kit/gates/tor_t.py", "kit/research/__init__.py",
    "kit/strategy/__init__.py", "forschung/__init__.py", "forschung/meta_training.py", "forschung/runde2.py",
    "requirements/forschung.in", "requirements/forschung.lock.txt",
)
# Runde 3 (F-05b): Richtungsmodell, Vorregistrierung docs/bot/prereg/F05B_ENTWURF.md (PREREG-OK im Laufprompt F-05b).
PREREG_F05B_REL = "docs/bot/prereg/F05B_ENTWURF.md"
PREREG_F05B_SHA = "b1ec2a2ee252f51de86963057ef553e4727e7b10bf96828c30a56498acbd08e9"
FAMILIEN_F05B = ("F05B-RICHTUNG", "F05B-DATEN")
WERKZEUG_F05B = "F05B-WERKZEUG"
CODE_F05B = (*CODE_F05, "kit/strategy/richtung.py", "kit/research/richtung.py", "forschung/richtung_training.py", "forschung/runde3.py")
WERKZEUG_FAMILIEN = (WERKZEUG, WERKZEUG_F05, WERKZEUG_F05B)
ALLE_FAMILIEN = (*FAMILIEN, *FAMILIEN_F05, *FAMILIEN_F05B)


def runde(lauf: str) -> dict:
    """Vorregistrierung, Familien, Werkzeugfamilie und Code-Liste eines Laufs. F-05 hat eigene Werte; jeder andere Lauf (F-04 und
    Testläufe) nutzt die F-04-Werte (zur Laufzeit gelesen, damit Tests sie ersetzen können)."""
    if lauf == "F-05":
        return {"lauf": lauf, "prereg_rel": PREREG_F05_REL, "prereg_sha": PREREG_F05_SHA, "familien": FAMILIEN_F05,
                "werkzeug": WERKZEUG_F05, "code": CODE_F05}
    if lauf == "F-05b":
        return {"lauf": lauf, "prereg_rel": PREREG_F05B_REL, "prereg_sha": PREREG_F05B_SHA, "familien": FAMILIEN_F05B,
                "werkzeug": WERKZEUG_F05B, "code": CODE_F05B}
    return {"lauf": lauf, "prereg_rel": PREREG_REL, "prereg_sha": PREREG_SHA, "familien": FAMILIEN, "werkzeug": WERKZEUG,
            "code": CODE_F04}
PROTOKOLL_REL = "forschung/versuchsprotokoll.jsonl"
_COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


class ProtokollFehler(RuntimeError):
    """Protokoll nicht lesbar, Kette gebrochen oder Vorbedingung verletzt (fail-closed)."""


# ---------------------------------------------------------------- Hashes
def sha256_datei(pfad: Path | str) -> str:
    try:
        return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()
    except OSError as exc:
        raise ProtokollFehler(f"Datei nicht lesbar: {Path(pfad).name} ({exc.__class__.__name__})") from exc


def _rel_ok(rel: str) -> str:
    p = PurePosixPath(rel)
    if not rel or "\\" in rel or p.is_absolute() or ".." in p.parts or ":" in rel:
        raise ProtokollFehler(f"kein Repo-relativer Pfad: {rel!r}")
    return rel


def code_hashes(dateien: Iterable[str] = CODE_F04, root: Path = ROOT) -> dict[str, str]:
    """SHA-256 je Repo-relativer Datei; eine fehlende Datei ist ein Fehler (fail-closed)."""
    out: dict[str, str] = {}
    for rel in dateien:
        pfad = Path(root) / _rel_ok(rel)
        if not pfad.is_file():
            raise ProtokollFehler(f"Datei fehlt: {rel}")
        out[rel] = sha256_datei(pfad)
    return out


KOSTEN_AUSLEGUNG = ("Prereg §1 Kosten laut Laufprompt F-04: Hauptprofil = Kommission laut erstem Demo-Trade (0 je Lot und Seite), "
                    "Gegenprobe Startwert cost_truth 3,25; Spread je Kerze aus den Daten; Swap aus den Startwerten (Rauchtest ohne Swap); "
                    "Kosten × 1,5 auf das Hauptprofil (Spread, Swap-Belastungen); die Größe rechnet der Takt mit kit_demo.toml (3,25).")


def mechanik_dateien(root: Path = ROOT) -> list[str]:
    """Repo-relative Pfade der Mechanik (tore.toml [tor_t].mechanik) – sie bestimmen das Ergebnis mit, liegen aber nicht in CODE_F04."""
    from kit.gates import tor_t, tore
    return [p.relative_to(root).as_posix() for p in tor_t.mechanik_dateien(list(tore()["tor_t"]["mechanik"]), Path(root))]


def _mechanik_hash(root: Path) -> str:
    from kit.gates import tor_t
    return tor_t.mechanik_hash(Path(root))


# ---------------------------------------------------------------- git (nur lesend)
def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    umgebung = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}   # kein fremdes GIT_DIR/GIT_INDEX_FILE
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], capture_output=True, check=False,
                              timeout=60, env=umgebung)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProtokollFehler(f"git nicht aufrufbar ({exc.__class__.__name__})") from exc


def git_kopf(root: Path = ROOT) -> str:
    erg = _git(root, "rev-parse", "HEAD")
    kopf = erg.stdout.decode("ascii", "replace").strip()
    if erg.returncode != 0 or not _COMMIT.fullmatch(kopf):
        raise ProtokollFehler("HEAD nicht bestimmbar")
    return kopf


def git_sauber(root: Path, dateien: Iterable[str]) -> bool:
    """True, wenn keine der Dateien geändert, unversioniert oder ignoriert ist (git status leer)."""
    dateien = [_rel_ok(d) for d in dateien]
    if not dateien:
        return False
    erg = _git(root, "status", "--porcelain", "--untracked-files=all", "--ignored", "--", *dateien)
    return erg.returncode == 0 and not erg.stdout.strip()


def datei_im_commit_sha(root: Path, commit: str, rel: str) -> str | None:
    """SHA-256 der Datei `rel`, wie sie im Commit liegt (Bytes von git show); None, wenn nicht vorhanden."""
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        return None
    erg = _git(root, "show", f"{commit}:{_rel_ok(rel)}")
    return hashlib.sha256(erg.stdout).hexdigest() if erg.returncode == 0 else None


def ist_vorfahr(root: Path, commit: str) -> bool:
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        return False
    return _git(root, "merge-base", "--is-ancestor", commit, "HEAD").returncode == 0


# ---------------------------------------------------------------- Lesen und Anhängen
def lesen(pfad: Path = PFAD) -> list[dict]:
    """Alle Einträge; fehlt die Datei, ist das Protokoll leer. Leere Zeilen werden übergangen."""
    pfad = Path(pfad)
    if not pfad.exists():
        return []
    try:
        text = pfad.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProtokollFehler(f"Protokoll nicht lesbar ({exc.__class__.__name__})") from exc
    log: list[dict] = []
    for nr, zeile in enumerate(text.split("\n"), 1):          # nicht splitlines: U+2028 u. ä. dürfen in Strings stehen
        if not zeile.strip():
            continue
        try:
            eintrag = json.loads(zeile)
        except ValueError as exc:
            raise ProtokollFehler(f"Zeile {nr}: kein gültiges JSON") from exc
        if not isinstance(eintrag, dict) or not isinstance(eintrag.get("body"), dict):
            raise ProtokollFehler(f"Zeile {nr}: kein Eintrag mit body")
        log.append(eintrag)
    return log


def _kette_heil(log: list[dict]) -> None:
    kaputt = [b for b in trials.verify(log) if b.startswith("CHAIN")]
    if kaputt:
        raise ProtokollFehler(f"Hashkette gebrochen: {', '.join(kaputt)}")


def anhaengen(body: Mapping, pfad: Path = PFAD) -> dict:
    """Prüft die Kette, erzeugt den Eintrag (Pflichtfelder fail-closed) und hängt genau eine Zeile an."""
    pfad = Path(pfad)
    log = lesen(pfad)
    _kette_heil(log)
    try:
        eintrag = trials.append(log, body)
        zeile = json.dumps(eintrag, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ProtokollFehler(f"Eintrag abgewiesen: {exc}") from exc
    if trials.entry_hash(eintrag["prev"], json.loads(zeile)["body"]) != eintrag["hash"]:
        raise ProtokollFehler("Eintrag nicht verlustfrei als JSON darstellbar")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if pfad.exists() and pfad.stat().st_size:
        with pfad.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                raise ProtokollFehler("Protokoll endet ohne Zeilenumbruch (von Hand bearbeitet?)")
    with pfad.open("a", encoding="utf-8", newline="\n") as f:
        f.write(zeile + "\n")
        f.flush()
        os.fsync(f.fileno())
    return eintrag


# ---------------------------------------------------------------- Einträge
def vorab(lauf: str, prereg_ok: str, datum: str, *, root: Path = ROOT, pfad: Path = PFAD,
          dateien: Iterable[str] | None = None) -> list[dict]:
    """Vorregistrierung je Familie des Laufs VOR der ersten Datensicht (PREREG_SIGNED mit Commit und Code-Hashes).

    Idempotent: sind alle Familien dieses Laufs schon eingetragen, werden die vorhandenen Einträge zurückgegeben.
    Fail-closed: PREREG-Datei ≠ PREREG-SHA des Laufs, Datei fehlt oder ist nicht committet, Datensicht/Versuch einer Familie schon im Log.
    """
    r = runde(lauf if isinstance(lauf, str) else "")
    familien, prereg_rel, prereg_sha = r["familien"], r["prereg_rel"], r["prereg_sha"]
    root, dateien = Path(root), list(r["code"] if dateien is None else dateien)
    if not all(isinstance(x, str) and x.strip() for x in (lauf, prereg_ok)):
        raise ProtokollFehler("Lauf und Freigabebezug (prereg_ok) nötig")
    if lauf in ("F-05", "F-05b") and not (re.search(r"(?i)\bja\b", prereg_ok) and prereg_sha[:12] in prereg_ok):
        raise ProtokollFehler(f"PREREG-OK für {lauf} braucht „ja“ und den SHA-256 der Vorregistrierung (Freigabezeile aus dem Laufprompt)")
    log = lesen(pfad)
    _kette_heil(log)
    prereg_datei = root / prereg_rel
    if not prereg_datei.is_file() or sha256_datei(prereg_datei) != prereg_sha:
        raise ProtokollFehler(f"{prereg_rel} weicht von PREREG_SHA ab oder fehlt")
    vorhanden = {e["body"]["family"]: e for e in log if e["body"].get("kind") == "PREREG_SIGNED"
                 and e["body"].get("lauf") == lauf and e["body"].get("family") in familien}      # je Familie der letzte
    gesehen = sorted({e["body"]["family"] for e in log if e["body"].get("kind") in ("DATA_VIEW", "TRIAL")
                      and e["body"].get("family") in familien})
    alle = [*dateien, prereg_rel, SCHWELLEN_REL, TRADE_TEST_REL, *mechanik_dateien(root)]
    code = code_hashes(dateien, root)
    schwellen = code_hashes([SCHWELLEN_REL, TRADE_TEST_REL], root)
    mechanik = _mechanik_hash(root)
    if all(f in vorhanden for f in familien):
        gleich = all(vorhanden[f]["body"].get("code") == code and vorhanden[f]["body"].get("mechanik_hash") == mechanik
                     for f in familien)
        if gleich:
            return [vorhanden[f] for f in familien]
        if gesehen:
            raise ProtokollFehler("Code oder Mechanik nach der Datensicht geändert – nur noch aenderung_nach_sicht (neuer Werkzeugstand)")
        vorhanden = {}                                      # vor der Sicht: alle Familien neu signieren (der letzte Eintrag gilt)
    if gesehen:
        raise ProtokollFehler(f"Datensicht vor der Vorregistrierung: {', '.join(gesehen)} – Vorregistrierung nicht mehr möglich")
    if not git_sauber(root, alle):
        raise ProtokollFehler("Code, Mechanik oder Vorregistrierung nicht committet (git status nicht leer)")
    commit = git_kopf(root)
    neu = {}
    for familie in familien:
        if familie in vorhanden:
            continue
        neu[familie] = anhaengen({"kind": "PREREG_SIGNED", "actor": "CODING_AGENT", "date": datum, "family": familie, "lauf": lauf,
                                  "prereg_pfad": prereg_rel, "prereg_sha": prereg_sha, "prereg_ok": prereg_ok, "commit": commit,
                                  "code": code, "schwellen_sha": schwellen[SCHWELLEN_REL], "trade_test_sha": schwellen[TRADE_TEST_REL],
                                  "mechanik_hash": mechanik, "kosten_auslegung": KOSTEN_AUSLEGUNG,
                                  "hinweis": "Code-Hashes vor der ersten Datensicht"}, pfad)
    return [vorhanden.get(f) or neu[f] for f in familien]


_KERN = ("kind", "actor", "date", "family", "variant_id", "split")


def _body(kind: str, familie: str, variante: str, split: str, datum: str, weitere: Mapping) -> dict:
    doppelt = sorted(set(weitere) & set(_KERN))
    if doppelt:
        raise ProtokollFehler(f"reservierte Felder: {', '.join(doppelt)}")
    return {"kind": kind, "actor": "CODING_AGENT", "date": datum, "family": familie, "variant_id": variante, "split": split,
            **weitere}


def datensicht(familie: str, variante: str, split: str, datum: str, daten: dict, *, pfad: Path = PFAD, **weitere) -> dict:
    """DATA_VIEW (z. B. daten = Abzugs-Hashes)."""
    return anhaengen(_body("DATA_VIEW", familie, variante, split, datum, {"daten": daten, **weitere}), pfad)


def versuch(familie: str, variante: str, datum: str, *, pfad: Path = PFAD, **felder) -> dict:
    """TRIAL auf den Entwicklungsdaten (mit `code=code_hashes()` prüft `pruefen` gegen die Vorregistrierung)."""
    return anhaengen(_body("TRIAL", familie, variante, "DEVELOPMENT", datum, felder), pfad)


def aenderung_nach_sicht(dateien: list[str], grund: str, datum: str, *, root: Path = ROOT, pfad: Path = PFAD,
                         lauf: str = LAUF) -> dict:
    """CHANGE_AFTER_VIEW (Werkzeugfamilie des Laufs, z. B. F04-WERKZEUG, Variante W<n>): erlaubt die neuen, committeten Hashes dieser
    Dateien – nur für die Versuche desselben Laufs."""
    werkzeug = runde(lauf)["werkzeug"]
    root, dateien = Path(root), list(dateien)
    if not dateien or not (isinstance(grund, str) and grund.strip()):
        raise ProtokollFehler("Dateien und Grund nötig")
    log = lesen(pfad)
    _kette_heil(log)
    code = code_hashes(dateien, root)
    if not git_sauber(root, dateien):
        raise ProtokollFehler("geänderte Dateien nicht committet (git status nicht leer)")
    n = 1 + sum(1 for e in log if e["body"].get("kind") == "CHANGE_AFTER_VIEW" and e["body"].get("family") == werkzeug)
    return anhaengen({"kind": "CHANGE_AFTER_VIEW", "actor": "CODING_AGENT", "date": datum, "family": werkzeug,
                      "variant_id": f"W{n}", "reason": grund, "commit": git_kopf(root), "code": code}, pfad)


# ---------------------------------------------------------------- Prüfung
def pruefen(pfad: Path = PFAD, *, root: Path = ROOT) -> list[str]:
    """Alle Befunde (leer = verifiziert): Kette und Regeln (trials.verify), Vorregistrierung gegen Datei und Commit,
    Code der Versuche gegen die Vorregistrierung (Abweichung nur mit vorherigem CHANGE_AFTER_VIEW derselben Hashes)."""
    root = Path(root)
    try:
        log = lesen(pfad)
    except ProtokollFehler as exc:
        return [f"LESEN:{exc}"]
    befunde = list(trials.verify(log))
    datei_sha: dict[str, str | None] = {}
    im_commit: dict[tuple[str, str], str | None] = {}
    prereg_code: dict[str, dict] = {}
    prereg_mechanik: dict[str, str | None] = {}
    familie_lauf: dict[str, str] = {}                        # Familie → Lauf ihrer Vorregistrierung
    signiert: set[str] = set()
    erlaubt: dict[str, set[tuple[str, str]]] = {}            # Werkzeugfamilie → erlaubte (Pfad, Hash)

    def prereg_datei_sha(rel: str) -> str | None:
        if rel not in datei_sha:
            datei_sha[rel] = sha256_datei(root / rel) if (root / rel).is_file() else None
        return datei_sha[rel]

    def commit_pruefen(seq: int, b: Mapping, soll: list[tuple[str, object]]) -> None:
        commit = b.get("commit")
        if not ist_vorfahr(root, commit):
            befunde.append(f"COMMIT_KEIN_VORFAHR:{seq}")
        falsch: dict[str, None] = {}
        for rel, h in soll:
            if (commit, rel) not in im_commit:
                try:
                    im_commit[(commit, rel)] = datei_im_commit_sha(root, commit, rel)
                except ProtokollFehler:
                    im_commit[(commit, rel)] = None
            if im_commit[(commit, rel)] != h:
                falsch[rel] = None
        befunde.extend(f"CODE_NICHT_IM_COMMIT:{seq}:{rel}" for rel in falsch)

    gesehen: set[str] = set()                                 # Familien mit Datensicht oder Versuch
    for i, e in enumerate(log):
        b = e["body"]
        kind, familie = b.get("kind"), b.get("family")
        code = _code(b)
        if kind == "PREREG_SIGNED" and familie in gesehen:
            befunde.append(f"NEUSIGNATUR_NACH_SICHT:{i}")        # nach der Sicht gilt die erste Vorregistrierung; neu = neuer Versuch
        if kind in ("DATA_VIEW", "TRIAL"):
            gesehen.add(familie)
        if kind == "TRIAL" and b.get("phase") == "ERGEBNIS":
            befunde.extend(_artefakte_pruefen(i, b, root))
        if kind == "PREREG_SIGNED":
            signiert.add(familie)
            if "lauf" in b:
                r = runde(str(b.get("lauf")))
                familie_lauf[familie] = str(b.get("lauf"))
                if b.get("prereg_sha") != r["prereg_sha"] or prereg_datei_sha(r["prereg_rel"]) != r["prereg_sha"]:
                    befunde.append(f"PREREG_SHA:{i}")
                if not code:
                    befunde.append(f"CODE_FEHLT:{i}")
                commit_pruefen(i, b, [*(code or {}).items(), (SCHWELLEN_REL, b.get("schwellen_sha")),
                                      (TRADE_TEST_REL, b.get("trade_test_sha"))])
                prereg_code[familie] = code or {}
                prereg_mechanik[familie] = b.get("mechanik_hash")
        elif kind == "CHANGE_AFTER_VIEW" and familie in WERKZEUG_FAMILIEN:
            if not code:
                befunde.append(f"CODE_FEHLT:{i}")
            commit_pruefen(i, b, list((code or {}).items()))
            erlaubt.setdefault(familie, set()).update((code or {}).items())
        elif kind in ("DATA_VIEW", "TRIAL") and familie in ALLE_FAMILIEN and familie not in signiert and b.get("split") != "DEVELOPMENT":
            befunde.append(f"VOR_PREREG:{i}")                  # DEVELOPMENT meldet bereits trials.verify
        if kind == "TRIAL" and familie in prereg_code:
            basis = prereg_code[familie]
            frei = erlaubt.get(runde(familie_lauf.get(familie, LAUF))["werkzeug"], set())
            if not code:
                befunde.append(f"CODE_FEHLT:{i}")
            else:
                befunde.extend(f"CODE_ABWEICHUNG:{i}:{rel}" for rel, h in code.items() if h != basis.get(rel) and (rel, h) not in frei)
                befunde.extend(f"CODE_FEHLT:{i}:{rel}" for rel in basis if rel not in code)
            soll_m = prereg_mechanik.get(familie)
            if soll_m is not None and b.get("mechanik_hash") != soll_m:
                befunde.append(f"MECHANIK_ABWEICHUNG:{i}")
        elif kind == "TRIAL" and "code" in b:
            befunde.append(f"CODE_OHNE_PREREG:{i}")
    befunde.extend(_umgeschrieben(Path(pfad), root))
    return befunde


def _artefakte_pruefen(seq: int, b: Mapping, root: Path) -> list[str]:
    """Bericht (berichte/forschung/) und Modelldatei (forschung/modelle/F05/ bzw. F05B/ nach Familie) eines ERGEBNIS-Eintrags gegen ihren
    SHA-256. Fehlt die Datei, ist das ein Befund – außer im öffentlichen Spiegel (Wurzel trägt PUBLIC_SNAPSHOT.md), der Modelldateien
    nicht enthält."""
    spiegel = (Path(root) / "PUBLIC_SNAPSHOT.md").is_file()
    aus = []
    for feld, sha_feld, ordner, art in (("bericht", "bericht_sha", "berichte/forschung", "BERICHT"),
                                        ("modell_datei", "modell_sha", "forschung/modelle/F05B" if str(b.get("family", "")).startswith("F05B")
                                         else "forschung/modelle/F05", "MODELL")):
        name, soll = b.get(feld), b.get(sha_feld)
        if not isinstance(name, str) or not isinstance(soll, str):
            continue
        if "/" in name or "\\" in name or ".." in name:
            aus.append(f"{art}_PFAD:{seq}")
            continue
        datei = Path(root) / ordner / name
        if not datei.is_file():
            if not (spiegel and art == "MODELL"):
                aus.append(f"{art}_FEHLT:{seq}")
        elif sha256_datei(datei) != soll:
            aus.append(f"{art}_ABWEICHUNG:{seq}")
    return aus


def _umgeschrieben(pfad: Path, root: Path) -> list[str]:
    """Ist das Protokoll committet, muss der Stand im HEAD ein Byte-Präfix der Datei sein (nichts abgeschnitten oder neu geschrieben)."""
    try:
        rel = pfad.resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError):
        return []
    erg = _git(root, "show", f"HEAD:{rel}")
    if erg.returncode != 0:
        return []                                             # (noch) nicht committet
    jetzt = pfad.read_bytes() if pfad.is_file() else b""
    return [] if jetzt.startswith(erg.stdout) else ["UMGESCHRIEBEN:Stand im HEAD ist kein Präfix der Datei"]


def laeufe(pfad: Path = PFAD) -> list[str]:
    """Läufe mit Vorregistrierung im Protokoll (Reihenfolge des ersten Eintrags); leer → ["F-04"] (Pflicht seit F-04)."""
    aus: list[str] = []
    for e in lesen(pfad):
        lauf = e["body"].get("lauf")
        if e["body"].get("kind") == "PREREG_SIGNED" and isinstance(lauf, str) and lauf not in aus:
            aus.append(lauf)
    return aus or [LAUF]


def vollstaendigkeit(pfad: Path = PFAD, *, lauf: str = LAUF, varianten_ids: Iterable[str] | None = None) -> list[str]:
    """Fehlende Pflichteinträge eines vollständigen Versuchsnachweises des Laufs (leer = vollständig): je Familie PREREG_SIGNED, eine
    Datensicht der Datenfamilie (F04-DATEN bzw. F05-DATEN), je Variante TRIAL BEGINN und ERGEBNIS in einer Familie des Laufs. Ein leeres
    Protokoll ist nicht vollständig."""
    r = runde(lauf)
    daten_familie = r["familien"][-1]                         # die Datenfamilie steht je Runde zuletzt
    if varianten_ids is None:
        if lauf == "F-05":
            from kit.research.meta import VARIANTEN
            varianten_ids = [v.id for v in VARIANTEN]
        elif lauf == "F-05b":
            from kit.research.richtung import VARIANTEN as RICHTUNG
            varianten_ids = [v.id for v in RICHTUNG]
        else:
            from kit.strategy.varianten import varianten
            varianten_ids = [v.id for v in varianten()]
    log = lesen(pfad)
    if not log:
        return ["LEER"]
    fehlt = [f"PREREG_FEHLT:{f}" for f in r["familien"]
             if not any(e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("family") == f and e["body"].get("lauf") == lauf
                        for e in log)]
    if not any(e["body"].get("kind") == "DATA_VIEW" and e["body"].get("family") == daten_familie for e in log):
        fehlt.append("DATENSICHT_FEHLT")
    for vid in varianten_ids:
        phasen = {e["body"].get("phase") for e in log if e["body"].get("kind") == "TRIAL" and e["body"].get("variant_id") == vid
                  and e["body"].get("family") in r["familien"]}
        fehlt += [f"{ph}_FEHLT:{vid}" for ph in ("BEGINN", "ERGEBNIS") if ph not in phasen]
    return fehlt


def vorpruefung(*, pfad: Path = PFAD, root: Path = ROOT, lauf: str = LAUF, dateien: Iterable[str] | None = None) -> dict:
    """Fail-closed vor jeder Datensicht und Auswertung: Protokoll ohne Befund, je Familie ein PREREG_SIGNED dieses Laufs, aktueller
    Code (Code-Liste der Runde) und mechanik_hash gleich dem Signierten (Abweichung nur mit CHANGE_AFTER_VIEW derselben Hashes in der
    Werkzeugfamilie der Runde), Code, Mechanik und Vorregistrierung committet. Rückgabe: commit, mechanik_hash, code, prereg_sha."""
    r = runde(lauf)
    familien, werkzeug, prereg_rel, prereg_sha = r["familien"], r["werkzeug"], r["prereg_rel"], r["prereg_sha"]
    root, dateien = Path(root), list(r["code"] if dateien is None else dateien)
    befunde = pruefen(pfad, root=root)
    if befunde:
        raise ProtokollFehler(f"Versuchsprotokoll mit Befunden: {', '.join(befunde[:5])}")
    log = lesen(pfad)
    signiert = {e["body"]["family"]: e["body"] for e in log if e["body"].get("kind") == "PREREG_SIGNED" and e["body"].get("lauf") == lauf
                and e["body"].get("family") in familien}
    if set(signiert) != set(familien):
        raise ProtokollFehler("Vorregistrierung fehlt (kit forschung vorab)")
    erlaubt = {(rel, h) for e in log if e["body"].get("kind") == "CHANGE_AFTER_VIEW" and e["body"].get("family") == werkzeug
               for rel, h in (_code(e["body"]) or {}).items()}
    code = code_hashes(dateien, root)
    mechanik = _mechanik_hash(root)
    for familie, b in signiert.items():
        soll = _code(b) or {}
        abw = [rel for rel in set(soll) | set(code) if code.get(rel) != soll.get(rel) and (rel, code.get(rel)) not in erlaubt]
        if abw:
            raise ProtokollFehler(f"Code weicht von der Vorregistrierung ab ({familie}): {', '.join(sorted(abw)[:5])}")
        if b.get("mechanik_hash") != mechanik:
            raise ProtokollFehler(f"mechanik_hash weicht von der Vorregistrierung ab ({familie})")
    if not git_sauber(root, [*dateien, prereg_rel, SCHWELLEN_REL, TRADE_TEST_REL, *mechanik_dateien(root)]):
        raise ProtokollFehler("Arbeitsbaum nicht sauber (Code, Mechanik oder Vorregistrierung nicht committet)")
    return {"commit": git_kopf(root), "mechanik_hash": mechanik, "code": code, "prereg_sha": prereg_sha}


def _code(b: Mapping) -> dict[str, str] | None:
    """Feld code als {Pfad: SHA}; fehlt es oder ist es kein solches Mapping: None."""
    code = b.get("code")
    if isinstance(code, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in code.items()):
        return code
    return None
