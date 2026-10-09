"""Agent-Wächter: PreToolUse-Hook für Claude Code im v4-Ordner (Plan F-1 §6.4). Nur Standardbibliothek.

Liest das Hook-Ereignis (JSON) von stdin. Erlaubt → Exit 0. Verweigert → Grund auf stderr, Exit 2.
Jede Ausnahme, jedes unlesbare Ereignis → Exit 2 (fail-closed). Der Hook-Befehl in .claude/settings.json hängt
"|| exit 2" an, damit auch ein fehlender Interpreter blockiert. Ein Timeout blockiert in Claude Code nicht – deshalb
stehen alle kritischen Regeln zusätzlich im Code von kit/ (Demo-Wächter, Live-Riegel) und in permissions.deny.

Diese Datei, .claude/settings*.json und .githooks/ ändert nur der Betreiber (der Wächter sperrt sie für den Agenten).
Probe: Ein Befehl mit KIT_WAECHTER_PROBE wird immer verweigert – so prüft jede Sitzung, dass der Hook wirkt.
"""
from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = "KIT_WAECHTER_PROBE"

# ---------------------------------------------------------------------------------------------------- Werkzeuge
ERLAUBTE_WERKZEUGE = {
    "Read", "Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead", "LS",
    "Bash", "PowerShell", "BashOutput", "KillShell", "KillBash", "Monitor",
    "WebFetch", "WebSearch", "TodoWrite", "Task", "Agent", "TaskOutput", "TaskStop", "ToolSearch",
    "AskUserQuestion", "Skill", "SlashCommand", "EnterPlanMode", "ExitPlanMode", "Workflow", "ListAgents", "SendMessage",
    "ReadNotifications", "FetchInboxMessage", "SendUserFile", "PushNotification", "ScheduleWakeup",
    "Artifact", "ArtifactComments", "ArtifactData", "ReportFindings", "StructuredOutput",
    "ListSkills", "SearchSkills", "SuggestSkills", "SearchPlugins", "SuggestPluginInstall", "ListPlugins",
    "EnterWorktree", "ExitWorktree",
}
ERLAUBTE_PRAEFIXE = (
    "mcp__ccd_session__mark_chapter", "mcp__ccd_session__dismiss_task", "mcp__ccd_view__", "mcp__visualize__",
    "mcp__ccd_pr__get_status", "mcp__ccd_connectors__session_connectors_status",
)
# ausdrücklich gesperrt (zur Klarheit der Meldung; alles Unbekannte ist ohnehin gesperrt)
GESPERRTE_PRAEFIXE = (
    "mcp__terminal__", "mcp__Claude_Browser__", "mcp__claude-in-chrome__", "mcp__scheduled-tasks__",
    "mcp__ccd_session_mgmt__", "mcp__ccd_settings", "mcp__ccd_host", "RemoteTrigger", "CronCreate", "CronDelete",
)

# ---------------------------------------------------------------------------------------------------- Pfade
# Laufzeitablage des Bots (nur der Bot selbst schreibt), Freigaben, Rohdaten, Geheimnisse, Sperrliste.
# Ab F-03b: <Benutzerprofil>\KI-Trading-Bot. Erkannt wird schon das Ordnersegment (auch der 8.3-Kurzname KI-TRA~n), damit
# relative Pfade, ~, $HOME, %USERPROFILE% und %HOMEDRIVE%%HOMEPATH% gleich greifen. Bis F-03b: %LOCALAPPDATA%\kit, aus
# paketierten Apps umgeleitet nach ...\Packages\<App>\LocalCache\Local\kit. Unter der Ablage ist nur export/ frei (redigierte
# Exporte, nur lesen); alles andere ist gesperrt – auch 8.3-Unterordner, ".", "//", Platzhalter und export/..
_ALTE_ABLAGE = r"(?:appdata/local|localappdata%?|\$env:localappdata|\$localappdata|\$\{localappdata\}|localcache/local)/kit"
_NEUE_ABLAGE = r"(?:ki-trading-bot|ki-tra~\d+)\.*"                # Windows ignoriert Punkte am Namensende
_KIT_ABLAGE = r"(?:" + _ALTE_ABLAGE + r"|" + _NEUE_ABLAGE + r")"
_ENDE = r"(?=$|[\s;&|)>,])"
GESCHUETZTE_ABLAGE = re.compile(_KIT_ABLAGE + r"/(?!export(?:/|$|[\s;&|)>,]))"     # alles unter der Ablage außer export/
                                r"|" + _KIT_ABLAGE + r"/export/\S*\.\."              # export/../geheim
                                r"|" + _ALTE_ABLAGE + r"/?" + _ENDE +                 # die Ablage selbst (Auflisten, Suchen) –
                                r"|(?<=[/~])" + _NEUE_ABLAGE + r"/?" + _ENDE)        # neue nur im Pfadkontext
