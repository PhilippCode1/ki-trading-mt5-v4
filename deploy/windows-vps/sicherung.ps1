<#
.SYNOPSIS
  Taegliche Sicherung (als kitbot, Aufgabe "KI-Trading Sicherung"): kit sichern ohne Schluessel in den Sicherungsordner.
.DESCRIPTION
  Sichert Journale, Zustaende, Freigaben (ohne PIN-Dateien) und Exporte als ZIP. Schluessel (geheim\) sichert nur der
  Betreiber interaktiv mit "kit sichern --mit-schluessel" (z. B. vor einem Umzug). Aeltere ZIPs als SicherungTage
  werden geloescht (nur kit-sicherung-*.zip in diesem Ordner). Fuer eine Kopie ausser Haus: docs/BETRIEB.md (restic).
#>
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
Assert-Benutzer $k.BotBenutzer
$repo = Join-Path $env:USERPROFILE $k.RepoOrdnerName
$py = Join-Path $repo '.venv-bot\Scripts\python.exe'
Push-Location $repo
try {
    & $py -B -m kit sichern --ziel $k.SicherungOrdner
    if ($LASTEXITCODE -ne 0) { throw "kit sichern Exit $LASTEXITCODE" }
} finally { Pop-Location }
Get-ChildItem -Path $k.SicherungOrdner -Filter 'kit-sicherung-*.zip' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$k.SicherungTage) } | Remove-Item -Force
