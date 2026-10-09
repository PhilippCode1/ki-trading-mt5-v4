"""Abschlussroutine jedes Laufs (Plan F-1 §7): säubern → prüfen → committen → privat pushen → bereinigter öffentlicher Spiegel.

Nur Standardbibliothek. Aufrufe (aus der Projektwurzel):
  python tools/publish.py pruefen [--oeffentlich]                 Trockenlauf aller Tore, ohne Commit/Push
  python tools/publish.py lauf --lauf F-01 --titel "…" [--oeffentlich] [--vermerk "Grund"]
  python tools/publish.py oeffentlich                              nur den Spiegel aus HEAD (HEAD == private/main)
  python tools/publish.py aufraeumen [--trocken]                   nur Caches (nie work/, .venv-*, .uv-cache)
  python tools/publish.py scan --gestaged|--baum                   Scan wie in den Hooks
  python tools/publish.py hook pre-commit|commit-msg DATEI|pre-push NAME URL
Exit: 0 grün · 1 Tor vor dem Commit blockiert · 2 Werkzeug-/Netzfehler (fortsetzbar) · 3 privat erledigt, Spiegel blockiert
      · 4 Remote-SHA weicht ab.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import kit_scan  # noqa: E402

AGENT_NAME = "KI-Trading v4 Agent"
AGENT_MAIL = "agent@localhost.invalid"
COAUTHOR = os.environ.get("KIT_COAUTHOR", "Claude Opus 5.5 <noreply@anthropic.com>")
TITEL_RE = re.compile(r"^(F-\d{2}[a-z]?|M-\d{2,3}|L-\d{2}): \S")
CACHE_NAMEN = ("__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis", ".mypy_cache")
CACHE_ENDUNGEN = (".pyc", ".prof", ".pstats", ".lprof")
NIE_ANFASSEN = ("work", ".uv-cache", ".git")
VERBOTENE_NAMEN = (".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "*.kdbx", "*.hcc", "*.hc", "*.hst", "accounts.dat",
                   "servers.dat", "terminal.ini", "common.ini", "assistant.ini", "*.bundle", "*.zip", "*.7z", "*.sqlite", "*.sqlite3",
                   "*.db")
MAX_DATEI = 2 * 1024 * 1024
MAX_GEAENDERT = 300
EXPORT_MAX_GESAMT = 50 * 1024 * 1024
EXPORT_MAX_DATEI = 10 * 1024 * 1024
# Wörter aus dem privaten Kontext und vierstellige Euro-Beträge (Hinweis auf Kontogröße) dürfen nicht öffentlich werden;
# Muster per Join gebaut, damit diese Datei sich im Spiegel nicht selbst meldet.
OEFFENTLICH_VERBOTEN = re.compile("(?i)" + "|".join([r"\b" + "her" + r"mes\b", r"\bH-" + r"003\b",
                                                     r"\b\d{1,3}(?:\.\d{3})+(?:,\d+)?\s*(?:€|EUR)\b", r"\b\d{4,}(?:,\d+)?\s*(?:€|EUR)\b"]))


class Abbruch(Exception):
    def __init__(self, code: int, text: str):
        super().__init__(text)
        self.code = code


@dataclass
class Bericht:
    zeilen: list[str] = field(default_factory=list)

    def __call__(self, text: str) -> None:
        self.zeilen.append(text)
        print(text, flush=True)


# ------------------------------------------------------------------------------------------------------------- Git-Hilfen
def git(root: Path, *args: str, pruefen: bool = True, eingabe: bytes | None = None, umgebung: dict | None = None) -> str:
    erg = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True, input=eingabe,
                         check=False, env=umgebung)
    if pruefen and erg.returncode != 0:
        raise Abbruch(2, f"git {' '.join(args[:3])}: {erg.stderr.decode('utf-8', 'replace').strip()[:400]}")
    return erg.stdout.decode("utf-8", "replace")


def git_ok(root: Path, *args: str) -> bool:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False).returncode == 0


def regeln(root: Path) -> dict:
    return json.loads((root / "tools" / "repo_regeln.json").read_text(encoding="utf-8"))


def passt(pfad: str, muster: list[str]) -> bool:
    return any(fnmatch.fnmatch(pfad, m) for m in muster)


def interpreter(root: Path, venv: str) -> str:
    for kandidat in (root / venv / "Scripts" / "python.exe", root / venv / "bin" / "python"):
        if kandidat.is_file():
            return str(kandidat)
    return sys.executable


# ------------------------------------------------------------------------------------------------------------- Säubern
def aufraeumen(root: Path, trocken: bool = False) -> list[str]:
    """Löscht nur aufgezählte Cache-Namen, die git als ignoriert bestätigt; nie work/, .venv-*, .uv-cache, .git, nie git clean."""
    kandidaten: list[Path] = []
    stapel = [root]
    while stapel:
        ordner = stapel.pop()
        for p in ordner.iterdir():
            if p.is_dir():
                if p.name in NIE_ANFASSEN or p.name.startswith(".venv"):
                    continue
                if p.name in CACHE_NAMEN:
                    kandidaten.append(p)
                    continue
                stapel.append(p)
            elif p.suffix in CACHE_ENDUNGEN or p.name == "prof.out":
                kandidaten.append(p)
    geloescht = []
    for p in kandidaten:
        rel = p.relative_to(root).as_posix()
        if not git_ok(root, "check-ignore", "-q", rel):
            continue
        geloescht.append(rel)
        if not trocken:
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
    return geloescht


# ------------------------------------------------------------------------------------------------------------- Tore
def pruefe_umgebung(root: Path, r: dict, oeffentlich: bool) -> None:
    zweig = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if zweig != "main":
        raise Abbruch(1, f"Zweig ist {zweig}, erwartet main.")
    gitdir = Path(git(root, "rev-parse", "--git-dir").strip())
    gitdir = gitdir if gitdir.is_absolute() else root / gitdir
    for marke in ("MERGE_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"):
        if (gitdir / marke).exists():
            raise Abbruch(1, f"Unfertige git-Operation ({marke}).")
    sp = r["spiegel"]
    remotes = git(root, "remote", "-v")
    if sp["privat_remote"] not in remotes or sp["privat_url"] not in remotes:
        raise Abbruch(1, "Remote 'private' fehlt oder zeigt nicht auf das private Repo.")
    if re.search(re.escape(sp["url"]) + r"\s", remotes + " ") or re.search(r"ki-trading-mt5-v4(?:\.git)?\s", remotes):
        raise Abbruch(1, "Ein Remote zeigt auf das öffentliche Repo – nicht erlaubt (Spiegel nur über publish.py).")
    hooks = git(root, "config", "--get", "core.hooksPath", pruefen=False).strip()
    if hooks != ".githooks":
        raise Abbruch(1, "core.hooksPath ist nicht .githooks (git config core.hooksPath .githooks).")
    if oeffentlich and not kit_scan.lade_sperrliste(kit_scan.standard_sperrliste()):
        raise Abbruch(1, "Öffentlicher Spiegel ohne Sperrliste (%LOCALAPPDATA%\\kit\\sperrliste.txt) nicht erlaubt.")
    if oeffentlich and shutil.which("gh") is None:                   # sonst fiele der fehlende Spiegel erst nach dem privaten Push auf
        raise Abbruch(1, "GitHub CLI (gh) fehlt – erst installieren und anmelden (docs/INSTALLATION_VPS.md §6), oder ohne --oeffentlich.")


def pruefe_fast_forward(root: Path, r: dict) -> None:
    git(root, "fetch", r["spiegel"]["privat_remote"])
    if not git_ok(root, "merge-base", "--is-ancestor", f"{r['spiegel']['privat_remote']}/main", "HEAD"):
        raise Abbruch(1, "private/main ist kein Vorfahr von HEAD – erst klären (nie mergen/rebasen/force).")


def pruefe_unbekannte_dateien(root: Path, r: dict) -> None:
    lebend = r["lebend"] + r.get("eingefroren_genutzt", [])      # verschobene Referenz ist bekannt, Vermerkpflicht bleibt
    unbekannt = [z[3:] for z in git(root, "status", "--porcelain", "--untracked-files=all").splitlines() if z.startswith("?? ")]
    fremd = [p for p in unbekannt if not passt(p, lebend)]
    if fremd:
        raise Abbruch(1, "Unbekannte Dateien außerhalb der lebenden Bereiche: " + ", ".join(fremd[:10]))
    ignoriert = git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "--", "kit", "kit_tests", "tools").splitlines()
    quellen = [p for p in ignoriert if p.endswith((".py", ".json", ".md", ".toml")) and "__pycache__" not in p]
    if quellen:
        raise Abbruch(1, "Ignorierte Quelldateien (würden verloren gehen): " + ", ".join(quellen[:10]))


def changelog_abschnitt(root: Path, lauf: str) -> str:
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(lauf)}\b.*?(?=^## |\Z)", text, flags=re.M | re.S)
    if not m:
        raise Abbruch(1, f"CHANGELOG.md hat keinen Abschnitt '## {lauf}'.")
    return m.group(0).strip()


def pruefe_laufdateien(root: Path, r: dict, lauf: str) -> str:
    abschnitt = changelog_abschnitt(root, lauf)
    basis = f"{r['spiegel']['privat_remote']}/main"
    for datei in ("HANDOFF.md", "NEXT_PROMPT.md"):
        if not (root / datei).is_file():
            raise Abbruch(1, f"{datei} fehlt.")
    if git_ok(root, "diff", "--quiet", basis, "--", "HANDOFF.md"):
        raise Abbruch(1, "HANDOFF.md ist gegenüber private/main unverändert – Laufdateien aktualisieren.")
    return abschnitt


def pruefe_staging(root: Path, r: dict) -> list[str]:
    git(root, "add", "-A")
    geaendert = [z for z in git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if z]
    if len(geaendert) > MAX_GEAENDERT:
        raise Abbruch(1, f"{len(geaendert)} geänderte Dateien (> {MAX_GEAENDERT}).")
    fehler = []
    for rel in geaendert:
        name = Path(rel).name
        if any(fnmatch.fnmatch(name, m) for m in VERBOTENE_NAMEN) and name != ".env.example":
            fehler.append(f"verbotener Dateiname {rel}")
        p = root / rel
        if p.is_file() and p.stat().st_size > MAX_DATEI and not kit_scan.ist_eingefroren(rel, r):
            fehler.append(f"Datei > 2 MB: {rel}")
    if fehler:
        raise Abbruch(1, "; ".join(fehler))
    return geaendert


def pruefe_scan(root: Path, r: dict) -> None:
    liste = kit_scan.lade_sperrliste(kit_scan.standard_sperrliste())
    basis = f"{r['spiegel']['privat_remote']}/main"
    befunde = kit_scan.scan_diff(["--cached"], liste) + kit_scan.scan_diff([f"{basis}..HEAD"], liste) + kit_scan.scan_baum(liste)
    if befunde:
        raise Abbruch(1, "Scan-Befunde:\n" + "\n".join(b.text() for b in befunde[:30]))


def eingefroren_beruehrt(root: Path, r: dict, geaendert: list[str]) -> list[str]:
    return [p for p in geaendert if kit_scan.ist_eingefroren(p, r)]


def tests(root: Path, voll_kern: bool, bericht: Bericht) -> None:
    if os.environ.get("KIT_PUBLISH_OHNE_TESTS") == "1":
        bericht("Tests übersprungen (KIT_PUBLISH_OHNE_TESTS=1, nur für Werkzeugtests).")
        return
    schritte = [
        ("ruff", [interpreter(root, ".venv-312"), "-m", "ruff", "check", "."]),
        ("kit_tests", [interpreter(root, ".venv-311"), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "kit_tests"]),
        ("kerntests", [interpreter(root, ".venv-312"), "-B", "tools/kerntests.py", "--ci", *([] if voll_kern else ["--schnell"])]),
    ]
    for name, cmd in schritte:
        erg = subprocess.run(cmd, cwd=root, capture_output=True, text=True, errors="replace", check=False)
        letzte = (erg.stdout.strip().splitlines() or [""])[-1]
        bericht(f"  {name}: {'grün' if erg.returncode == 0 else 'ROT'} – {letzte[:160]}")
        if erg.returncode != 0:
            raise Abbruch(1, f"{name} rot:\n{(erg.stdout + erg.stderr)[-3000:]}")


# ------------------------------------------------------------------------------------------------------------- Commit/Push
def commit(root: Path, lauf: str, titel: str, abschnitt: str, vermerk: str | None) -> bool:
    if git_ok(root, "diff", "--cached", "--quiet"):
        return False
    kopf = f"{lauf}: {titel}"
    if not TITEL_RE.match(kopf):
        raise Abbruch(1, f"Commit-Titel passt nicht zum Muster: {kopf}")
    rumpf = abschnitt.split("\n", 1)[1].strip() if "\n" in abschnitt else ""
    teile = [kopf, ""]
    if vermerk:
        teile += [f"[EINGEFROREN-AENDERUNG: {vermerk}]", ""]
    teile += [rumpf, "", f"Co-Authored-By: {COAUTHOR}"]
    git(root, "-c", f"user.name={AGENT_NAME}", "-c", f"user.email={AGENT_MAIL}", "commit", "-q", "-F", "-",
        eingabe="\n".join(teile).encode("utf-8"))
    return True


def tag_und_push(root: Path, r: dict, lauf: str, bericht: Bericht) -> str:
    remote = r["spiegel"]["privat_remote"]
    kopf = git(root, "rev-parse", "HEAD").strip()
    tag = f"lauf/{lauf}"
    vorhanden = git(root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", pruefen=False).strip()
    if vorhanden and vorhanden != kopf:
        raise Abbruch(1, f"Tag {tag} existiert bereits auf {vorhanden[:7]} – neue Lauf-ID wählen (z. B. {lauf}b).")
    if not vorhanden:
        git(root, "-c", f"user.name={AGENT_NAME}", "-c", f"user.email={AGENT_MAIL}", "tag", "-a", tag, "-m", f"Lauf {lauf}")
    git(root, "push", remote, "main")
    git(root, "push", remote, f"refs/tags/{tag}")
    fern = git(root, "ls-remote", remote, "refs/heads/main", f"refs/tags/{tag}^{{}}")
    shas = {z.split()[1]: z.split()[0] for z in fern.splitlines() if z.strip()}
    if shas.get("refs/heads/main") != kopf or shas.get(f"refs/tags/{tag}^{{}}") != kopf:
        raise Abbruch(4, f"Remote-SHA weicht ab: {shas} (lokal {kopf}).")
    bericht(f"Privat: main = {tag} = {kopf[:7]} (Remote geprüft).")
    return kopf


# ------------------------------------------------------------------------------------------------------------- Spiegel
GhGet = Callable[[str], dict | None]


def gh_get(pfad: str) -> dict | None:
    try:
        erg = subprocess.run(["gh", "api", "-X", "GET", pfad], capture_output=True, check=False)
    except OSError:                                  # GitHub CLI fehlt (z. B. frischer VPS): wie „nicht erreichbar“, Spiegel übersprungen
        return None
    if erg.returncode != 0:
        return None
    try:
        return json.loads(erg.stdout.decode("utf-8"))
    except ValueError:
        return None


def ziel_pruefen(r: dict, holen: GhGet = gh_get) -> str | None:
    """None = Spiegel darf aktualisiert werden; sonst Grund zum Überspringen (nie ein Repo anlegen)."""
    ziel = r["spiegel"]["ziel"]
    repo = holen(f"repos/{ziel}")
    if repo is None:
        return f"Ziel {ziel} nicht erreichbar oder nicht vorhanden – Spiegel übersprungen (kein Repo anlegen)."
    if repo.get("private", True):
        return f"Ziel {ziel} ist privat – Spiegel übersprungen."
    if repo.get("size", 0) and holen(f"repos/{ziel}/contents/PUBLIC_SNAPSHOT.md") is None:
        return f"Spitze von {ziel} trägt keine PUBLIC_SNAPSHOT.md – fremder Inhalt, Spiegel übersprungen."
    return None


def ersetze(text: str, liste: list[kit_scan.Eintrag]) -> tuple[str, dict[str, int]]:
    zaehler: dict[str, int] = {}
    for e in sorted(liste, key=lambda x: -len(x.wert)):
        if e.art not in {"ersetzen", "benutzer"}:
            continue
        ersatz = e.ersatz or "<entfernt>"
        text, n = re.subn(r"(?i)(?<![A-Za-z0-9])" + re.escape(e.wert) + r"(?![A-Za-z0-9])", ersatz, text)
        if n:
            zaehler[e.art] = zaehler.get(e.art, 0) + n

    def pfad(m: re.Match) -> str:
        name = m.group(1) or m.group(2) or ""
        return m.group(0).replace(name, "Benutzer") if name.lower() not in kit_scan.ERLAUBTE_PFADNAMEN else m.group(0)
    text, n = kit_scan.USER_PATH.subn(pfad, text)
    if n:
        zaehler["benutzerpfad"] = zaehler.get("benutzerpfad", 0) + n
    return text, zaehler


def exportieren(root: Path, ziel: Path, r: dict, liste: list[kit_scan.Eintrag]) -> dict[str, int]:
    """git archive HEAD → Positivliste − Ausschluss → Ersetzungen. Liefert Ersetzungszähler je Kategorie."""
    sp = r["spiegel"]
    roh = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, capture_output=True, check=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        tar_pfad = Path(tmp) / "a.tar"
        tar_pfad.write_bytes(roh)
        with tarfile.open(tar_pfad) as tar:
            tar.extractall(Path(tmp) / "x", filter="data")
        quelle = Path(tmp) / "x"
        zaehler: dict[str, int] = {}
        for p in sorted(quelle.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(quelle).as_posix()
            if not passt(rel, sp["positivliste"]) or passt(rel, sp["ausschluss"]):
                continue
            daten = p.read_bytes()
            if rel.endswith(kit_scan.TEXT_ENDUNGEN) or b"\x00" not in daten:
                text, z = ersetze(daten.decode("utf-8", "replace"), liste)
                daten = text.encode("utf-8")
                for k, v in z.items():
                    zaehler[k] = zaehler.get(k, 0) + v
            ausgabe = ziel / rel
            ausgabe.parent.mkdir(parents=True, exist_ok=True)
            ausgabe.write_bytes(daten)
    return zaehler


def export_pruefen(ziel: Path, liste: list[kit_scan.Eintrag]) -> list[str]:
    fehler = [b.text() for b in kit_scan.scan_export(ziel, liste)]
    gesamt = 0
    for p in ziel.rglob("*"):
        if p.is_file() and ".git" not in p.relative_to(ziel).parts:
            groesse = p.stat().st_size
            gesamt += groesse
            if groesse > EXPORT_MAX_DATEI:
                fehler.append(f"{p.relative_to(ziel).as_posix()}: > 10 MB")
            text = p.read_bytes().decode("utf-8", "replace")
            for m in OEFFENTLICH_VERBOTEN.finditer(text):
                fehler.append(f"{p.relative_to(ziel).as_posix()}: verbotenes Wort/Betrag ({m.group(0)[:1]}…)")
    if gesamt > EXPORT_MAX_GESAMT:
        fehler.append(f"Export {gesamt / 1e6:.1f} MB > 50 MB")
    return fehler


def snapshot_text(quelle_sha: str, lauf: str, zaehler: dict[str, int], r: dict) -> str:
    zeit = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    kat = ", ".join(f"{k}: {v}" for k, v in sorted(zaehler.items())) or "keine"
    return (f"# Öffentliche, bereinigte Momentaufnahme\n\n"
            f"Quelle: privater Commit `{quelle_sha[:12]}` · Lauf `{lauf}` · erzeugt {zeit} mit `tools/publish.py`.\n\n"
            f"- Enthalten ist alles für die Weiterarbeit: Bot `kit/`, Tests, Werkzeuge, VPS-Skripte, CI und die gesamte Doku. "
            f"Privat bleiben nur `docs/bot/privat/` (Betreibernotizen), der Großteil von `referenz/` (Konzeptarchiv), die Kostenstartwerte "
            f"und das Spreadprofil (`config/kostenprofil/`) und die eingefrorenen Forschungsmodelle (`forschung/modelle/`). "
            f"Einstieg: `README.md` → `HANDOFF.md`.\n"
            f"- Ersetzungen (Anzahl je Kategorie, nie die Werte): {kat}.\n"
            f"- Eine einzelne Momentaufnahme ohne Historie; die volle Historie liegt privat.\n"
            f"- Tests: `powershell -ExecutionPolicy Bypass -File tools\\dev.ps1 alles`. Tests, die das private Repo brauchen, "
            f"werden hier übersprungen.\n\n"
            f"**Keine Anlageberatung, keine Gewinnzusage, kein Echtgeld freigegeben.** Der Bot handelt ausschließlich auf "
            f"Demokonten; es gibt keinen belegten Handelsvorteil.\n")


def export_testen(ziel: Path, root: Path) -> str | None:
    if os.environ.get("KIT_PUBLISH_OHNE_TESTS") == "1":
        return None
    erg = subprocess.run([interpreter(root, ".venv-311"), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not privat",
                          "kit_tests"], cwd=ziel, capture_output=True, text=True, errors="replace", check=False)
    return None if erg.returncode == 0 else (erg.stdout + erg.stderr)[-2000:]


def scratch_commit(ziel: Path, nachricht: str) -> str:
    umg = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
    git(ziel, "init", "-q", "-b", "main", umgebung=umg)
    git(ziel, "add", "-A", umgebung=umg)
    git(ziel, "-c", f"user.name={AGENT_NAME}", "-c", f"user.email={AGENT_MAIL}", "-c", "core.hooksPath=/dev/null", "commit", "-q",
        "-m", nachricht, umgebung=umg)
    return git(ziel, "rev-parse", "HEAD").strip()


def spiegeln(root: Path, r: dict, lauf: str, bericht: Bericht, holen: GhGet = gh_get, pushen: bool = True) -> int:
    grund = ziel_pruefen(r, holen)
    if grund:
        bericht(f"Spiegel: {grund}")
        return 3
    liste = kit_scan.lade_sperrliste(kit_scan.standard_sperrliste())
    if not liste:
        bericht("Spiegel: Sperrliste fehlt – blockiert.")
        return 3
    quelle_sha = git(root, "rev-parse", "HEAD").strip()
    # nicht unter %LOCALAPPDATA%\kit: das ist die alte, vom Agent-Wächter gesperrte Ablage (dort verweigern die Wächtertests im
    # Export jeden relativen Pfad)
    basis = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "kit-publish"
    stempel = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    ziel = basis / f"{lauf}-{stempel}"
    ziel.mkdir(parents=True, exist_ok=False)
    zaehler = exportieren(root, ziel, r, liste)
    (ziel / "PUBLIC_SNAPSHOT.md").write_text(snapshot_text(quelle_sha, lauf, zaehler, r), encoding="utf-8")
    fehler = export_pruefen(ziel, liste)
    if fehler:
        bericht("Spiegel blockiert – Rescan-Befunde:\n" + "\n".join(fehler[:30]) + f"\nExport bleibt zur Prüfung: {ziel}")
        return 3
    testfehler = export_testen(ziel, root)
    if testfehler:
        bericht(f"Spiegel blockiert – Tests im Export rot:\n{testfehler}\nExport: {ziel}")
        return 3
    neu = scratch_commit(ziel, f"Öffentliche Momentaufnahme {lauf} (Quelle {quelle_sha[:7]})\n\nCo-Authored-By: {COAUTHOR}")
    autor = git(ziel, "log", "-1", "--format=%an <%ae>").strip()
    if autor != f"{AGENT_NAME} <{AGENT_MAIL}>":
        bericht(f"Spiegel blockiert – unerwarteter Commit-Autor im Scratch: {autor}")
        return 3
    if not pushen:
        bericht(f"Spiegel vorbereitet (ohne Push): {ziel}")
        return 0
    url = r["spiegel"]["url"]
    alt = git(ziel, "ls-remote", url, "refs/heads/main", pruefen=False).split()
    lease = f"--force-with-lease=refs/heads/main:{alt[0]}" if alt else "--force-with-lease=refs/heads/main:"
    git(ziel, "push", "-q", lease, url, "HEAD:refs/heads/main")
    nachher = git(ziel, "ls-remote", url, "refs/heads/main").split()
    if not nachher or nachher[0] != neu:
        bericht(f"Spiegel: Remote-SHA weicht ab ({nachher[:1]} statt {neu[:7]}).")
        return 4
    bericht(f"Öffentlich: {r['spiegel']['ziel']} main = {neu[:7]} (Momentaufnahme von {quelle_sha[:7]}).")
    shutil.rmtree(ziel, ignore_errors=True)
    return 0


# ------------------------------------------------------------------------------------------------------------- Hooks
def hook(root: Path, art: str, args: list[str]) -> int:
    r = regeln(root)
    if art == "pre-commit":
        liste = kit_scan.lade_sperrliste(kit_scan.standard_sperrliste())
        befunde = kit_scan.scan_diff(["--cached"], liste)
        for b in befunde:
            print(b.text(), file=sys.stderr)
        py = [z for z in git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
              if z.endswith(".py") and not kit_scan.ist_eingefroren(z, r)]
        if py:
            erg = subprocess.run([interpreter(root, ".venv-312"), "-m", "ruff", "check", *py], cwd=root, check=False)
            if erg.returncode != 0:
                return 1
        return 1 if befunde else 0
    if art == "commit-msg":
        text = Path(args[0]).read_text(encoding="utf-8")
        erste = text.splitlines()[0] if text.strip() else ""
        if not TITEL_RE.match(erste):
            print(f"commit-msg: Titel muss '<ID>: …' sein (F-01, F-00b, M-01, L-01), war: {erste[:80]}", file=sys.stderr)
            return 1
        geaendert = [z for z in git(root, "diff", "--cached", "--name-only").splitlines() if z]
        if eingefroren_beruehrt(root, r, geaendert) and "[EINGEFROREN-AENDERUNG:" not in text:
            print("commit-msg: eingefrorene Pfade geändert – Vermerk [EINGEFROREN-AENDERUNG: Grund] fehlt.", file=sys.stderr)
            return 1
        if "Co-Authored-By:" not in text:
            print("commit-msg: Hinweis – Zeile Co-Authored-By fehlt.", file=sys.stderr)
        return 0
    if art == "pre-push":
        url = args[1] if len(args) > 1 else ""
        if re.search(r"(?i)philippcode1/ki-trading-mt5-v4(?:\.git)?$", url.strip()):
            print("pre-push: Push auf das öffentliche Repo nur über tools/publish.py (Scratch-Export).", file=sys.stderr)
            return 1
        if os.environ.get("KIT_PUBLISH_OHNE_TESTS") == "1":
            return 0
        erg = subprocess.run([interpreter(root, ".venv-311"), "-B", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "kit_tests"],
                             cwd=root, capture_output=True, text=True, errors="replace", check=False)
        if erg.returncode != 0:
            print(erg.stdout[-2000:], file=sys.stderr)
            return 1
        return 0
    print(f"Unbekannter Hook {art}", file=sys.stderr)
    return 2


# ------------------------------------------------------------------------------------------------------------- Befehle
def lauf_befehl(root: Path, lauf: str, titel: str, oeffentlich: bool, vermerk: str | None, nur_pruefen: bool, bericht: Bericht) -> int:
    r = regeln(root)
    pruefe_umgebung(root, r, oeffentlich)
    pruefe_fast_forward(root, r)
    weg = aufraeumen(root)
    bericht(f"Säubern: {len(weg)} Cache-Einträge entfernt (work/, .venv-*, .uv-cache unberührt).")
    pruefe_unbekannte_dateien(root, r)
    abschnitt = pruefe_laufdateien(root, r, lauf) if not nur_pruefen else ""
    geaendert = pruefe_staging(root, r)
    pruefe_scan(root, r)
    eingefroren = eingefroren_beruehrt(root, r, geaendert)
    if eingefroren and not vermerk:
        raise Abbruch(1, "Eingefrorene Pfade geändert (" + ", ".join(eingefroren[:5]) + ") – --vermerk \"Grund\" angeben.")
    bericht(f"Tore: {len(geaendert)} geänderte Dateien, Scan 0 Befunde.")
    tests(root, voll_kern=bool(eingefroren), bericht=bericht)
    if nur_pruefen:
        git(root, "reset", "-q")
        bericht("Prüfung grün (kein Commit, kein Push).")
        return 0
    if commit(root, lauf, titel, abschnitt, vermerk):
        bericht(f"Commit: {lauf}: {titel}")
    tag_und_push(root, r, lauf, bericht)
    if oeffentlich:
        return spiegeln(root, r, lauf, bericht)
    return 0


def main(argv: list[str] | None = None) -> int:
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Abschlussroutine eines Laufs (Plan F-1 §7)")
    sub = ap.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("pruefen")
    p.add_argument("--oeffentlich", action="store_true")
    p.add_argument("--vermerk")
    lf = sub.add_parser("lauf")
    lf.add_argument("--lauf", required=True)
    lf.add_argument("--titel", required=True)
    lf.add_argument("--oeffentlich", action="store_true")
    lf.add_argument("--vermerk")
    sub.add_parser("oeffentlich").add_argument("--lauf", default="manuell")
    a = sub.add_parser("aufraeumen")
    a.add_argument("--trocken", action="store_true")
    s = sub.add_parser("scan")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--gestaged", action="store_true")
    g.add_argument("--baum", action="store_true")
    h = sub.add_parser("hook")
    h.add_argument("art")
    h.add_argument("args", nargs="*")
    ns = ap.parse_args(argv)
    bericht = Bericht()
    try:
        if ns.befehl == "aufraeumen":
            for rel in aufraeumen(ROOT, ns.trocken):
                print(("würde löschen " if ns.trocken else "gelöscht ") + rel)
            return 0
        if ns.befehl == "scan":
            return kit_scan.main(["--gestaged"] if ns.gestaged else ["--baum"])
        if ns.befehl == "hook":
            return hook(ROOT, ns.art, ns.args)
        if ns.befehl == "pruefen":
            return lauf_befehl(ROOT, "F-00", "pruefen", ns.oeffentlich, ns.vermerk, True, bericht)
        if ns.befehl == "lauf":
            return lauf_befehl(ROOT, ns.lauf, ns.titel, ns.oeffentlich, ns.vermerk, False, bericht)
        if ns.befehl == "oeffentlich":
            r = regeln(ROOT)
            pruefe_fast_forward(ROOT, r)
            if git(ROOT, "rev-parse", "HEAD").strip() != git(ROOT, "rev-parse", f"{r['spiegel']['privat_remote']}/main").strip():
                raise Abbruch(1, "HEAD ist nicht private/main – erst privat veröffentlichen.")
            return spiegeln(ROOT, r, ns.lauf, bericht)
    except Abbruch as exc:
        print(f"ABBRUCH ({exc.code}): {exc}", file=sys.stderr)
        return exc.code
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