EXPORT = re.compile(_KIT_ABLAGE + r"/export")
UNC = re.compile(r"^[\\/]{2}")                               # \\?\, \\.\, \\host\c$: Geräte-, Volume- und UNC-Pfade
UNC_BEFEHL = re.compile(r"(?:^|[\s=(;&|])//(?:[?.]/|[^/\s]+/[a-z]\$)")
# Suchen und Kopien über das ganze Benutzerprofil erreichen die Ablage, ohne sie zu nennen
_HEIM = r"(?:~|\$home|\$\{home\}|%userprofile%|\$env:userprofile|%homedrive%%homepath%|[a-z]:/users/[^/\s]+)"
HEIM_PLATZHALTER = re.compile(r"(?:^|[\s;&|(=])" + _HEIM + r"/[^/\s]*[*?\[{]")
HEIM_ALLEIN = re.compile(r"(?:^|[\s;&|(=])" + _HEIM + r"/?" + _ENDE)
HEIM_VARIABLE = re.compile(r"(?:^|[\s;&|(=])" + _HEIM + r"/[$%]")       # ~/$D/probe: Ordnername aus einer Variablen
PFAD_BAU = re.compile(r"join-path|getfolderpath|path\]::combine")            # PowerShell/.NET setzen Pfade zusammen
HEIM_BEZUG = re.compile(r"userprofile|localappdata|\$home|~")
SUCHVERBEN = {"grep", "egrep", "rg", "ag", "ack", "find", "findstr", "tree", "ls", "dir", "gci", "get-childitem", "select-string",
              "sls", "robocopy", "xcopy", "cp", "copy", "copy-item", "tar", "zip", "7z", "compress-archive", "du"}
NAVIGATIONSVERBEN = {"cd", "pushd", "chdir", "set-location", "push-location", "sl"}
EINZELBEFEHL = re.compile(r"\n|;|&&|\|\||\|")
TOKEN = re.compile(r"[^\s;&|()<>]+")
SUCHWERKZEUGE = {"Glob", "Grep", "LS"}
LESEWERKZEUGE = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
DATEI_SCHLUESSEL = ("file_path", "file_paths", "files", "root", "path", "paths", "notebook_path")
ZIEL_SCHLUESSEL = ("out_dir",)                               # Werkzeuge, die dorthin schreiben (Artifact read)
METAQUOTES = re.compile(r"(?:appdata/roaming|appdata%?|\$env:appdata|\$appdata)/metaquotes|/metaquotes/terminal|accounts\.dat|"
                        r"assistant\.ini|common\.ini")
# Dateien, die nur der Betreiber ändert
BETREIBER_DATEIEN = re.compile(r"(?:^|/)(?:tools/agent_waechter\.py|\.claude/settings(?:\.local)?\.json|\.githooks/[^/]+|"
                               r"config/live_freigabe\.json|\.mcp\.json|\.claude\.json)$")
HOME_CLAUDE_SETTINGS = re.compile(r"/\.claude/settings[^/]*\.json$|/\.claude\.json$")
# nach dem ersten Commit unveränderliche Schwellen-/Protokolldateien
EINGEFROREN_NACH_COMMIT = ("config/tore.toml", "config/trade_test.toml", "config/demo_live.toml", "config/tor_p_schwellen.json")
NUR_ANHAENGEN = ("forschung/versuchsprotokoll.jsonl",)
# MT5-Import nur im Adapter (und in Tests/Stubs)
MT5_IMPORT = re.compile(r"(?m)^\s*(?:import\s+MetaTrader5|from\s+MetaTrader5\s+import)|import_module\(\s*[\"']MetaTrader5|"
                        r"__import__\(\s*[\"']MetaTrader5")
