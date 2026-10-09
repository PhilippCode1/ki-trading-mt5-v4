<#
.SYNOPSIS
  Status-Export (als kitbot, Aufgabe "KI-Trading Status", alle 15 min).
.DESCRIPTION
  Schreibt den redigierten Status und den Tor-T-Stand in den Austauschordner (lesbar fuer den Agent-Benutzer und fuer
  Monitoring). Liegt in %USERPROFILE%\KI-Trading-Bot\herzschlag_url.txt eine Ping-URL (z. B. healthchecks.io oder
  Uptime Kuma "Push"), wird sie aufgerufen, solange der Bot laeuft - bleibt der Ping aus, alarmiert der Dienst.
#>
param([ValidateSet('probe', 'demo')][string]$Modus = 'probe')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
Assert-Benutzer $k.BotBenutzer
$repo = Join-Path $env:USERPROFILE $k.RepoOrdnerName
$py = Join-Path $repo '.venv-bot\Scripts\python.exe'
Push-Location $repo
try {
    $status = (& $py -B -m kit status --modus $Modus) -join "`n"
    $tor = (& $py -B -m kit tor-t --stand --modus $Modus --ohne-export) -join "`n"
} finally { Pop-Location }
$stempel = Get-Date -Format s
Set-Content -Path (Join-Path $k.AustauschOrdner "status_$Modus.txt") -Value "Stand $stempel`n$status" -Encoding UTF8
Set-Content -Path (Join-Path $k.AustauschOrdner "tor_t_$Modus.txt") -Value "Stand $stempel`n$tor" -Encoding UTF8

$urlDatei = Join-Path $env:USERPROFILE 'KI-Trading-Bot\herzschlag_url.txt'
$prozess = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '-m kit lauf' })
if ((Test-Path $urlDatei) -and $prozess.Count -and $status -match '"laeuft_vermutlich": true') {   # Prozess UND Journal
    $url = (Get-Content $urlDatei -TotalCount 1).Trim()
    if ($url.StartsWith('https://')) {
        try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20 | Out-Null } catch { }
    }
}
