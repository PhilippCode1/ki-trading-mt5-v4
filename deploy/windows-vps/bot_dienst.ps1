<#
.SYNOPSIS
  Autostart-Huelle des Bots (laeuft als kitbot, gestartet von der Aufgabe "KI-Trading Bot" bei Anmeldung).
.DESCRIPTION
  - Vor JEDEM Start: BEENDEN-Datei beachten (dann Ende) und sicherstellen, dass das MT5-Terminal des Benutzers laeuft
    (bei Bedarf portabel starten und auf die Verbindung warten). Der Bot selbst startet nie ein Terminal.
  - Startet die installierte Kopie aus %USERPROFILE%\KI-Trading-Bot\app\<aktiver Tag> (start_<modus>.cmd).
  - Exit 0 (BEENDEN-Datei oder Laufzeitende) = gewollter Stopp -> Huelle endet.
  - Exit 2 (Sicherheits-Ende des Takts, z. B. NICHT_DEMO, Algo Trading aus, Hedging fehlt) -> Huelle endet; der Betreiber
    behebt die Ursache und startet neu (Aufgabe "KI-Trading Bot" ausfuehren).
  - Exit 3/4/5 (Terminal weg, MT5 nicht nutzbar bzw. Markt zu, Demo-Pruefung) -> Neustart mit wachsender Pause
    (1, 2, 4 ... hoechstens 15 min) ohne Begrenzung, z. B. uebers Wochenende.
  - Andere Exits (Programmfehler) -> wie oben, aber hoechstens 10 Neustarts je 6 h.
  - Ausgabe des Bots geht an <Ablage>\<modus>\konsole.log, die Huelle protokolliert nach <Ablage>\dienst.log.
#>
param([ValidateSet('probe', 'demo')][string]$Modus = 'probe')
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
Assert-Benutzer $k.BotBenutzer
$heim = Join-Path $env:USERPROFILE 'KI-Trading-Bot'
$log = Join-Path $heim 'dienst.log'
$beenden = Join-Path $heim "$Modus\BEENDEN"
function Protokoll([string]$Text) { Add-Content -Path $log -Value "$(Get-Date -Format s) $Text" -Encoding UTF8 }

$tagDatei = Join-Path $heim 'aktiver_tag.txt'
if (-not (Test-Path $tagDatei)) { Protokoll 'Kein aktiver Tag (40_bot.ps1 -Tag ...) - Ende.'; exit 2 }
$tag = (Get-Content $tagDatei -TotalCount 1).Trim()
$app = Join-Path $heim ('app\' + $tag.Replace('/', '_'))
$start = Join-Path $app "start_$Modus.cmd"
if (-not (Test-Path $start)) { Protokoll "Installation fehlt: $start - Ende."; exit 2 }
New-Item -ItemType Directory -Path (Join-Path $heim $Modus) -Force | Out-Null
$konsole = Join-Path $heim "$Modus\konsole.log"
$terminal = Join-Path $k.Mt5Ordner 'terminal64.exe'

function Test-Mt5 { [bool](Get-Process -Name terminal64 -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $terminal }) }

function Sicherstellen-Mt5 {
    if (Test-Mt5) { return $true }
    Protokoll "Starte MT5: $terminal /portable"
    Start-Process -FilePath $terminal -ArgumentList '/portable'
    for ($i = 0; $i -lt 60 -and -not (Test-Mt5); $i++) { Start-Sleep -Seconds 5 }
    if (-not (Test-Mt5)) { return $false }
    Start-Sleep -Seconds 60                               # Terminal verbindet sich mit dem Server
    return $true
}

function Warten([int]$Sekunden) {
    # in kurzen Schritten warten, damit ein "kit stop --beenden" waehrend der Pause sofort wirkt
    for ($i = 0; $i -lt $Sekunden; $i += 5) {
        if (Test-Path $beenden) { Protokoll 'BEENDEN waehrend der Pause - Huelle endet.'; exit 0 }
        Start-Sleep -Seconds 5
    }
}

$neustarts = @()
$pause = 60
while ($true) {
    if (Test-Path $beenden) { Protokoll 'BEENDEN vorhanden - Huelle endet (kein Start).'; exit 0 }
    if (-not (Sicherstellen-Mt5)) {
        Protokoll 'MT5 laeuft nicht - naechster Versuch nach der Pause.'
        Warten $pause
        $pause = [Math]::Min($pause * 2, 900)
        continue
    }
    Protokoll "Start $tag ($Modus)"
    # cmd /s /c "<ganzer Befehl>": mit /s entfernt cmd genau die aeusseren Anfuehrungszeichen, die inneren bleiben gueltig
    $befehl = '"' + '"' + $start + '" >> "' + $konsole + '" 2>&1' + '"'
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList '/d', '/s', '/c', $befehl -WorkingDirectory $app -PassThru -Wait -WindowStyle Hidden
    $code = $p.ExitCode
    Protokoll "Bot beendet mit Exit $code"
    if ($code -eq 0) { Protokoll 'Gewollter Stopp (BEENDEN/Laufzeit) - Huelle endet.'; exit 0 }
    if ($code -eq 2) { Protokoll 'Sicherheits-Ende des Takts - kein Neustart (Ursache in MELDUNGEN.txt, docs/BETRIEB.md).'; exit 2 }
    $jetzt = Get-Date
    if ($code -notin 3, 4, 5) {
        # unerwartete Fehler: Absturzschleifen begrenzen. 3/4/5 (Terminal weg, Markt zu - Serverversatz erst bei laufenden
        # Kursen messbar -, Demo-Pruefung) wartet die Huelle dagegen unbegrenzt ab, z. B. uebers Wochenende.
        $neustarts = @($neustarts | Where-Object { $_ -ge $jetzt.AddHours(-6) }) + $jetzt
        if ($neustarts.Count -gt 10) { Protokoll 'Mehr als 10 Fehler-Neustarts in 6 h - Huelle endet (docs/BETRIEB.md).'; exit 4 }
    }
    Protokoll "Neustart in $pause s"
    Warten $pause
    $pause = [Math]::Min($pause * 2, 900)
}