MT5_IMPORT_ERLAUBT = ("kit/broker/mt5_real.py",)

# ---------------------------------------------------------------------------------------------------- Befehle
MT5_WORTE = re.compile(r"(?i)metatrader5|order_send|order_check|\b2234[56]\b")
PYTHON_AUFRUF = re.compile(r"(?i)(?:^|[\s;&|(\"'/\\])(?:py|python[0-9.]*|pythonw)(?:\.exe)?(?=[\s\"']|$)|\buv\s+run\b|\buvx\b|"
                           r"\bpip[0-9.]*(?:\.exe)?\s")
VENV_BOT = re.compile(r"(?i)\.venv-bot[\\/]+scripts[\\/]+python(?:w)?(?:\.exe)?[\"']?\s+((?:-[BIEsSuOq]\s+|-[WX]\s*\S+\s+)*)(.*)")
KIT_VERBOTEN = re.compile(r"(?i)(?:-m\s+kit|kit[\\/.]cli(?:\.py)?)\b[^\n;&|]*\b(entsperren|freigeben|pin-setzen|live|sichern)\b")
SCHREIB_HART = re.compile(r"(?i)(?:(?<![\d&-])>{1,2}(?![&=])|\brm\b|\bdel\b|\berase\b|remove-item|\bmv\b|\bmove\b|move-item|\bcp\b|"
                          r"\bcopy\b|copy-item|set-content|out-file|add-content|new-item|rename-item|\btee\b|sed\s+-i|perl\s+-i|"
                          r"git\s+(?:checkout|restore|apply|am|mv|rm|stash|reset|update-index))")
SCHREIB_WEICH = re.compile(r"(?i)\bpython|(?:^|[\s;&|(\"'/\\])py(?:\.exe)?\s|\becho\b|\bprintf\b|\bpowershell\b|\bpwsh\b|\bcmd\b")
BETREIBER_NAMEN = re.compile(r"(?i)agent_waechter|\.claude[\\/]+settings|\.githooks|live_freigabe\.json|\.mcp\.json|\.claude\.json|"
                             r"claude\s+mcp\s+add")
GH_AUFRUF = re.compile(r"(?i)(?:^|[\s;&|(])gh(?:\.exe)?\s+(\S+)(?:\s+(\S+))?([^\n;&|]*)")
GIT_AUFRUF = re.compile(r"(?i)(?:^|[\s;&|(])git(?:\.exe)?\s+((?:-c\s+\S+\s+|-C\s+\S+\s+|--\S+\s+)*)(\S+)([^\n;&|]*)")
OEFFENTLICHE_URL = re.compile(r"(?i)github\.com[/:]philippcode1/ki-trading-mt5-v4(?:\.git)?(?![\w-])")
PIP_INSTALL = re.compile(r"(?i)\b(?:pip[0-9.]*|uv\s+pip)\s+(install|sync|uninstall|compile)\b([^\n;&|]*)")


def _norm_pfad(p: str) -> str:
    return p.replace("\\", "/").lower()


def _git_verfolgt(rel: str) -> bool:
    erg = subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True, check=False, timeout=8)
    return erg.returncode == 0


def _rel(pfad: str) -> str | None:
    try:
        p = Path(pfad)
        if not p.is_absolute():
            p = ROOT / p
        return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def _norm_befehl(text: str) -> str:
    """Für den Ablage-Abgleich: \\ → /, klein, Quoting entfernt, ${env:x} → $env:x, "/./" und "//" zusammengefasst."""
    n = re.sub(r"[\"'`]", "", _norm_pfad(text))
    n = re.sub(r"\$\{env:([a-z_]+)\}", r"$env:\1", n)
    while "/./" in n:
        n = n.replace("/./", "/")
    return re.sub(r"(?<!:)//+", "/", n)


def _ablage_wurzeln() -> tuple[Path, ...]:
    return _wurzeln(str(Path.home()), os.environ.get("LOCALAPPDATA") or "")


