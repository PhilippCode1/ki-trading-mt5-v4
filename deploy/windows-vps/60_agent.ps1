<#
.SYNOPSIS
  Schritt 6 (als Agent-Benutzer kitdev): Claude Code, Entwicklungs-Checkout, Test- und Forschungsumgebungen, Pruefung.
.DESCRIPTION
  - Claude Code ueber den offiziellen Installer (im Profil von kitdev). Anmelden macht der Betreiber selbst ("claude"
    starten, Browser-Anmeldung). Sitzungen immer im Repo-Ordner starten - nur dann greift der Waechter-Hook.
    Claude Code nie unter kitbot oder Administrator.
  - Privates Repo voll klonen (Remote heisst danach "private"). Die Git-Anmeldung im Credential-Manager-Fenster macht
    der Betreiber: Fine-grained-Token nur fuer das private Repo und den oeffentlichen Spiegel (publish.py pusht auf
    beide), Contents: Read and write, Workflows: Read and write (Spiegel enthaelt .github/workflows), Metadata: Read, KEIN
    Administration; gh mit demselben Token (Paste an authentication token, keine Browser-Anmeldung). Das Skript speichert keine Zugangsdaten.
  - .venv-311 (kit_tests) und .venv-312 (Kerntests, ruff) aus requirements/dev.lock.txt mit --require-hashes;
    .venv-forschung (scikit-learn) ueber tools\dev.ps1 forschung aus requirements/forschung.lock.txt (fuehrt dabei die
    Forschungstests aus). .venv-bot nur, wenn auf diesem Benutzer Adaptertests mit dem echten MetaTrader5-Paket noetig
    sind (normal: nein).
  - Hooks aktivieren (core.hooksPath .githooks), Identitaet des Agenten setzen.
  - Ohne -OhneTests: tools\dev.ps1 alles (ruff, kit_tests, Kerntests, Forschungstests, Scan) und
    kit forschung pruefen (muss VERIFIZIERT melden). Scheitert eines davon: Exit 1.
  - Zum Schluss Warnungen, falls die Sperrliste (%LOCALAPPDATA%\kit\sperrliste.txt) oder die angemeldete GitHub CLI
    fehlt. Beides richtet nur der Betreiber ein (docs/INSTALLATION_VPS.md, Abschnitt 6); ohne Sperrliste bricht
    publish.py --oeffentlich ab, ohne gh wird der oeffentliche Spiegel uebersprungen.
  kitdev sieht die Bot-Ablage von kitbot nicht (Profilrechte): kit status und kit tor-t lesen hier nur die eigene, leere
  Ablage. Einen Bot-Stand gibt es nur im Austauschordner (solange das Projekt ruht, laeuft kein Bot).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\60_agent.ps1
  powershell -ExecutionPolicy Bypass -File .\60_agent.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$OhneClaude, [switch]$OhneTests)
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
Assert-Benutzer $k.AgentBenutzer
if (Test-Admin) { throw 'Bitte als normaler Agent-Benutzer ausfuehren, nicht als Administrator.' }
$repo = Join-Path $env:USERPROFILE $k.RepoOrdnerName

if (-not $OhneClaude) {
    Write-Schritt 'Claude Code'
    if (Test-Befehl 'claude') { Write-Ok ((& claude --version) -join ' ') }
    elseif ($PSCmdlet.ShouldProcess('Claude Code', 'offiziellen Installer ausfuehren')) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-RestMethod -Uri 'https://claude.ai/install.ps1' | Invoke-Expression
        Write-Ok 'Claude Code installiert - neue PowerShell oeffnen, "claude" starten und anmelden.'
    }
}

Write-Schritt "Repo $repo"
if (-not (Test-Path (Join-Path $repo '.git')) -and $PSCmdlet.ShouldProcess($k.RepoUrl, "klonen nach $repo")) {
    & git clone $k.RepoUrl $repo
    if ($LASTEXITCODE -ne 0) { throw 'git clone fehlgeschlagen (Anmeldung im Git-Credential-Manager?).' }
}
if ($PSCmdlet.ShouldProcess($repo, 'Hooks und Agent-Identitaet')) {
    & git -C $repo config core.hooksPath .githooks
    & git -C $repo config core.autocrlf false
    & git -C $repo config user.name 'KI-Trading v4 Agent'
    & git -C $repo config user.email 'agent@localhost.invalid'
    if (-not ((& git -C $repo remote) -contains 'private')) { & git -C $repo remote rename origin private }
}

