<#
.SYNOPSIS
  Schritt 2 (Administrator): Benutzer und Ordner mit getrennten Rechten.
.DESCRIPTION
  Benutzermodell (docs/SICHERHEIT.md):
    kitbot  - betreibt MT5-Demo-Terminal und den Bot; per Autologon immer angemeldet (MT5 ist eine GUI-Anwendung).
              Bot-Daten liegen in %SystemDrive%\Users\kitbot\KI-Trading-Bot - fuer andere Benutzer per Profilrecht unlesbar.
    kitdev  - Claude Code und Entwicklung; liest nur redigierte Exporte im Austauschordner.
  Passwoerter gibt ausschliesslich der Betreiber hier interaktiv ein; sie werden nirgends gespeichert.
  Ordner unter Basis:
    mt5-demo  (kitbot aendern)            - portables MT5-Demo-Terminal
    sicherung (kitbot aendern)            - taegliche Sicherungen (kit sichern)
    austausch (kitbot aendern, kitdev lesen) - redigierte Exporte/Status fuer Agent und Monitoring
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\20_benutzer.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()
. "$PSScriptRoot\_gemeinsam.ps1"
Assert-Admin
$k = Get-VpsKonfig

foreach ($name in $k.BotBenutzer, $k.AgentBenutzer) {
    Write-Schritt "Benutzer $name"
    if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) {
        Write-Ok "$name existiert bereits"
    } elseif ($PSCmdlet.ShouldProcess($name, 'Lokalen Standardbenutzer anlegen')) {
        $pw = Read-Host -AsSecureString "Neues Passwort fuer $name (nur du kennst es; mind. 16 Zeichen empfohlen)"
        $pw2 = Read-Host -AsSecureString 'Passwort wiederholen'
        $a = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
        $b = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw2))
        if ($a -ne $b) { throw 'Die Passwoerter stimmen nicht ueberein.' }
        $a = $null; $b = $null
        New-LocalUser -Name $name -Password $pw -FullName "KI-Trading $name" -Description 'KI-Trading MT5 (Standardbenutzer)' | Out-Null
        Write-Ok "$name angelegt (Standardbenutzer, kein Administrator)"
    }
    if ($PSCmdlet.ShouldProcess($name, 'Gruppe Remotedesktopbenutzer')) {
        $gruppe = (Get-LocalGroup -SID 'S-1-5-32-555').Name
        if (-not (Get-LocalGroupMember -Group $gruppe -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*\$name" })) {
            Add-LocalGroupMember -Group $gruppe -Member $name
        }
        Write-Ok "$name darf sich per RDP anmelden"
    }
}
if ($PSCmdlet.ShouldProcess($k.BotBenutzer, 'Passwort laeuft nicht ab (sonst bricht der Autologon)')) {
    Set-LocalUser -Name $k.BotBenutzer -PasswordNeverExpires $true
}

Write-Schritt "Ordner unter $($k.Basis)"
if ($PSCmdlet.ShouldProcess($k.Basis, 'Ordner anlegen und Rechte setzen')) {
    Set-OrdnerRechte -Pfad $k.Basis -Rechte @{ $k.BotBenutzer = 'RX'; $k.AgentBenutzer = 'RX' }
    Set-OrdnerRechte -Pfad $k.Mt5Ordner -Rechte @{ $k.BotBenutzer = 'M' }
    Set-OrdnerRechte -Pfad $k.SicherungOrdner -Rechte @{ $k.BotBenutzer = 'M' }
    Set-OrdnerRechte -Pfad $k.AustauschOrdner -Rechte @{ $k.BotBenutzer = 'M'; $k.AgentBenutzer = 'RX' }
}

if ($PSCmdlet.ShouldProcess($script:ZentraleKonfig, 'Konfiguration zentral ablegen (fuer Repo-Skripte und Aufgaben)')) {
    $quelle = $k.Quelle
    if ($quelle -ne $script:ZentraleKonfig) { Copy-Item -Path $quelle -Destination $script:ZentraleKonfig -Force }
    Write-Ok "Konfiguration: $script:ZentraleKonfig (Aenderungen kuenftig dort)"
}

Write-Host ''
Write-Ok 'Benutzer und Ordner fertig.'
Write-Host @"
Naechste Handgriffe (nur Betreiber):
  1. Autologon fuer $($k.BotBenutzer) einrichten: Sysinternals Autologon (https://learn.microsoft.com/sysinternals/downloads/autologon)
     starten, Benutzer $($k.BotBenutzer) und sein Passwort eingeben. Autologon speichert es verschluesselt (LSA-Secret).
  2. Weiter mit 30_software.ps1 (Administrator).
"@