@functools.lru_cache(maxsize=4)
def _wurzeln(profil: str, lokal: str) -> tuple[Path, ...]:
    wurzeln = [Path(profil) / "KI-Trading-Bot"]
    if lokal:
        wurzeln.append(Path(lokal) / "kit")
        try:
            wurzeln += sorted((Path(lokal) / "Packages").glob("*/LocalCache/Local/kit"))
        except OSError:
            pass
    return tuple(w.resolve() for w in wurzeln)


def _pfad_gesperrt(pfad: str, *, suche: bool, schreiben: bool) -> bool:
    """Pfad zeigt in die Laufzeitablage (außer lesend in export/) – geprüft am Text und am aufgelösten Pfad (relativ zum Repo;
    ~ und Umgebungsvariablen erweitert; 8.3-Namen, ".", ".." aufgelöst). Bei Such-/Listenwerkzeugen auch jeder Elternordner.
    UNC-, Geräte- und Volume-Pfade sind immer gesperrt (fail-closed)."""
    roh = str(pfad).strip()
    if not roh:
        return False
    if UNC.match(roh) or GESCHUETZTE_ABLAGE.search(_norm_befehl(roh)):
        return True
    p = Path(os.path.expandvars(os.path.expanduser(roh)))
    r = (p if p.is_absolute() else ROOT / p).resolve()
    if GESCHUETZTE_ABLAGE.search(_norm_pfad(str(r))):
        return True
    for w in _ablage_wurzeln():
        if r == w or w in r.parents:
            teile = r.relative_to(w).parts
            if schreiben or not teile or teile[0].lower() != "export":
                return True
        elif suche and r in w.parents:
            return True
    return False


def _dateiparameter(eingabe: dict, schluessel: tuple[str, ...] = DATEI_SCHLUESSEL) -> list[str]:
    """Alle Pfadangaben eines Werkzeugs (auch SendUserFile, Artifact, ArtifactData): Zeichenketten, Listen, Zuordnungen."""
    werte: list[str] = []
    for k in schluessel:
        v = eingabe.get(k)
        eintraege = v.values() if isinstance(v, dict) else v if isinstance(v, list) else [v]
        for e in eintraege:
            if isinstance(e, dict):
                e = e.get("from") or e.get("path")
            if isinstance(e, str) and e.strip():
                werte.append(e)
    return werte


def _pfad_tokens(befehl: str) -> list[str]:
    """Pfadartige Argumente eines Shell-Befehls (ohne Quoting, Optionen und URLs) in ihren Lesarten: Backslash als Trenner
    (Windows) und als Escape (Bash); $env:X erweitert; Git-Bash-Laufwerk /c/ → C:/; Punkte am Segmentende entfernt."""
    aus: list[str] = []
    for t in TOKEN.findall(re.sub(r"[\"'`]", "", befehl)):
        if "=" in t:
            t = t.split("=", 1)[1]                       # --ziel=x, VAR=x
        if not t or t.startswith("-") or re.match(r"(?i)^[a-z][a-z0-9+.-]*://|^//?[a-z?]{2,12}$", t):   # URL, cmd-Option //FI
            continue
        if not re.search(r"[/\\~$%]", t) and t not in (".", ".."):
            continue
        for v in {t, re.sub(r"\\(.)", r"\1", t)}:
            v = re.sub(r"(?i)\$env:([a-z_]+)", lambda m: os.environ.get(m.group(1).upper(), m.group(0)), v)
            v = re.sub(r"^/([a-zA-Z])(?=/|$)", r"\1:", v)
            aus.append(re.sub(r"(?<=[^/\\.])\.+(?=[/\\]|$)", "", v))
    return aus


def _verb(einzel: str) -> str:
    """Befehlsname eines Einzelbefehls (ohne vorangestellte VAR=wert, ohne Pfad), klein."""
    for t in re.sub(r"[\"'`(]", " ", einzel).split():
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            return re.split(r"[/\\]", t.lower())[-1].removesuffix(".exe")
    return ""


