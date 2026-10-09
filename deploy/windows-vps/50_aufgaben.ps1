<#
.SYNOPSIS
  Schritt 5 (Administrator): Aufgabenplanung fuer den Dauerbetrieb des Bot-Benutzers.
.DESCRIPTION
  Alle Aufgaben laufen als kitbot mit "nur wenn angemeldet" (interaktives Token) - es wird KEIN Passwort gespeichert.
  Das funktioniert, weil kitbot per Autologon dauerhaft angemeldet ist (MT5 braucht eine Desktop-Sitzung).
    KI-Trading Bot          bei Anmeldung: bot_dienst.ps1 (MT5 sicherstellen, Bot starten, Neustart mit Pause)
    KI-Trading Sicherung    taeglich: kit sichern -> Sicherungsordner, alte Sicherungen aufraeumen
    KI-Trading Status       alle 15 min: redigierter Status/Tor-T in den Austauschordner (+ optional Herzschlag-Ping)
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\50_aufgaben.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([ValidateSet('probe', 'demo')][string]$Modus = 'probe', [switch]$Entfernen)
. "$PSScriptRoot\_gemeinsam.ps1"
Assert-Admin
$k = Get-VpsKonfig
$benutzer = "$env:COMPUTERNAME\$($k.BotBenutzer)"
$botProfil = Join-Path (Join-Path $env:SystemDrive 'Users') $k.BotBenutzer
$skripte = Join-Path $botProfil "$($k.RepoOrdnerName)\deploy\windows-vps"
$ordner = '\KI-Trading\'

function Neue-Aufgabe([string]$Name, $Ausloeser, [string]$Skript, [string]$Argumente = '') {
    $aktion = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$skripte\$Skript`" $Argumente" -WorkingDirectory $skripte
    $prinzipal = New-ScheduledTaskPrincipal -UserId $benutzer -LogonType Interactive -RunLevel Limited
    $einst = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
    if ($PSCmdlet.ShouldProcess("$ordner$Name", 'Aufgabe registrieren')) {
        Register-ScheduledTask -TaskPath $ordner -TaskName $Name -Action $aktion -Trigger $Ausloeser -Principal $prinzipal -Settings $einst -Force | Out-Null
        Write-Ok "Aufgabe $ordner$Name"
    }
}

if ($Entfernen) {
    Get-ScheduledTask -TaskPath $ordner -ErrorAction SilentlyContinue | ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.TaskName, 'Aufgabe entfernen')) { Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $ordner -Confirm:$false }
    }
    Write-Ok 'Aufgaben entfernt.'; return
}
if (-not (Get-LocalUser -Name $k.BotBenutzer -ErrorAction SilentlyContinue)) { throw "Benutzer $($k.BotBenutzer) fehlt (20_benutzer.ps1)." }
if (-not (Test-Path (Join-Path $skripte 'bot_dienst.ps1'))) { throw "Bot-Checkout fehlt: $skripte (40_bot.ps1 als $($k.BotBenutzer))." }

Write-Schritt 'Aufgaben fuer den Bot-Benutzer'
$beiAnmeldung = New-ScheduledTaskTrigger -AtLogOn -User $benutzer
$beiAnmeldung.Delay = 'PT1M'
Neue-Aufgabe -Name 'KI-Trading Bot' -Ausloeser $beiAnmeldung -Skript 'bot_dienst.ps1' -Argumente "-Modus $Modus"
Neue-Aufgabe -Name 'KI-Trading Sicherung' -Ausloeser (New-ScheduledTaskTrigger -Daily -At $k.SicherungUhrzeit) -Skript 'sicherung.ps1'
$alle15 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 15)
Neue-Aufgabe -Name 'KI-Trading Status' -Ausloeser $alle15 -Skript 'status_export.ps1' -Argumente "-Modus $Modus"

Write-Host ''
Write-Ok 'Autostart eingerichtet. Test: als kitbot ab- und wieder anmelden (bzw. Neustart), dann 90_status.ps1.'
