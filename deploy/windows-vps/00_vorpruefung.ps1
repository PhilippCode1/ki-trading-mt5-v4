<#
.SYNOPSIS
  Schritt 0: Nur-Lese-Pruefung des VPS vor der Einrichtung (aendert nichts).
.DESCRIPTION
  Prueft Windows-Version, Ressourcen, Virtualisierung (fuer Docker/WSL2), Zeitsynchronisation, offene Ports,
  vorhandene Werkzeuge und Ordner. Ausgabe je Punkt OK / WARNUNG / FEHLER. Exit 1 bei FEHLER.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\00_vorpruefung.ps1
#>
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
$fehler = 0
function Melde([string]$Stufe, [string]$Text) {
    switch ($Stufe) { 'OK' { Write-Ok $Text } 'WARNUNG' { Write-Warnung $Text } default { Write-Fehler $Text; $script:fehler++ } }
}

Write-Schritt "Konfiguration: $($k.Quelle)"
$os = Get-CimInstance Win32_OperatingSystem
Melde $(if ([int]$os.BuildNumber -ge 17763) { 'OK' } else { 'FEHLER' }) "Windows: $($os.Caption) Build $($os.BuildNumber)"
Melde $(if ($PSVersionTable.PSVersion.Major -ge 5) { 'OK' } else { 'FEHLER' }) "PowerShell $($PSVersionTable.PSVersion)"

$ram = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
Melde $(if ($ram -ge 8) { 'OK' } elseif ($ram -ge 4) { 'WARNUNG' } else { 'FEHLER' }) "Arbeitsspeicher $ram GB (Ziel >= 8 GB)"
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
Melde $(if ($cpu -ge 4) { 'OK' } else { 'WARNUNG' }) "Logische Prozessoren: $cpu (Ziel >= 4)"
$c = Get-PSDrive -Name C
$frei = [math]::Round($c.Free / 1GB, 1)
Melde $(if ($frei -ge 40) { 'OK' } elseif ($frei -ge 15) { 'WARNUNG' } else { 'FEHLER' }) "Freier Platz auf C: $frei GB (Ziel >= 40 GB)"

# Virtualisierung: noetig fuer WSL2/Docker Desktop (verschachtelte Virtualisierung beim Anbieter)
$virt = $null
try { $virt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled } catch { }
$hyper = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
if ($virt) { Melde 'OK' 'Virtualisierung in der VM verfuegbar (WSL2/Docker moeglich)' }
elseif ($hyper) { Melde 'WARNUNG' 'Hypervisor erkannt, verschachtelte Virtualisierung unklar - Docker/WSL2 vor dem Kauf beim Anbieter klaeren' }
else { Melde 'WARNUNG' 'Keine Virtualisierung - Docker/WSL2 hier nicht moeglich; Zusatzdienste auf einem Linux-Server betreiben' }

# Zeit: der Bot misst den Serverversatz selbst, braucht aber eine laufende Zeitsynchronisation
$w32 = (& w32tm /query /status 2>&1) -join ' '
Melde $(if ($w32 -match 'Stratum|Quelle|Source') { 'OK' } else { 'WARNUNG' }) 'Zeitdienst w32time antwortet'
Melde 'OK' "Zeitzone: $((Get-TimeZone).Id) (der Bot rechnet intern in UTC, Fenster in Europe/Berlin)"

# Offene Ports (nur lauschende TCP-Ports ausserhalb Loopback)
$lausch = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') } |
    Select-Object -ExpandProperty LocalPort -Unique | Sort-Object
Melde 'OK' "Lauschende Ports (extern erreichbar, falls Firewall offen): $($lausch -join ', ')"
foreach ($p in 22345, 22346) { if ($lausch -contains $p) { Melde 'FEHLER' "MT5-KI/MCP-Port $p lauscht - abschalten" } }
$rdp = @(Get-RdpRegeln | Where-Object { $_.Enabled -eq 'True' })
$rdpOffen = @($rdp | Get-NetFirewallAddressFilter | Where-Object { $_.RemoteAddress -ne '100.64.0.0/10' })
if ($rdpOffen.Count) { Melde 'WARNUNG' 'RDP ist nicht auf das Tailnet beschraenkt - nach Einrichtung von Tailscale 10_system.ps1 -RdpNurTailscale' }
elseif ($rdp.Count) { Melde 'OK' 'RDP nur aus dem Tailnet (100.64.0.0/10)' }

foreach ($w in 'git', 'gh', 'py', 'uv', 'winget', 'tailscale', 'docker', 'claude') {
    Melde $(if (Test-Befehl $w) { 'OK' } else { 'WARNUNG' }) "Werkzeug '$w' $(if (Test-Befehl $w) { 'vorhanden' } else { 'fehlt (' + $(if ($w -eq 'claude') { '60_agent.ps1' } else { '30_software.ps1' }) + ')' })"
}
if (Test-Befehl 'py') {
    $versionen = (& py -0p 2>&1) -join ' '
    foreach ($v in $k.PythonBot, $k.PythonDev) { Melde $(if ($versionen -match "-V:$v|-$v") { 'OK' } else { 'WARNUNG' }) "Python $v $(if ($versionen -match "-V:$v|-$v") { 'installiert' } else { 'fehlt' })" }
}
Melde $(if (Test-Path (Join-Path $k.Mt5Ordner 'terminal64.exe')) { 'OK' } else { 'WARNUNG' }) "MT5-Terminal unter $($k.Mt5Ordner)"
foreach ($b in $k.BotBenutzer, $k.AgentBenutzer) {
    Melde $(if (Get-LocalUser -Name $b -ErrorAction SilentlyContinue) { 'OK' } else { 'WARNUNG' }) "Benutzer $b $(if (Get-LocalUser -Name $b -ErrorAction SilentlyContinue) { 'vorhanden' } else { 'fehlt (20_benutzer.ps1)' })"
}
$neustart = Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
Melde $(if ($neustart) { 'WARNUNG' } else { 'OK' }) "Ausstehender Neustart nach Updates: $neustart"

Write-Host ''
if ($fehler) { Write-Fehler "$fehler Fehler - erst beheben."; exit 1 }
Write-Ok 'Vorpruefung ohne Fehler.'