def _befehl_pfad_gesperrt(befehl: str) -> str | None:
    """Je Einzelbefehl die Argumente aufgelöst prüfen (relativ zum Repo, Variablen, 8.3, ..):
    - jedes Argument, das in die Ablage zeigt (außer lesend export/);
    - bei Such-/Listen-/Kopierbefehlen und Ordnerwechseln auch jeder Elternordner der Ablage;
    - Platzhalter-Argumente über ihren festen Anfang (ist der ein Elternordner, wird gesperrt)."""
    for einzel in EINZELBEFEHL.split(befehl):
        verb = _verb(einzel)
        if verb in NAVIGATIONSVERBEN and re.search(_KIT_ABLAGE, _norm_befehl(einzel)):
            return "Ordnerwechsel in die Laufzeitablage ist gesperrt – nur über die kit-CLI."
        suche = verb in SUCHVERBEN or verb in NAVIGATIONSVERBEN
        if suche and HEIM_ALLEIN.search(_norm_befehl(einzel)):
            return "Suchen, Auflisten und Kopieren über das ganze Benutzerprofil sind gesperrt (erreicht die Laufzeitablage)."
        for t in _pfad_tokens(einzel):
            platzhalter = bool(re.search(r"[*?\[{]", t))
            basis = _glob_basis("", t) if platzhalter else t
            if UNC.match(basis) or not (re.search(r"[A-Za-z0-9~]|\.\.", basis) or (suche and basis == "/")):
                continue                                 # Regex-/Code-Bruchstücke wie \\s, \[ oder /*; UNC prüft UNC_BEFEHL
            try:
                if _pfad_gesperrt(basis, suche=suche or platzhalter, schreiben=False):
                    return "Befehl zeigt (aufgelöst) in die Laufzeitablage oder durchsucht einen Elternordner von ihr – nur über die kit-CLI."
            except (OSError, ValueError, RuntimeError):
                continue                                 # unauflösbar: bleibt bei der Textprüfung
    return None


def _glob_basis(pfad: str, muster: str) -> str:
    """Fester Anfang eines Glob-Ausdrucks (bis zum ersten Platzhalter) als Verzeichnis."""
    voll = muster if not pfad or Path(muster).is_absolute() else pfad.rstrip("/\\") + "/" + muster
    fest = re.split(r"[*?\[{]", voll, maxsplit=1)[0]
    return fest if fest.endswith(("/", "\\")) or fest == voll else os.path.dirname(fest) or "."


def pruefe_datei(werkzeug: str, eingabe: dict) -> str | None:
    pfad = eingabe.get("file_path") or eingabe.get("notebook_path") or eingabe.get("path") or ""
    roh = _norm_pfad(str(pfad))
    lesend = werkzeug in LESEWERKZEUGE
    if _pfad_gesperrt(str(pfad), suche=werkzeug in SUCHWERKZEUGE, schreiben=not lesend):
        return "Zugriff auf die Laufzeitablage/Freigaben/Rohdaten/Sperrliste des Bots ist dem Agenten gesperrt (nur über die kit-CLI)."
    if METAQUOTES.search(roh):
        return "Zugriff auf MetaQuotes-Terminaldaten (Konten, Schlüssel, Einstellungen) ist dem Agenten gesperrt."
    if lesend:                                           # Grep-„pattern“ ist ein Inhaltsmuster, kein Pfad
        texte = [str(eingabe.get("glob") or "")]
        if werkzeug == "Glob":                           # Pfad und Muster gemeinsam: path=<Profil>, pattern=KI-Trading-Bot/**
            muster = str(eingabe.get("pattern") or "")
            if UNC.match(muster.strip()) or _pfad_gesperrt(_glob_basis(str(pfad), muster), suche=True, schreiben=False):
                return "Suchmuster zeigt in gesperrte Ablagen."
            texte += [muster, roh.rstrip("/") + "/" + _norm_pfad(muster)]
        if any(t and (GESCHUETZTE_ABLAGE.search(_norm_befehl(t)) or METAQUOTES.search(_norm_pfad(t))) for t in texte):
            return "Suchmuster zeigt in gesperrte Ablagen."
        return None
    # schreibende Werkzeuge
    if HOME_CLAUDE_SETTINGS.search(roh) and "/projects/" not in roh:
        return "Claude-Einstellungen ändert nur der Betreiber."
    rel = _rel(str(pfad))
    if rel is not None:
        if BETREIBER_DATEIEN.search("/" + rel) or BETREIBER_DATEIEN.search(rel):
            return f"{rel} ändert nur der Betreiber (Wächter, Hooks, Einstellungen, Live-Freigabe)."
        if rel in EINGEFROREN_NACH_COMMIT and _git_verfolgt(rel):
            return f"{rel} ist eingefroren (bereits committet); Änderung nur durch den Betreiber als neuer Versuch."
        if rel in NUR_ANHAENGEN and (ROOT / rel).exists():
            return f"{rel} ist nur anhängbar – Einträge nur über die kit-CLI."
        inhalt = str(eingabe.get("content") or "") + str(eingabe.get("new_string") or "") + str(eingabe.get("new_source") or "")
        for e in eingabe.get("edits") or []:
            inhalt += str(e.get("new_string") or "")
        if MT5_IMPORT.search(inhalt) and rel not in MT5_IMPORT_ERLAUBT and not rel.startswith(("kit_tests/", "stubs/")):
            return "MetaTrader5 darf nur in kit/broker/mt5_real.py importiert werden (keine eigenen MT5-Skripte)."
    elif MT5_IMPORT.search(str(eingabe.get("content") or "") + str(eingabe.get("new_string") or "")):
        return "Dateien mit MetaTrader5-Import außerhalb des Repos sind gesperrt (keine eigenen MT5-Skripte)."
    return None


