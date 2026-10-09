# Gemeinsame Hilfsfunktionen fuer die VPS-Skripte (Windows PowerShell 5.1, nur ASCII).
# Wird per Dot-Sourcing geladen:  . "$PSScriptRoot\_gemeinsam.ps1"
# Grundsaetze: idempotent (mehrfach ausfuehrbar), keine Zugangsdaten in Dateien, -WhatIf zeigt nur an.

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:ZentraleKonfig = Join-Path $env:SystemDrive 'KI-Trading\vps.config.psd1'

function Get-VpsKonfig {
    # Reihenfolge: vps.config.psd1 neben dem Skript (Einrichtung aus C:\KI-Trading-Setup) -> zentrale Kopie
    # %SystemDrive%\KI-Trading\vps.config.psd1 (legt 20_benutzer.ps1 an; gilt fuer die Skripte im Repo-Checkout und die Aufgaben)
    # -> Vorlage vps.config.example.psd1 mit deutlicher Warnung.
    $eigen = Join-Path $PSScriptRoot 'vps.config.psd1'
    $vorlage = Join-Path $PSScriptRoot 'vps.config.example.psd1'
    $pfad = if (Test-Path $eigen) { $eigen } elseif (Test-Path $script:ZentraleKonfig) { $script:ZentraleKonfig } else { $vorlage }
    if ($pfad -eq $vorlage) { Write-Warning "Keine vps.config.psd1 gefunden - es gilt die Vorlage ($vorlage)." }
    $k = Import-PowerShellDataFile -Path $pfad
    $k['Quelle'] = $pfad
    return $k
}

function Get-RdpRegeln {
    # Sprachunabhaengig ueber die Gruppen-Ressource (DisplayGroup ist uebersetzt, z. B. 'Remotedesktop').
    @(Get-NetFirewallRule -Group '@FirewallAPI.dll,-28752' -ErrorAction SilentlyContinue | Where-Object { $_.Direction -eq 'Inbound' })
}

function Write-Schritt([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "OK       $Text" -ForegroundColor Green }
function Write-Warnung([string]$Text) { Write-Host "WARNUNG  $Text" -ForegroundColor Yellow }
function Write-Fehler([string]$Text) { Write-Host "FEHLER   $Text" -ForegroundColor Red }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Admin {
    if (-not (Test-Admin)) { throw 'Dieses Skript braucht eine Administrator-PowerShell (Rechtsklick > Als Administrator ausfuehren).' }
}

function Assert-Benutzer([string]$Name) {
    if ($env:USERNAME -ne $Name) { throw "Dieses Skript laeuft als Benutzer '$Name' (angemeldet ist '$env:USERNAME')." }
}

function Test-Befehl([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Invoke-Download {
    # Laedt eine Datei per HTTPS und prueft die Authenticode-Signatur gegen den erwarteten Herausgeber.
    param([string]$Url, [string]$Ziel, [string]$Herausgeber)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    if (-not $Url.StartsWith('https://')) { throw "Nur HTTPS-Downloads: $Url" }
    Invoke-WebRequest -Uri $Url -OutFile $Ziel -UseBasicParsing
    $sig = Get-AuthenticodeSignature -FilePath $Ziel
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike "*$Herausgeber*") {
        Remove-Item $Ziel -Force
        throw "Signatur von $Ziel ungueltig oder fremder Herausgeber ($($sig.Status), $($sig.SignerCertificate.Subject))."
    }
    Write-Ok "Download signiert von '$Herausgeber': $Ziel"
}

function Set-OrdnerRechte {
    # Setzt explizite NTFS-Rechte (Vererbung aus, nur die angegebenen Eintraege). $Rechte: @{ 'Benutzer' = 'F'|'M'|'RX' }
    param([string]$Pfad, [hashtable]$Rechte)
    if (-not (Test-Path $Pfad)) { New-Item -ItemType Directory -Path $Pfad -Force | Out-Null }
    $argumente = @($Pfad, '/inheritance:r', '/grant:r', '*S-1-5-32-544:(OI)(CI)F', '/grant:r', '*S-1-5-18:(OI)(CI)F')
    foreach ($eintrag in $Rechte.GetEnumerator()) {
        $argumente += '/grant:r'
        $argumente += "$($eintrag.Key):(OI)(CI)$($eintrag.Value)"
    }
    & icacls @argumente | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls fuer $Pfad fehlgeschlagen (Exit $LASTEXITCODE)." }
    Write-Ok "Rechte gesetzt: $Pfad"
}