foreach ($v in @(@{ Name = '.venv-311'; Py = $k.PythonBot }, @{ Name = '.venv-312'; Py = $k.PythonDev })) {
    Write-Schritt "$($v.Name) (Python $($v.Py), hash-gesperrt)"
    $py = Join-Path $repo "$($v.Name)\Scripts\python.exe"
    if ($PSCmdlet.ShouldProcess($v.Name, 'anlegen/aktualisieren')) {
        if (-not (Test-Path $py)) { & py "-$($v.Py)" -m venv (Join-Path $repo $v.Name) }
        & $py -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $repo 'requirements\dev.lock.txt')
        if ($LASTEXITCODE -ne 0) { throw "pip install fuer $($v.Name) fehlgeschlagen." }
    }
}

$devPs1 = Join-Path $repo 'tools\dev.ps1'
Write-Schritt '.venv-forschung (Python 3.11, hash-gesperrt, mit Forschungstests)'
$gruen = $true
if ($PSCmdlet.ShouldProcess('.venv-forschung', 'anlegen/aktualisieren (tools\dev.ps1 forschung, fuehrt die Forschungstests immer aus)')) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $devPs1 forschung
    if ($LASTEXITCODE -ne 0) { $gruen = $false; Write-Fehler "tools\dev.ps1 forschung fehlgeschlagen (Exit $LASTEXITCODE)." }
}
if (-not $OhneTests -and $PSCmdlet.ShouldProcess($repo, 'tools\dev.ps1 alles und kit forschung pruefen')) {
    Write-Schritt 'Tests: tools\dev.ps1 alles'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $devPs1 alles
    if ($LASTEXITCODE -ne 0) { $gruen = $false; Write-Fehler "tools\dev.ps1 alles nicht gruen (Exit $LASTEXITCODE)." }
    Write-Schritt 'Versuchsprotokoll: kit forschung pruefen'
    Push-Location $repo
    try {
        & (Join-Path $repo '.venv-311\Scripts\python.exe') -B -m kit forschung pruefen
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    if ($code -ne 0) { $gruen = $false; Write-Fehler "kit forschung pruefen meldet nicht VERIFIZIERT (Exit $code)." }
}

# Nur pruefen, nie anlegen oder lesen: Sperrliste und gh-Anmeldung richtet ausschliesslich der Betreiber ein.
Write-Schritt 'Voraussetzungen fuer die Veroeffentlichung (publish.py)'
$sperrliste = if ($env:KIT_SPERRLISTE) { $env:KIT_SPERRLISTE } else { Join-Path $env:LOCALAPPDATA 'kit\sperrliste.txt' }
if (Test-Path -LiteralPath $sperrliste -PathType Leaf) { Write-Ok 'Sperrliste vorhanden (%LOCALAPPDATA%\kit\sperrliste.txt)' }
else {
    Write-Warnung ('Sperrliste fehlt (%LOCALAPPDATA%\kit\sperrliste.txt). Der Betreiber kopiert sie offline vom Laptop ' +
        '(RDP-Laufwerk oder tailscale file cp, nie Repo oder Cloud). Ohne sie bricht publish.py --oeffentlich ab.')
}
if (-not (Test-Befehl 'gh')) {
    Write-Warnung 'GitHub CLI (gh) fehlt: als Administrator 30_software.ps1 erneut ausfuehren oder von https://cli.github.com installieren, dann "gh auth login".'
} else {
    $ghAngemeldet = & { $ErrorActionPreference = 'Continue'; & gh auth status *> $null; $LASTEXITCODE -eq 0 }
    if ($ghAngemeldet) { Write-Ok 'GitHub CLI angemeldet (gh auth status)' }
    else {
        Write-Warnung ('GitHub CLI nicht angemeldet: der Betreiber fuehrt "gh auth login" aus (Paste an authentication token, Token nur fuer privates Repo ' +
            'und Spiegel, Workflows schreiben, ohne Administration). Ohne Anmeldung wird der oeffentliche Spiegel uebersprungen.')
    }
}

Write-Host ''
if (-not $gruen) { Write-Fehler 'Pruefung nicht gruen - Ausgabe oben ansehen und beheben, erst danach Sitzungen starten.'; exit 1 }
Write-Ok "Agent-Arbeitsplatz fertig. Sitzungen so starten:  cd $repo ; claude"
Write-Host '   Erste Sitzung: Startpruefung laut CLAUDE.md (Waechter-Probe verweigert, git status sauber, HEAD = private/main,'
Write-Host '   tools\dev.ps1 alles gruen, kit forschung pruefen = VERIFIZIERT, gh auth status), dann den Prompt aus NEXT_PROMPT.md.'
