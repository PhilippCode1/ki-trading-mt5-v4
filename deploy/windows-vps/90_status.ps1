<#
.SYNOPSIS
  Gesundheitsblick auf den VPS (nur lesen; vollstaendig als Administrator oder kitbot - kitdev sieht Bot-Prozess und
  Sicherungen nicht).
.DESCRIPTION
  Aufgaben, Prozesse (MT5, Bot), letzter Status-Export, Platz, Zeitquelle, ausstehender Neustart, Sicherungsalter.
#>
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig

Write-Schritt 'Aufgaben'
Get-ScheduledTask -TaskPath '\KI-Trading\' -ErrorAction SilentlyContinue | ForEach-Object {
    $info = $_ | Get-ScheduledTaskInfo
    '{0,-22} {1,-8} letzter Lauf {2}  Ergebnis {3}' -f $_.TaskName, $_.State, $info.LastRunTime, $info.LastTaskResult
}
Write-Schritt 'Prozesse'
$mt5 = Get-Process -Name terminal64 -ErrorAction SilentlyContinue
if ($mt5) { Write-Ok "MT5 laeuft ($(@($mt5).Count) Prozess(e))" } else { Write-Warnung 'MT5 laeuft nicht' }
$bot = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '-m kit lauf' })
if ($bot.Count) { Write-Ok "Bot laeuft (PID $(@($bot.ProcessId) -join ', '))" }
else { Write-Warnung 'Bot-Prozess nicht gefunden (als kitdev nicht sichtbar - dann als Administrator oder kitbot pruefen)' }

Write-Schritt 'Austausch'
foreach ($d in Get-ChildItem -Path $k.AustauschOrdner -Filter 'status_*.txt' -ErrorAction SilentlyContinue) {
    $alter = [int]((Get-Date) - $d.LastWriteTime).TotalMinutes
    if ($alter -le 30) { Write-Ok "$($d.Name) vor $alter min" } else { Write-Warnung "$($d.Name) vor $alter min (Aufgabe 'KI-Trading Status' pruefen)" }
    Get-Content $d.FullName | Select-String -Pattern 'laeuft_vermutlich|sperren|stop_datei|umzug_offen' | ForEach-Object { "   $($_.Line.Trim())" }
}
Write-Schritt 'System'
$c = Get-PSDrive -Name C
'Freier Platz C: {0:N1} GB' -f ($c.Free / 1GB)
"Zeitquelle: $((& w32tm /query /source) -join ' ')"
if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') { Write-Warnung 'Neustart nach Updates ausstehend (im Wartungsfenster erledigen)' }
$letzte = Get-ChildItem -Path $k.SicherungOrdner -Filter 'kit-sicherung-*.zip' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($letzte) { "Letzte Sicherung: $($letzte.Name) ($($letzte.LastWriteTime))" } else { Write-Warnung 'Keine Sicherung im Sicherungsordner' }
