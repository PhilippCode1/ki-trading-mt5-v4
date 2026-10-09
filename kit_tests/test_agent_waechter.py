"""Agent-Wächter (tools/agent_waechter.py): jede Regel aus Plan F-1 §6.4 mit erlaubtem und verweigertem Beispiel."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import agent_waechter as w

ROOT = Path(__file__).resolve().parents[1]
MT5 = "Meta" + "Trader5"


def _bash(cmd: str) -> str | None:
    return w.pruefe({"tool_name": "Bash", "tool_input": {"command": cmd}})


VERWEIGERT = [
    "echo KIT_WAECHTER_PROBE",
    "git push --force private main",
    "git push private main -f",
    "git push private :refs/tags/lauf/F-00",
    "git push private +main",
    "git push private --delete lauf/F-00",
    'git -c user.name="A B" push --force private main',
    "git -c core.hooksPath=/dev/null commit -m x",
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git clean -fdX",
    "git tag -d konzept-c11-gruen",
    "git config core.hooksPath /tmp/leer",
    "git push https://github.com/PhilippCode1/ki-trading-mt5-v4.git HEAD:main",
    "git remote add oeffentlich https://github.com/PhilippCode1/ki-trading-mt5-v4.git",
    "gh repo edit PhilippCode1/ki-trading-mt5-v4-private --visibility public",
    "gh repo delete PhilippCode1/x --yes",
    "gh api -X DELETE repos/PhilippCode1/x",
    "gh api repos/PhilippCode1/x -f name=y",
    "gh gist create notizen.txt",
    "gh secret set X",
    f'python -c "import {MT5}"',
    f'.venv-311/Scripts/python.exe -c "import {MT5} as m; m.initialize()"',
    f"py -3.11 -c \"import {MT5}\"",
    "python -c \"print('order_send')\"",
    ".venv-bot\\Scripts\\python.exe skript.py",
    '.venv-bot\\Scripts\\python.exe -c "print(1)"',
    ".venv-bot\\Scripts\\python.exe -m kit entsperren",
    ".venv-bot\\Scripts\\python.exe -m kit pin-setzen",
    ".venv-bot\\Scripts\\python.exe -m kit live --schreiben",
    "curl http://127.0.0.1:22346/mcp",
    'rm -rf "$LOCALAPPDATA/kit/demo"',
    "Remove-Item $env:LOCALAPPDATA\\kit\\freigaben\\pin.txt",
    "cat %LOCALAPPDATA%\\kit\\sperrliste.txt",
    "type %APPDATA%\\MetaQuotes\\Terminal\\X\\config\\common.ini",
    "echo x > tools/agent_waechter.py",
    "cmd /c del tools\\agent_waechter.py",
    "git apply waechter.diff && git add tools/agent_waechter.py",
    "git checkout konzept-c12-wip -- .claude/settings.json",
    "python -c \"open('.claude/settings.json','w').write('{}')\"",
    "Set-Content config/live_freigabe.json '{}'",
    "pip install requests",
    "uv add numpy",
    "uvx ruff check",
    # Laufzeitablage ab F-03b im Benutzerprofil – jede Schreibweise
    'cat "$HOME/KI-Trading-Bot/probe/journal/2026-10-05.jsonl"',
    "type %USERPROFILE%\\KI-Trading-Bot\\freigaben\\pin.json",
    "type %HOMEDRIVE%%HOMEPATH%\\KI-Trading-Bot\\geheim\\hmac.key",
    "Get-Content $env:USERPROFILE\\KI-Trading-Bot\\demo\\zustand.json",
    "Get-ChildItem -Recurse $env:USERPROFILE\\KI-Trading-Bot",
    "ls ~/KI-Trading-Bot/",
    "dir C:\\Users\\X\\KI-TRA~1\\probe",
    "cat ../../../KI-Trading-Bot/probe/zustand.json",
    "grep -r LOSS_LOCK ~/KI-Trading-Bot/*/journal",
    "rm -rf ~/KI-Trading-Bot/schreiber",
    'cat "C:/Users/X/AppData/Local/Packages/Claude_abc/LocalCache/Local/kit/probe/zustand.json"',
    "dir %LOCALAPPDATA%\\kit",
    # Umgehungen aus dem Review F-03b
    "cat ~/KI-Trading-Bot//probe/zustand.json",
    "cat ~/KI-Trading-Bot/./probe/zustand.json",
    "cat ~/KI-Trading-Bot/export/../geheim/hmac.key",
    "cd ~/KI-Trading-Bot/export && cat ../geheim/hmac.key",
    "type %USERPROFILE%\\KI-Trading-Bot\\FREIGA~1\\pin.json",
    'cat ~/KI-Trading-Bot/p"rob"e/zustand.json',
    "cat ${env:USERPROFILE}/KI-Trading-Bot/UMZUG.json",
    "cat ~/KI-*/probe/zustand.json",
    "cat ~/KI-Trading-Bo[t]/geheim/hmac.key",
    "grep -r LOSS_LOCK ~",
    "rg -n hmac $HOME",
    "Get-ChildItem -Recurse $env:USERPROFILE",
    "dir /s %USERPROFILE%",
    "type \\\\?\\C:\\Users\\X\\Dokumente\\a.txt",
    "dir \\\\localhost\\c$\\Users",
    "echo K3 > ~/KI-Trading-Bot/export/x.json",
    ".venv-bot\\Scripts\\python.exe -m kit sichern --ziel work\\s --mit-schluessel",
    # Umgehungen aus Review-Runde 3
    "cd ~ && cat KI-Tr*/geheim/hmac.key",
    "ls ~/.",
    "cat ~/KI-Trading\\-Bot/probe/zustand.json",
    "D=KI-Trading-Bot; cat ~/$D/probe/zustand.json",
    "Get-Content (Join-Path $env:USERPROFILE ('KI-'+'Trading-Bot'))",
    "type %USERPROFILE%\\KI-Trading-Bot.\\probe\\zustand.json",
    "pushd ~/KI-Trading-Bot",
    "Set-Location $env:USERPROFILE\\KI-Trading-Bot; gc probe\\zustand.json",
    "cd  ~/KI-Trading-Bot/export && cat ../probe/zustand.json",
]
ERLAUBT = [
    "git status --porcelain",
    "git push private main",
    "git push private refs/tags/lauf/F-01",
    "git log --oneline -5",
    "git diff -- tools/agent_waechter.py",
    "git config core.hooksPath .githooks",
    'git -c user.name="KI-Trading v4 Agent" -c user.email=agent@localhost.invalid commit -m "F-01: Titel"',
    "gh api repos/PhilippCode1/mt5-trading-ai/contents/README.md -H \"Accept: application/vnd.github.raw\"",
    "gh api -X GET repos/PhilippCode1/x",
    "gh run list --limit 5",
    "gh auth status",
    f"grep -rn {MT5} kit/",
    ".venv-bot\\Scripts\\python.exe -m kit pruefen",
    ".venv-bot\\Scripts\\python.exe -B -m kit rauchtest",
    ".venv-bot\\Scripts\\python.exe -m pip install -r requirements/bot-runtime.lock.txt",
    "uv pip install --python .venv-bot\\Scripts\\python.exe -r requirements/bot-runtime.lock.txt",
    f"py -3.11 -m pip uninstall -y {MT5}",
    ".venv-311/Scripts/python.exe -m pytest kit_tests/test_agent_waechter.py -q 2>&1 | tail -5",
    ".venv-312/Scripts/python.exe -B tools/kerntests.py --schnell",
    "python tools/publish.py lauf --lauf F-00b --titel x --oeffentlich",
    "cat tools/agent_waechter.py",
    "ls -la kit",
    "cat ~/KI-Trading-Bot/export/tor_t-probe-20261005T210000Z.json",
    ".venv-bot\\Scripts\\python.exe -m kit status --modus probe",
    # Erwähnungen ohne Pfad bleiben frei (Fehlalarme aus dem Review F-03b)
    'git commit -m "F-03b: Laufzeitablage nach KI-Trading-Bot verlegt"',
    "git log --oneline --grep=KI-Trading-Bot",
    'grep -rn "KI-Trading-Bot" kit docs',
    'python tools/publish.py lauf --lauf F-03b --titel "Umzug nach KI-Trading-Bot" --oeffentlich',
    "git fetch https://github.com/PhilippCode1/mt5-trading-ai",
]


@pytest.mark.parametrize("cmd", VERWEIGERT)
def test_verweigert(cmd):
    assert _bash(cmd), f"hätte verweigert werden müssen: {cmd}"


@pytest.mark.parametrize("cmd", ERLAUBT)
def test_erlaubt(cmd):
    assert _bash(cmd) is None, f"fälschlich verweigert: {cmd} -> {_bash(cmd)}"


@pytest.mark.parametrize("werkzeug", ["mcp__terminal__run_in_terminal", "mcp__Claude_Browser__navigate", "mcp__claude-in-chrome__computer",
                                      "RemoteTrigger", "mcp__ccd_session_mgmt__set_session_permission_mode", "UnbekanntesWerkzeug"])
def test_werkzeuge_gesperrt(werkzeug):
    assert w.pruefe({"tool_name": werkzeug, "tool_input": {}})


@pytest.mark.parametrize("werkzeug", ["AskUserQuestion", "TodoWrite", "Agent", "Workflow", "StructuredOutput", "mcp__ccd_session__mark_chapter"])
def test_werkzeuge_erlaubt(werkzeug):
    assert w.pruefe({"tool_name": werkzeug, "tool_input": {}}) is None


def test_dateiregeln():
    meta = "C:/" + "Users/" + "Benutzer/AppData/Roaming/MetaQuotes/Terminal/ABC/config/accounts.dat"
    assert w.pruefe({"tool_name": "Read", "tool_input": {"file_path": meta}})
    ablage = "C:/" + "Users/" + "Benutzer/AppData/Local/kit/demo/zustand.json"
    assert w.pruefe({"tool_name": "Read", "tool_input": {"file_path": ablage}})
    for geschuetzt in ("tools/agent_waechter.py", ".claude/settings.json", ".claude/settings.local.json", "config/live_freigabe.json",
                       ".githooks/pre-push", ".mcp.json"):
        assert w.pruefe({"tool_name": "Write", "tool_input": {"file_path": str(ROOT / geschuetzt), "content": "x"}}), geschuetzt
    assert w.pruefe({"tool_name": "Read", "tool_input": {"file_path": str(ROOT / "tools/agent_waechter.py")}}) is None
    imp = f"import {MT5} as mt5\n"
    assert w.pruefe({"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "kit/eigenes.py"), "content": imp}})
    assert w.pruefe({"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "kit/broker/mt5_real.py"), "content": imp}}) is None
    assert w.pruefe({"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / "kit/x.py"), "old_string": "a", "new_string": imp}})


def _datei(werkzeug: str, **eingabe) -> str | None:
    return w.pruefe({"tool_name": werkzeug, "tool_input": eingabe})


def test_dateiregeln_laufzeitablage_im_benutzerprofil():
    heim = Path.home() / "KI-Trading-Bot"
    fremd = "C:/" + "Users/" + "Benutzer/KI-Trading-Bot"
    for pfad in (f"{fremd}/demo/zustand.json", str(heim / "probe" / "zustand.json"), str(heim / "geheim" / "hmac.key"),
                 str(heim / "app" / "rel_F-03b-2" / "kit" / "cli.py")):
        assert _datei("Read", file_path=pfad), pfad
    assert _datei("Edit", file_path=str(heim / "freigaben" / "demo_konten.json"), old_string="a", new_string="b")
    assert _datei("Write", file_path=str(heim / "probe" / "STOP"), content="0")
    assert _datei("Glob", path=str(heim), pattern="**/*.jsonl")                     # Ablage selbst durchsuchen
    assert _datei("Glob", path=fremd.rsplit("/", 1)[0], pattern="KI-Trading-Bot/**")   # Pfad und Muster nur gemeinsam
    assert _datei("Glob", path=str(Path.home()), pattern="*/probe/*")               # Elternordner + Platzhalter
    assert _datei("Grep", path=str(Path.home()), pattern="LOSS_LOCK")               # Suche über das ganze Profil
    assert _datei("Grep", path=str(heim), pattern="x", glob="*.jsonl")
    assert _datei("LS", path=str(heim))
    try:
        relativ = os.path.relpath(heim / "probe" / "zustand.json", ROOT)
    except ValueError:                                                             # anderes Laufwerk
        relativ = None
    if relativ:
        assert _datei("Read", file_path=relativ)
        assert _datei("Grep", path=os.path.relpath(Path.home(), ROOT), pattern="x")
    assert _datei("Read", file_path=str(heim / "export" / "tor_t-probe.json")) is None   # redigierte Exporte bleiben lesbar
    assert _datei("Glob", path=str(ROOT), pattern="kit/**/*.py") is None
    assert _datei("Glob", pattern="**/*.md") is None
    assert _datei("Grep", path=str(ROOT / "kit"), pattern="Schreibsperre") is None
    assert _datei("Read", file_path=str(ROOT / "kit" / "paths.py")) is None


def test_dateiregeln_umgehungen_aus_dem_review(tmp_path, monkeypatch):
    heim = Path.home() / "KI-Trading-Bot"
    for pfad in ("\\\\?\\" + str(heim / "probe" / "zustand.json"),            # Geräte-Präfix
                 "\\\\localhost\\C$\\Users\\X\\KI-Trading-Bot\\export\\x.json",    # UNC: immer gesperrt
                 str(heim) + "\\export\\..\\probe\\zustand.json",
                 str(heim) + "/./probe/zustand.json",
                 str(heim) + "//geheim//hmac.key",
                 str(heim / "FREIGA~1" / "pin.json"),
                 str(heim / "UMZUG.json")):
        assert _datei("Read", file_path=pfad), pfad
    assert _datei("Edit", file_path=str(heim / "export" / "x.json"), old_string="a", new_string="b")   # export nur lesen
    assert _datei("Read", file_path=str(heim / "export" / "x.json")) is None
    assert _datei("Grep", pattern="KI-Trading-Bot", path=str(ROOT)) is None          # Inhaltsmuster, kein Pfad
    assert _datei("Grep", pattern="AppData/Local/kit") is None
    lokal = tmp_path / "Lokal"
    cache = lokal / "Packages" / "Claude_abc" / "LocalCache" / "Local" / "kit"
    (cache / "probe").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(lokal))
    assert _datei("Read", file_path=str(cache) + "/./probe/zustand.json")
    assert _datei("Read", file_path=str(cache / "backup" / "x.bundle"))
    assert _datei("LS", path=str(lokal / "Packages"))                                # Elternordner der Paketkopie
    assert _datei("Grep", path=str(lokal / "Packages" / "Claude_abc"), pattern="x")
    for werkzeug, eingabe in (("SendUserFile", {"files": [str(heim / "geheim" / "hmac.key")]}),
                              ("ArtifactData", {"action": "update", "file_path": str(heim / "freigaben" / "demo_konten.json")}),
                              ("Artifact", {"asset": True, "file_path": str(heim / "probe" / "zustand.json")}),
                              ("Artifact", {"files": {"a.json": str(heim / "probe" / "zustand.json")}}),
                              ("Artifact", {"files": {"a.json": {"from": str(cache / "probe" / "x")}}})):
        assert w.pruefe({"tool_name": werkzeug, "tool_input": eingabe}), (werkzeug, eingabe)
    assert w.pruefe({"tool_name": "SendUserFile", "tool_input": {"files": [str(ROOT / "HANDOFF.md")]}}) is None


def test_shellpfade_werden_aufgeloest():
    heim = Path.home()
    try:
        relativ = os.path.relpath(heim, ROOT).replace("\\", "/")
    except ValueError:                                                             # anderes Laufwerk
        relativ = None
    if relativ:
        assert _bash(f"cat {relativ}/KI-Tr*/geheim/hmac.key")                       # Platzhalter ohne Ordnernamen
        assert _bash(f"cat {relativ}/KI-TRA~1/probe/zustand.json")
    assert _bash(f"find {heim.parent.as_posix()} -name hmac.key")                   # Suche über einen Vorfahren
    assert _bash(f"ls {heim.anchor.replace(chr(92), '/')}")
    assert _bash("ls *.py") is None and _bash("cat kit/paths.py") is None
    assert _bash("cd kit && ls") is None


def test_artifact_ziel_in_der_ablage_gesperrt(tmp_path):
    heim = Path.home() / "KI-Trading-Bot"
    for ziel in (heim / "probe", heim / "export"):                                 # Schreiben auch nicht nach export/
        assert w.pruefe({"tool_name": "Artifact", "tool_input": {"action": "read", "url": "x", "path": "STOP", "out_dir": str(ziel)}})
    assert w.pruefe({"tool_name": "Artifact", "tool_input": {"action": "read", "url": "x", "path": "a", "out_dir": str(tmp_path)}}) is None


def test_einstellungen_sperren_neue_ablage():
    deny = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["deny"]
    for teil in ("demo", "live", "probe", "freigaben", "marktdaten", "geheim"):
        assert f"Read(~/KI-Trading-Bot/{teil}/**)" in deny
    assert "Edit(~/KI-Trading-Bot/**)" in deny


def _hook(eingabe: bytes) -> int:
    return subprocess.run([sys.executable, "-B", "-I", str(ROOT / "tools" / "agent_waechter.py")], input=eingabe,
                          capture_output=True, check=False, timeout=30).returncode


def test_hook_exitcodes_fail_closed():
    assert _hook(b"kein json") == 2
    assert _hook(b"{}") == 2
    assert _hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo KIT_WAECHTER_PROBE"}}).encode()) == 2
    assert _hook(json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}}).encode()) == 0
    assert _hook(json.dumps({"tool_name": "Read", "tool_input": "kaputt"}).encode()) == 2
