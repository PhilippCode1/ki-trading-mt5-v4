<#
.SYNOPSIS
  Schritt 3 (Administrator): Software fuer alle Benutzer installieren.
.DESCRIPTION
  Git, GitHub CLI (gh, fuer tools/publish.py: Pruefung des oeffentlichen Spiegels), Python 3.11 (Bot) und 3.12
  (Entwicklung) mit py-Launcher, Tailscale (Fernzugriff ohne offenes RDP), optional Docker Desktop. Bevorzugt winget;
  ohne winget (z. B. Windows Server 2022) werden die offiziellen Installer per HTTPS geladen und ihre
  Authenticode-Signatur gegen den Herausgeber geprueft. Scheitert nur die GitHub CLI, gibt es eine Warnung mit dem
  Hinweis auf die Installation von Hand (https://cli.github.com); der Rest laeuft weiter.
  MetaTrader 5 wird geladen und interaktiv installiert (Zielordner aus der Konfiguration waehlen) - nur fuer den Bot.
  Solange das Projekt ruht (nur Entwicklung): mit -OhneMt5 aufrufen.
  Claude Code installiert 60_agent.ps1 im Profil des Agent-Benutzers. Anmeldungen (gh auth login, Git) macht nur der
  Betreiber selbst als Agent-Benutzer; dieses Skript speichert keine Zugangsdaten.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\30_software.ps1 -OhneMt5
  powershell -ExecutionPolicy Bypass -File .\30_software.ps1
  powershell -ExecutionPolicy Bypass -File .\30_software.ps1 -OhneMt5 -Docker
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$OhneMt5, [switch]$Docker, [switch]$OhneTailscale)
. "$PSScriptRoot\_gemeinsam.ps1"
Assert-Admin
$k = Get-VpsKonfig
$tmp = Join-Path $env:TEMP 'ki-trading-setup'
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
$winget = Test-Befehl 'winget'

function Install-Paket {
    param([string]$Name, [string]$WingetId, [scriptblock]$Ersatz, [scriptblock]$Vorhanden)
    Write-Schritt $Name
    if (& $Vorhanden) { Write-Ok "$Name ist installiert"; return }
    if (-not $PSCmdlet.ShouldProcess($Name, 'installieren')) { return }
    if ($winget -and $WingetId) {
        & winget install --id $WingetId --exact --silent --accept-package-agreements --accept-source-agreements --scope machine
        if ($LASTEXITCODE -ne 0) { throw "winget $WingetId fehlgeschlagen (Exit $LASTEXITCODE)" }
    } else {
        & $Ersatz
    }
    Write-Ok "$Name installiert"
}

Install-Paket -Name 'Git' -WingetId 'Git.Git' -Vorhanden { Test-Befehl 'git' } -Ersatz {
    $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest' -UseBasicParsing
    $asset = $rel.assets | Where-Object { $_.name -match '^Git-[\d.]+-64-bit\.exe$' } | Select-Object -First 1
    $datei = Join-Path $tmp $asset.name
    Invoke-Download -Url $asset.browser_download_url -Ziel $datei -Herausgeber 'Johannes Schindelin'
    Start-Process -FilePath $datei -ArgumentList '/VERYSILENT', '/NORESTART', '/NOCANCEL', '/SP-' -Wait
}

