"""Geheimnis- und Personendaten-Scan der Fast-Track-Läufe (nur Standardbibliothek, Python >= 3.11).

Herkunft der Muster (Kopie, kein Import, damit der öffentliche Spiegel ohne validation/ läuft):
- PEM_RE, TOKEN_PATTERNS, TELEGRAM_ID, token_hit: validation/checks_semantics.py (Tag konzept-c12-wip)
- USER_PATH: validation/checks_hygiene.py (Tag konzept-c12-wip)
- MT5-Muster: neu (Login-/Kontonummer-Zuweisung, Passwort-Zuweisung, MT5-Journalzeile)

Sperrliste (nie im Repo): %LOCALAPPDATA%\\kit\\sperrliste.txt, je Zeile "art | wert | ersatz-oder-bezeichnung".
Arten: benutzer (Windows-Name; Pfade werden geprüft), ersetzen (nur öffentlich), geheim (blockiert immer),
geheim-hash (sha256:<hex> einer 5-12-stelligen Zahl, z. B. MT5-Login; blockiert immer).

Aufrufe:
  python tools/kit_scan.py --gestaged                 hinzugefügte Zeilen im Index (gegen HEAD)
  python tools/kit_scan.py --bereich A..B             hinzugefügte Zeilen eines Commit-Bereichs
  python tools/kit_scan.py --baum                     alle verfolgten Dateien, nur Geheimnis-/Token-/Login-Muster (Basislinie)
  python tools/kit_scan.py --export ORDNER            Null-Toleranz für den öffentlichen Spiegel (alle Kategorien)
Rückgabe: 0 ohne Befund, 1 mit Befund, 2 Werkzeugfehler. Werte werden nie im Klartext ausgegeben.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- Kopie aus validation/checks_semantics.py -------------------------------------------------------------------------
PEM_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----\s*[A-Za-z0-9+/=\s:,.-]{40,}?-----END (?:[A-Z0-9]+ )*PRIVATE KEY")
TOKEN_PATTERNS = {
    "AWS-Zugangsschlüssel": (re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"), "A-Z0-9"),
    "GitHub-Token": (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}"), "A-Za-z0-9_"),
    "Slack-Token": (re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"), "A-Za-z0-9"),
    "API-Schlüssel sk-": (re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}"), "A-Za-z0-9_-"),
    "Google-API-Schlüssel": (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "A-Za-z0-9"),
    "Telegram-Bot-Token": (re.compile(r":AA[A-Za-z0-9_-]{33}(?![A-Za-z0-9_-])"), "TELEGRAM"),
    "JWT": (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "A-Za-z0-9_-"),
}
TELEGRAM_ID = re.compile(r"(?<![0-9A-Za-z])[0-9]{8,10}")
# --- Kopie aus validation/checks_hygiene.py ---------------------------------------------------------------------------
USER_PATH = re.compile(r"(?i)(?<![\w])[a-z]:(?:\\+|/)(?:users|benutzer|documents and settings)(?:\\+|/)([^\\/\s\"'`<>|*?]+)"
                       r"|(?<![\w.:/-])/(?:home|Users)/([^/\s\"'`<>]+)")
# --- neu ---------------------------------------------------------------------------------------------------------------
MT5_LOGIN = re.compile(r"(?i)\b(?:login|kontonummer|konto|account)\b[\"']?\s*[:=]\s*[\"']?(\d{5,12})\b")
PASSWORT = re.compile(r"(?i)\b(?:password|passwort|passwd|pwd|investor_password)\b[\"']?\s*[:=]\s*[\"']([^\"'\s]{4,})[\"']")
MT5_JOURNAL = re.compile(r"'(\d{5,12})': (?:authorized|login|connected)")
ZAHL = re.compile(r"(?<!\d)(\d{5,12})(?!\d)")
ERLAUBTE_PFADNAMEN = {"benutzer", "<benutzerordner>", "probenutzer", "x", "public", "default", "<name>", "name", "%username%", "$env:username"}
TEXT_ENDUNGEN = (".py", ".pyi", ".json", ".jsonl", ".md", ".txt", ".toml", ".in", ".lock", ".yml", ".yaml", ".cfg", ".ini", ".csv",
                 ".ps1", ".sh", ".mq5", ".html", ".css", ".js", ".gitignore", ".gitattributes")
GEHEIMNIS_KATEGORIEN = {"PEM", "TOKEN", "MT5_LOGIN", "PASSWORT", "MT5_JOURNAL", "GEHEIM", "GEHEIM_HASH"}


@dataclass(frozen=True)
class Befund:
    datei: str
    zeile: int
    kategorie: str
    abdruck: str      # sha256[:16] des Treffers (für die Basislinie, nie der Wert)
    maske: str        # erstes Zeichen + Länge

    def text(self) -> str:
        return f"{self.datei}:{self.zeile} {self.kategorie} {self.maske} [{self.abdruck}]"


@dataclass(frozen=True)
class Eintrag:
    art: str
    wert: str
    ersatz: str


def _maske(wert: str) -> str:
    return f"{wert[:1]}…({len(wert)})"


def _abdruck(wert: str) -> str:
    return hashlib.sha256(wert.encode("utf-8")).hexdigest()[:16]


def standard_sperrliste() -> Path:
    basis = os.environ.get("KIT_SPERRLISTE")
    if basis:
        return Path(basis)
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "kit" / "sperrliste.txt"


def lade_sperrliste(pfad: Path | None) -> list[Eintrag]:
    if pfad is None or not pfad.is_file():
        return []
    if ROOT in pfad.resolve().parents:
        raise SystemExit("Sperrliste liegt im Repository – Abbruch (sie gehört nach %LOCALAPPDATA%\\kit).")
    out = []
    for roh in pfad.read_text(encoding="utf-8").splitlines():
        zeile = roh.strip()
        if not zeile or zeile.startswith("#"):
            continue
        teile = [t.strip() for t in zeile.split("|")]
        if len(teile) < 2 or teile[0] not in {"benutzer", "ersetzen", "geheim", "geheim-hash"} or not teile[1]:
            raise SystemExit(f"Sperrliste: ungültige Zeile ({_maske(zeile)})")
        out.append(Eintrag(teile[0], teile[1], teile[2] if len(teile) > 2 else ""))
    return out


def token_hit(text: str, pat: re.Pattern, prev: str) -> list[re.Match]:
    treffer = []
    for m in pat.finditer(text):
        if prev == "TELEGRAM":
            vor = text[max(0, m.start() - 11):m.start()]
            if TELEGRAM_ID.search(vor) and re.search(r"(?:^|[^0-9A-Za-z])[0-9]{8,10}$", vor):
                treffer.append(m)
            continue
        if m.start() == 0 or not re.fullmatch(f"[{prev}]", text[m.start() - 1]):
            treffer.append(m)
    return treffer


def _wortmuster(wert: str) -> re.Pattern:
    return re.compile(r"(?i)(?<![A-Za-z0-9])" + re.escape(wert) + r"(?![A-Za-z0-9])")


def scan_text(datei: str, text: str, sperrliste: list[Eintrag], *, oeffentlich: bool, nur_geheimnisse: bool = False,
              zeilen: list[int] | None = None) -> list[Befund]:
    """Prüft text; zeilen = 1-basierte Zeilennummern der Textzeilen (für Diff-Ausschnitte), sonst fortlaufend."""
    befunde: list[Befund] = []
    teile = text.split("\n")
    nummern = zeilen if zeilen is not None else list(range(1, len(teile) + 1))
    benutzer = [e for e in sperrliste if e.art == "benutzer"]
    geheim = [e for e in sperrliste if e.art == "geheim"]
    hashes = {e.wert.lower().removeprefix("sha256:"): e.ersatz for e in sperrliste if e.art == "geheim-hash"}
    ersetzen = [e for e in sperrliste if e.art == "ersetzen"]

    def neu(nr: int, kat: str, wert: str) -> None:
        befunde.append(Befund(datei, nr, kat, _abdruck(wert), _maske(wert)))

    for nr, zeile in zip(nummern, teile, strict=False):
        for m in PEM_RE.finditer(zeile):
            neu(nr, "PEM", m.group(0))
        for label, (pat, prev) in TOKEN_PATTERNS.items():
            for m in token_hit(zeile, pat, prev):
                neu(nr, f"TOKEN:{label}", m.group(0))
        for m in MT5_LOGIN.finditer(zeile):
            neu(nr, "MT5_LOGIN", m.group(1))
        for m in PASSWORT.finditer(zeile):
            neu(nr, "PASSWORT", m.group(1))
        for m in MT5_JOURNAL.finditer(zeile):
            neu(nr, "MT5_JOURNAL", m.group(1))
        for e in geheim:
            for m in _wortmuster(e.wert).finditer(zeile):
                neu(nr, "GEHEIM", m.group(0))
        if hashes:
            for m in ZAHL.finditer(zeile):
                if hashlib.sha256(m.group(1).encode()).hexdigest() in hashes:
                    neu(nr, "GEHEIM_HASH", m.group(1))
        if nur_geheimnisse:
            continue
        for m in USER_PATH.finditer(zeile):
            name = (m.group(1) or m.group(2) or "").strip().lower()
            if name not in ERLAUBTE_PFADNAMEN:
                neu(nr, "BENUTZERPFAD", m.group(0))
        for e in benutzer:
            for m in _wortmuster(e.wert).finditer(zeile):
                neu(nr, "BENUTZERNAME", m.group(0))
        if oeffentlich:
            for e in ersetzen:
                for m in _wortmuster(e.wert).finditer(zeile):
                    neu(nr, "ERSETZEN", m.group(0))
    # PEM über Zeilengrenzen
    if not any(b.kategorie == "PEM" for b in befunde):
        for m in PEM_RE.finditer(text):
            nr = nummern[min(len(nummern) - 1, text[:m.start()].count("\n"))] if nummern else 1
            neu(nr, "PEM", m.group(0))
    return befunde


# --- Git-Hilfen ----------------------------------------------------------------------------------------------------------
def _git(*args: str) -> str:
    erg = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=ROOT, capture_output=True, check=False)
    if erg.returncode != 0:
        raise SystemExit(f"git {' '.join(args[:2])} fehlgeschlagen: {erg.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return erg.stdout.decode("utf-8", "replace")


def regeln() -> dict:
    return json.loads((ROOT / "tools" / "repo_regeln.json").read_text(encoding="utf-8"))


def ist_eingefroren(pfad: str, r: dict | None = None) -> bool:
    r = r or regeln()
    muster = r.get("eingefroren", []) + r.get("eingefroren_genutzt", [])
    lebend = r.get("lebend", [])
    if any(fnmatch.fnmatch(pfad, m) for m in lebend):
        return False
    return any(fnmatch.fnmatch(pfad, m) for m in muster)


def diff_zeilen(diff_args: list[str]) -> dict[str, list[tuple[int, str]]]:
    """Hinzugefügte Zeilen je Datei aus einem unified diff (-U0)."""
    roh = _git("diff", "-U0", "--no-color", "--no-ext-diff", "-M", *diff_args)
    out: dict[str, list[tuple[int, str]]] = {}
    datei = None
    nr = 0
    for zeile in roh.split("\n"):
        if zeile.startswith("+++ "):
            ziel = zeile[4:]
            datei = None if ziel == "/dev/null" else ziel[2:] if ziel.startswith("b/") else ziel
            continue
        if zeile.startswith("@@"):
            m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", zeile)
            nr = int(m.group(1)) if m else 0
            continue
        if datei and zeile.startswith("+") and not zeile.startswith("+++"):
            out.setdefault(datei, []).append((nr, zeile[1:]))
            nr += 1
    return out


def scan_diff(diff_args: list[str], sperrliste: list[Eintrag]) -> list[Befund]:
    r = regeln()
    befunde: list[Befund] = []
    for datei, zeilen in diff_zeilen(diff_args).items():
        if not datei.lower().endswith(TEXT_ENDUNGEN) and "." in Path(datei).name:
            continue
        text = "\n".join(z for _, z in zeilen)
        befunde += scan_text(datei, text, sperrliste, oeffentlich=False, nur_geheimnisse=ist_eingefroren(datei, r),
                             zeilen=[n for n, _ in zeilen])
    return befunde


def lade_basislinie() -> set[tuple[str, str, str]]:
    pfad = ROOT / ".scan_basislinie.json"
    if not pfad.is_file():
        return set()
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    for e in daten.get("eintraege", []):
        if not e.get("grund"):
            raise SystemExit(f"Basislinie ohne Begründung: {e.get('datei')}")
    return {(e["datei"], e["kategorie"], e["abdruck"]) for e in daten.get("eintraege", [])}


def scan_baum(sperrliste: list[Eintrag]) -> list[Befund]:
    basis = lade_basislinie()
    befunde: list[Befund] = []
    for datei in _git("ls-files", "-z").split("\0"):
        if not datei:
            continue
        pfad = ROOT / datei
        try:
            roh = pfad.read_bytes()
        except OSError:
            continue
        text = roh.decode("utf-8", "replace") if datei.lower().endswith(TEXT_ENDUNGEN) else roh.decode("latin-1")
        for b in scan_text(datei, text, sperrliste, oeffentlich=False, nur_geheimnisse=True):
            if (b.datei, b.kategorie, b.abdruck) not in basis:
                befunde.append(b)
    return befunde


def scan_export(ordner: Path, sperrliste: list[Eintrag]) -> list[Befund]:
    befunde: list[Befund] = []
    for pfad in sorted(ordner.rglob("*")):
        if not pfad.is_file() or ".git" in pfad.relative_to(ordner).parts:
            continue
        rel = pfad.relative_to(ordner).as_posix()
        befunde += scan_text(f"{rel} (Dateiname)", rel, sperrliste, oeffentlich=True)
        roh = pfad.read_bytes()
        for text in (roh.decode("utf-8", "replace"), roh.decode("utf-16-le", "replace") if b"\x00" in roh else ""):
            if text:
                befunde += scan_text(rel, text, sperrliste, oeffentlich=True)
    return befunde


def main(argv: list[str] | None = None) -> int:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Geheimnis-/Personendaten-Scan (Fast-Track)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--gestaged", action="store_true")
    g.add_argument("--bereich")
    g.add_argument("--baum", action="store_true")
    g.add_argument("--export", type=Path)
    ap.add_argument("--sperrliste", type=Path, default=None)
    a = ap.parse_args(argv)
    try:
        liste = lade_sperrliste(a.sperrliste or standard_sperrliste())
        if a.gestaged:
            befunde = scan_diff(["--cached"], liste)
        elif a.bereich:
            befunde = scan_diff([a.bereich], liste)
        elif a.baum:
            befunde = scan_baum(liste)
        else:
            if not liste:
                print("Öffentlicher Scan ohne Sperrliste ist nicht erlaubt.", file=sys.stderr)
                return 2
            befunde = scan_export(a.export, liste)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    for b in befunde:
        print(b.text())
    print(f"kit_scan: {len(befunde)} Befund(e)" + ("" if liste else " (ohne Sperrliste – nur allgemeine Muster)"))
    return 1 if befunde else 0


if __name__ == "__main__":
    raise SystemExit(main())