def _venv_bot_ok(befehl: str) -> str | None:
    for m in VENV_BOT.finditer(befehl):
        davor = befehl[:m.start()].rstrip().lower()
        if davor.endswith(("--python", "-p")):
            continue                                         # uv pip ... --python .venv-bot\Scripts\python.exe
        rest = m.group(2).strip().strip("\"'")
        if re.match(r"(?i)-m\s+(kit|pytest)\b", rest):
            continue
        if re.match(r"(?i)-m\s+pip\s+(install|uninstall|list|show|freeze|check)\b", rest):
            continue
        if re.match(r"(?i)--version\b", rest):
            continue
        return "Die Bot-Umgebung .venv-bot darf nur mit -m kit, -m pytest oder -m pip (gesperrte Pakete) aufgerufen werden."
    return None


def pruefe_befehl(befehl: str) -> str | None:
    if PROBE in befehl:
        return f"{PROBE}: Wächter aktiv – Probe korrekt verweigert."
    n = _norm_pfad(befehl)
    k = _norm_befehl(befehl)
    if UNC_BEFEHL.search(re.sub(r"[\"'`]", "", n)):
        return "UNC-, Geräte- und Volume-Pfade sind für den Agenten gesperrt."
    if GESCHUETZTE_ABLAGE.search(k) or (EXPORT.search(k) and (".." in k or SCHREIB_HART.search(befehl))):
        return "Befehl berührt die Laufzeitablage/Freigaben/Rohdaten/Sperrliste des Bots – nur über die kit-CLI."
    if HEIM_PLATZHALTER.search(k) or HEIM_VARIABLE.search(k) or (PFAD_BAU.search(k) and HEIM_BEZUG.search(k)):
        return "Suchen, Auflisten und Kopieren über das ganze Benutzerprofil sind gesperrt (erreicht die Laufzeitablage)."
    grund = _befehl_pfad_gesperrt(befehl)
    if grund:
        return grund
    if METAQUOTES.search(n):
        return "Befehl berührt MetaQuotes-Terminaldaten (Konten, Schlüssel, Einstellungen) – gesperrt."
    if KIT_VERBOTEN.search(befehl):
        return "kit entsperren/freigeben/pin-setzen/live/sichern darf nur der Betreiber in seiner eigenen Konsole ausführen."
    if BETREIBER_NAMEN.search(befehl) and (SCHREIB_HART.search(befehl)
                                           or (SCHREIB_WEICH.search(befehl) and not re.search(r"(?i)-m\s+pytest\b", befehl))):
        return "Wächter, Hooks, Claude-Einstellungen und Live-Freigabe ändert nur der Betreiber."
    if re.search(r"(?i)\bgit\b", befehl):
        if "--no-verify" in befehl:
            return "Hooks dürfen nicht umgangen werden (--no-verify)."
        if re.search(r"(?i)\bpush\b[^\n;&|]*(?:\s-f\b|--force|--delete|--mirror|--prune|\s-d\b|\s:\S|\s\+\S)", befehl):
            return "git push nur als normaler Fast-Forward-Push (kein force/delete/mirror/prune/Lösch-Refspec)."
        if re.search(r"(?i)\bgit\b[^\n;&|]*\sclean\b", befehl):
            return "git clean ist gesperrt (löscht ignorierte Daten wie work/ unwiderruflich)."
    grund = _venv_bot_ok(befehl)
    if grund:
        return grund
    if MT5_WORTE.search(befehl):
        pip = PIP_INSTALL.search(befehl)
        erlaubt_pip = pip and (
            (pip.group(1).lower() == "uninstall" and re.search(r"(?i)\bmetatrader5\b", pip.group(2)))
            or re.search(r"(?i)-r\s+\S*requirements[\\/][\w.-]+\.lock\.txt", pip.group(2))
            or (pip.group(1).lower() == "compile" and "--generate-hashes" in pip.group(2))
        )
        nur_venv_bot_kit = bool(VENV_BOT.search(befehl)) and not PYTHON_AUFRUF.search(VENV_BOT.sub("", befehl))
        if not (erlaubt_pip or nur_venv_bot_kit) and PYTHON_AUFRUF.search(befehl):
            return "MetaTrader5/order_send/order_check/MCP-Ports nur über die kit-CLI aus .venv-bot (keine eigenen MT5-Skripte)."
        if re.search(r"\b2234[56]\b", befehl):
            return "Die MT5-KI/MCP-Ports 22345/22346 sind für den Agenten gesperrt."
    for m in GH_AUFRUF.finditer(befehl):
        grund = _gh_ok(m.group(1).lower(), (m.group(2) or "").lower(), m.group(3) or "")
        if grund:
            return grund
    for m in GIT_AUFRUF.finditer(befehl):
        grund = _git_ok(m.group(1) or "", m.group(2).lower(), m.group(3) or "", befehl)
        if grund:
            return grund
    if OEFFENTLICHE_URL.search(befehl) and not re.search(r"(?i)tools[\\/]publish\.py", befehl):
        return "Die öffentliche Spiegel-URL nutzt nur tools/publish.py."
    pip = PIP_INSTALL.search(befehl)
    if pip and pip.group(1).lower() in {"install", "sync"} and \
            not re.search(r"(?i)(?:-r\s+|\s)\S*requirements[\\/][\w.-]+\.lock\.txt", pip.group(2)):
        return "Pakete nur hash-gesperrt aus requirements/*.lock.txt installieren (Plan §6.9)."
    if re.search(r"(?i)\buv\s+(?:add|tool)\b|\buvx\b|\buv\s+run\s+[^\n;&|]*--with\b|\bpipx\b", befehl):
        return "uv add/uvx/uv run --with/pipx sind gesperrt (nur hash-gesperrte Locks)."
    return None


