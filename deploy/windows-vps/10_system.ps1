<#
.SYNOPSIS
  Schritt 1 (Administrator): Systemgrundlage fuer den Dauerbetrieb.
.DESCRIPTION
  - Energie: nie Standby/Ruhezustand, Hochleistung.
  - Zeit: w32time mit festen NTP-Quellen, sofortige Synchronisation.
  - Windows Update: Nutzungszeit, kein automatischer Neustart bei angemeldetem Benutzer (der Bot-Benutzer ist per
    Autologon immer angemeldet) - Neustarts nur im Wartungsfenster am Samstag (Markt geschlossen).
  - Lange Pfade, Defender-Echtzeitschutz pruefen, Firewall aktiv mit Standard "eingehend blockieren".
  - Optional: RDP nur aus dem Tailscale-Netz (100.64.0.0/10) - erst aktivieren, wenn Tailscale laeuft!
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\10_system.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$RdpNurTailscale)
. "$PSScriptRoot\_gemeinsam.ps1"
Assert-Admin
$k = Get-VpsKonfig
$rdpTailscale = $RdpNurTailscale -or $k.RdpNurTailscale

Write-Schritt 'Energie: kein Standby, kein Ruhezustand'
if ($PSCmdlet.ShouldProcess('Energieoptionen', 'Standby/Ruhezustand aus, Hochleistung')) {
    & powercfg /setactive SCHEME_MIN | Out-Null
    foreach ($x in 'standby-timeout-ac', 'standby-timeout-dc', 'hibernate-timeout-ac', 'hibernate-timeout-dc', 'monitor-timeout-ac') {
        & powercfg /change $x 0 | Out-Null
    }
    & powercfg /hibernate off | Out-Null
    Write-Ok 'Energieoptionen gesetzt'
}

Write-Schritt 'Zeitsynchronisation'
if ($PSCmdlet.ShouldProcess('w32time', 'NTP-Quellen setzen und synchronisieren')) {
    Set-Service -Name w32time -StartupType Automatic
    Start-Service w32time -ErrorAction SilentlyContinue
    & w32tm /config /manualpeerlist:"time.windows.com,0x9 0.de.pool.ntp.org,0x9 1.de.pool.ntp.org,0x9" /syncfromflags:manual /reliable:yes /update | Out-Null
    & w32tm /resync /force | Out-Null
    Write-Ok ((& w32tm /query /source) -join ' ')
}

Write-Schritt 'Windows Update: Nutzungszeit und keine Zwangsneustarts'
$wu = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
$ux = 'HKLM:\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings'
if ($PSCmdlet.ShouldProcess('Windows Update', "Nutzungszeit $($k.AktivVon)-$($k.AktivBis) Uhr, NoAutoRebootWithLoggedOnUsers")) {
    New-Item -Path $wu -Force | Out-Null
    Set-ItemProperty -Path $wu -Name NoAutoRebootWithLoggedOnUsers -Type DWord -Value 1
    Set-ItemProperty -Path $wu -Name AUOptions -Type DWord -Value 3          # herunterladen, Installation zur Wartung
    New-Item -Path $ux -Force | Out-Null
    Set-ItemProperty -Path $ux -Name ActiveHoursStart -Type DWord -Value $k.AktivVon
    Set-ItemProperty -Path $ux -Name ActiveHoursEnd -Type DWord -Value $k.AktivBis
    Write-Ok "Updates werden geladen; installieren + neu starten im Wartungsfenster ($($k.WartungsTag) $($k.WartungsStunde):00, siehe docs/BETRIEB.md)"
}

Write-Schritt 'Lange Pfade, Defender, Firewall'
if ($PSCmdlet.ShouldProcess('System', 'LongPathsEnabled, Firewall-Profile aktiv')) {
    Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Type DWord -Value 1
    Set-NetFirewallProfile -Profile Domain, Public, Private -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow
    Write-Ok 'Firewall: alle Profile aktiv, eingehend standardmaessig blockiert'
}
try {
    $mp = Get-MpComputerStatus
    if ($mp.RealTimeProtectionEnabled) { Write-Ok 'Defender-Echtzeitschutz aktiv' } else { Write-Warnung 'Defender-Echtzeitschutz AUS - einschalten' }
} catch { Write-Warnung 'Defender-Status nicht lesbar (anderer Virenschutz?)' }

if ($rdpTailscale) {
    Write-Schritt 'RDP nur ueber Tailscale'
    $tailnet = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -like '100.*' })
    if (-not (Test-Befehl 'tailscale') -or -not $tailnet.Count) {
        Write-Warnung 'Tailscale fehlt oder ist nicht verbunden - RDP bleibt unveraendert (sonst sperrst du dich aus). Erst "tailscale up" und RDP ueber die 100.x-Adresse testen.'
    } elseif ($PSCmdlet.ShouldProcess('Firewall', 'RDP-Regeln auf 100.64.0.0/10 beschraenken')) {
        $regeln = Get-RdpRegeln
        if ($regeln.Count -eq 0) { throw 'Keine eingehenden RDP-Firewallregeln gefunden - nichts beschraenkt. Regeln pruefen (wf.msc).' }
        $regeln | Set-NetFirewallRule -RemoteAddress '100.64.0.0/10'
        $offen = @($regeln | Get-NetFirewallAddressFilter | Where-Object { $_.RemoteAddress -ne '100.64.0.0/10' })
        if ($offen.Count) { throw 'RDP-Regel(n) nicht auf das Tailnet beschraenkt - bitte pruefen.' }
        Write-Ok "RDP ($($regeln.Count) Regeln) nur noch aus dem Tailnet. Zusaetzlich beim VPS-Anbieter Port 3389 schliessen."
    }
}
Write-Host ''
Write-Ok 'Systemgrundlage fertig. Weiter mit 20_benutzer.ps1.'