# GitHub CLI: publish.py prueft das Spiegelziel mit "gh api". Fehlschlag nur als Warnung (Installation von Hand moeglich).
try {
    Install-Paket -Name 'GitHub CLI' -WingetId 'GitHub.cli' -Vorhanden { Test-Befehl 'gh' } -Ersatz {
        $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/cli/cli/releases/latest' -UseBasicParsing
        $asset = $rel.assets | Where-Object { $_.name -match '^gh_[\d.]+_windows_amd64\.msi$' } | Select-Object -First 1
        if (-not $asset) { throw 'Kein MSI fuer windows_amd64 im letzten Release gefunden.' }
        $datei = Join-Path $tmp $asset.name
        Invoke-Download -Url $asset.browser_download_url -Ziel $datei -Herausgeber 'GitHub'
        $p = Start-Process -FilePath 'msiexec.exe' -ArgumentList '/i', "`"$datei`"", '/qn', '/norestart' -Wait -PassThru
        if ($p.ExitCode -notin @(0, 3010)) { throw "msiexec fuer GitHub CLI fehlgeschlagen (Exit $($p.ExitCode))." }
    }
    Write-Host '   Danach als Agent-Benutzer (nur Betreiber, neue PowerShell): "gh auth login" -> "Paste an authentication token" (keine'
    Write-Host '   Browser-Anmeldung) mit einem Fine-grained-Token nur fuer das private Repo und den oeffentlichen Spiegel'
    Write-Host '   (Contents: Read and write, Workflows: Read and write, Metadata: Read, KEIN Administration).'
} catch {
    Write-Warnung "GitHub CLI nicht installiert ($($_.Exception.Message)). Von Hand installieren: https://cli.github.com (MSI, signiert von GitHub)."
}

# Python: 3.11.9 und 3.12.10 sind die letzten Versionen mit Windows-Installer ihrer Reihe.
$pythons = @{ '3.11' = '3.11.9'; '3.12' = '3.12.10' }
foreach ($reihe in $k.PythonBot, $k.PythonDev) {
    $voll = $pythons[$reihe]
    Install-Paket -Name "Python $reihe" -WingetId "Python.Python.$reihe" -Vorhanden {
        (Test-Befehl 'py') -and (((& py -0p 2>&1) -join ' ') -match "-V:$reihe|-$reihe")
    } -Ersatz {
        $datei = Join-Path $tmp "python-$voll-amd64.exe"
        Invoke-Download -Url "https://www.python.org/ftp/python/$voll/python-$voll-amd64.exe" -Ziel $datei -Herausgeber 'Python Software Foundation'
        Start-Process -FilePath $datei -ArgumentList '/quiet', 'InstallAllUsers=1', 'PrependPath=0', 'Include_launcher=1',
            'InstallLauncherAllUsers=1', 'Include_test=0', 'Shortcuts=0' -Wait
    }
}

if (-not $OhneTailscale) {
    Install-Paket -Name 'Tailscale' -WingetId 'Tailscale.Tailscale' -Vorhanden { Test-Befehl 'tailscale' } -Ersatz {
        $datei = Join-Path $tmp 'tailscale-setup-latest-amd64.msi'
        Invoke-Download -Url 'https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi' -Ziel $datei -Herausgeber 'Tailscale'
        Start-Process -FilePath 'msiexec.exe' -ArgumentList '/i', "`"$datei`"", '/qn' -Wait
    }
    Write-Host '   Danach als Betreiber: "tailscale up" ausfuehren und im Browser am eigenen Tailscale-Konto bestaetigen.'
}

if ($Docker -or $k.Docker) {
    Write-Schritt 'Docker (optional)'
    $virt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
    if (-not $virt) {
        Write-Warnung 'Keine Virtualisierung in der VM - Docker Desktop/WSL2 laeuft hier nicht. Zusatzdienste auf einem Linux-Server betreiben (docs/VPS_IDEEN.md).'
    } elseif ($PSCmdlet.ShouldProcess('Docker Desktop', 'WSL2 aktivieren und installieren')) {
        & wsl --install --no-distribution
        Install-Paket -Name 'Docker Desktop' -WingetId 'Docker.DockerDesktop' -Vorhanden { Test-Befehl 'docker' } -Ersatz {
            $datei = Join-Path $tmp 'DockerDesktopInstaller.exe'
            Invoke-Download -Url 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' -Ziel $datei -Herausgeber 'Docker'
            Start-Process -FilePath $datei -ArgumentList 'install', '--quiet', '--accept-license' -Wait
        }
        Write-Warnung 'Neustart noetig. Docker Desktop: Lizenzbedingungen beachten (kostenlos fuer kleine Unternehmen/privat).'
    }
}

if (-not $OhneMt5) {
    Write-Schritt 'MetaTrader 5 (interaktiv)'
    $terminal = Join-Path $k.Mt5Ordner 'terminal64.exe'
    if (Test-Path $terminal) {
        Write-Ok "MT5 vorhanden: $terminal"
    } elseif ($PSCmdlet.ShouldProcess('MetaTrader 5', 'Installer laden und starten')) {
        $datei = Join-Path $tmp 'mt5setup.exe'
        Invoke-Download -Url $k.Mt5InstallerUrl -Ziel $datei -Herausgeber 'MetaQuotes'
        Write-Host "   Im Installer 'Einstellungen' waehlen und als Ordner $($k.Mt5Ordner) eintragen. Nach der Installation NICHT anmelden -"
        Write-Host "   das macht der Bot-Benutzer $($k.BotBenutzer) selbst (40_bot.ps1)."
        Start-Process -FilePath $datei -Wait
    }
}
Write-Host ''
Write-Ok 'Software fertig. Neue PowerShell oeffnen (PATH), dann als Agent-Benutzer 60_agent.ps1.'
Write-Host '   40_bot.ps1 (als Bot-Benutzer) und 50_aufgaben.ps1 nur bei Bot-Betrieb - nicht, solange das Projekt ruht.'