def _gh_ok(sub: str, sub2: str, rest: str) -> str | None:
    if sub == "api":
        if re.search(r"(?i)(?:^|\s)(?:-X|--method)\s*(?!get\b)\w+", " " + sub2 + rest) or \
           re.search(r"(?:^|\s)(?:-f|-F|--field|--raw-field|--input)(?:\s|=|$)", " " + sub2 + rest):
            return "gh api nur lesend (GET ohne Felder)."
        return None
    erlaubt = {("run", "list"), ("run", "view"), ("run", "watch"), ("auth", "status"), ("repo", "view"), ("pr", "view"),
               ("pr", "list"), ("pr", "status"), ("pr", "checks"), ("issue", "view"), ("issue", "list"), ("release", "view"),
               ("release", "list"), ("repo", "list"), ("workflow", "list"), ("workflow", "view"), ("search", "repos"), ("search", "code"),
               ("--version", "")}
    if (sub, sub2) in erlaubt or sub == "--version" or sub == "help":
        return None
    return f"gh {sub} {sub2} ist für den Agenten gesperrt (nur lesende gh-Befehle; Sichtbarkeit/Einstellungen ändert der Betreiber)."


def _git_ok(optionen: str, sub: str, rest: str, befehl: str) -> str | None:
    alles = f" {optionen} {sub} {rest} "
    if re.search(r"(?i)-c\s+core\.hookspath", optionen) or "--no-verify" in alles:
        return "Hooks dürfen nicht umgangen werden (--no-verify / -c core.hooksPath)."
    if sub == "config" and re.search(r"(?i)core\.hookspath", rest):
        if re.fullmatch(r"(?i)\s*(?:--local\s+)?core\.hookspath\s+\.githooks\s*", rest):
            return None
        return "core.hooksPath darf nur auf .githooks gesetzt werden."
    if sub == "commit" and re.search(r"(?:^|\s)-n(?:\s|$)", rest):
        return "git commit -n (ohne Hooks) ist gesperrt."
    if sub == "push":
        if re.search(r"(?:^|\s)(?:-f|--force(?:-with-lease)?(?:=\S*)?|--force-if-includes|--delete|-d|--mirror|--prune|--all)(?:\s|$)",
                     rest):
            return "git push nur als normaler Fast-Forward-Push (kein force/delete/mirror/prune)."
        for ref in rest.split():
            if ref.startswith((":", "+")):
                return "git push mit Lösch- oder Zwangs-Refspec ist gesperrt."
        if OEFFENTLICHE_URL.search(rest):
            return "Der öffentliche Spiegel wird nur über tools/publish.py aktualisiert."
    if sub == "clean":
        return "git clean ist gesperrt (löscht ignorierte Daten wie work/ unwiderruflich)."
    if sub == "tag" and re.search(r"(?:^|\s)(?:-d|--delete|-f|--force)(?:\s|$)", rest):
        return "Tags dürfen nicht gelöscht oder überschrieben werden."
    if sub in {"filter-branch", "filter-repo", "replace"} or (sub == "reflog" and "expire" in rest) or \
            (sub == "gc" and "--prune=now" in rest):
        return "Historie umschreibende/vernichtende git-Befehle sind gesperrt."
    if sub == "remote" and OEFFENTLICHE_URL.search(rest):
        return "Die öffentliche URL darf nicht als Remote eingetragen werden."
    return None


def pruefe(ereignis: dict) -> str | None:
    werkzeug = str(ereignis.get("tool_name") or "")
    eingabe = ereignis.get("tool_input") or {}
    if not isinstance(eingabe, dict):
        return "Unlesbare Werkzeugeingabe."
    if werkzeug.startswith(GESPERRTE_PRAEFIXE):
        return f"Werkzeug {werkzeug} ist in diesem Projekt gesperrt (Terminal/Browser/Planung/Remote/Sitzungsverwaltung)."
    if werkzeug not in ERLAUBTE_WERKZEUGE and not werkzeug.startswith(ERLAUBTE_PRAEFIXE):
        return f"Werkzeug {werkzeug} steht nicht in der Allowlist des Wächters (tools/agent_waechter.py; freischalten nur Betreiber)."
    if werkzeug in {"Bash", "PowerShell", "Monitor"}:
        befehl = str(eingabe.get("command") or "")
        return pruefe_befehl(befehl)
    if werkzeug in {"Read", "Glob", "Grep", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead", "LS"}:
        return pruefe_datei(werkzeug, eingabe)
    for pfad, schreiben in [(p, False) for p in _dateiparameter(eingabe)] + [(p, True) for p in _dateiparameter(eingabe, ZIEL_SCHLUESSEL)]:
        if _pfad_gesperrt(pfad, suche=False, schreiben=schreiben) or METAQUOTES.search(_norm_pfad(pfad)):
            return f"Werkzeug {werkzeug}: Dateiangabe zeigt in die Laufzeitablage oder MetaQuotes-Daten – gesperrt."
    return None


def main() -> int:
    try:
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        roh = sys.stdin.buffer.read().decode("utf-8")
        ereignis = json.loads(roh) if roh.strip() else {}
        if not isinstance(ereignis, dict) or "tool_name" not in ereignis:
            print("Agent-Wächter: unlesbares Hook-Ereignis – verweigert (fail-closed).", file=sys.stderr)
            return 2
        grund = pruefe(ereignis)
        if grund:
            print(f"Agent-Wächter: {grund}", file=sys.stderr)
            return 2
        return 0
    except Exception as exc:  # noqa: BLE001 - fail-closed
        print(f"Agent-Wächter: interner Fehler ({type(exc).__name__}) – verweigert (fail-closed).", file=sys.stderr)
        return 2


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
