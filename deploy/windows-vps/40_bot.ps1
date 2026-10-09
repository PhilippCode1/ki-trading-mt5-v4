<#
.SYNOPSIS
  Schritt 4 (als Bot-Benutzer kitbot): Repo holen, Bot-Umgebung bauen, Terminal pruefen, Bot installieren.
.DESCRIPTION
  1. Repo nach %USERPROFILE%\ki-trading klonen bzw. aktualisieren (nur lesen; Anmeldung bei GitHub macht der Betreiber
     im Git-Credential-Manager-Fenster - am besten mit einem Fine-grained-Token, nur Lesen, nur dieses Repo).
  2. .venv-bot (Python 3.11) aus requirements/bot-runtime.lock.txt mit --require-hashes.
  3. kit pruefen.
  4. Optional -Tag: kit installieren --tag <Tag> (unveraenderliche Kopie unter KI-Trading-Bot\app\<Tag>).
  5. Optional -Uebernahme <Ordner>: Altbestand (entpackte Laptop-Sicherung) mit kit umziehen --von uebernehmen.
  Vor dem ersten Bot-Start (Betreiber, im MT5-Terminal): mit dem DEMO-Konto anmelden, "Algo Trading" an,
  Extras > Optionen > Charts > "Max. Balken im Chart: Unbegrenzt". Dann: kit konto-registrieren, kit rauchtest.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\40_bot.ps1 -Tag lauf/F-05d
  (Immer ein lauf/<ID>-Tag; lauf/F-05d traegt denselben mechanik_hash wie das Tor-T-Zertifikat vom 09.10.2026.
  Nur bei Bot-Betrieb ausfuehren - nicht, solange das Projekt ruht.)
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$Tag, [string]$Uebernahme)
. "$PSScriptRoot\_gemeinsam.ps1"
$k = Get-VpsKonfig
Assert-Benutzer $k.BotBenutzer
if (Test-Admin) { throw 'Bitte als normaler Bot-Benutzer ausfuehren, nicht als Administrator.' }
$repo = Join-Path $env:USERPROFILE $k.RepoOrdnerName

Write-Schritt "Repo $repo"
if (Test-Path (Join-Path $repo '.git')) {
    if ($PSCmdlet.ShouldProcess($repo, 'git fetch --tags (nur schnell vorspulen)')) {
        & git -C $repo fetch --tags --prune-tags origin
        & git -C $repo merge --ff-only origin/main
        if ($LASTEXITCODE -ne 0) { throw 'Kein Fast-Forward moeglich - Bot-Checkout darf keine eigenen Aenderungen haben.' }
    }
} elseif ($PSCmdlet.ShouldProcess($k.RepoUrl, "klonen nach $repo")) {
    & git clone $k.RepoUrl $repo
    if ($LASTEXITCODE -ne 0) { throw 'git clone fehlgeschlagen (Anmeldung im Git-Credential-Manager?).' }
}
Write-Ok ((& git -C $repo log --oneline -1) -join ' ')

Write-Schritt '.venv-bot (Python 3.11, hash-gesperrt)'
$py = Join-Path $repo '.venv-bot\Scripts\python.exe'
if ($PSCmdlet.ShouldProcess('.venv-bot', 'anlegen/aktualisieren')) {
    if (-not (Test-Path $py)) { & py "-$($k.PythonBot)" -m venv (Join-Path $repo '.venv-bot') }
    & $py -m pip install --disable-pip-version-check --require-hashes -r (Join-Path $repo 'requirements\bot-runtime.lock.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install fehlgeschlagen.' }
    Write-Ok ((& $py --version) -join ' ')
}

Write-Schritt 'Rechnerspezifische Einstellung lokal.toml (Terminalpfad)'
$heim = Join-Path $env:USERPROFILE 'KI-Trading-Bot'
$lokal = Join-Path $heim 'lokal.toml'
if (Test-Path $lokal) { Write-Ok "vorhanden: $lokal" }
elseif ($PSCmdlet.ShouldProcess($lokal, 'anlegen')) {
    New-Item -ItemType Directory -Path $heim -Force | Out-Null
    $inhalt = "# Rechnerspezifisch (nicht im Repo). Erlaubt: [terminal] pfad, [symbol_namen].`r`n[terminal]`r`npfad = '" +
        (Join-Path $k.Mt5Ordner 'terminal64.exe') + "'`r`n"
    Set-Content -Path $lokal -Value $inhalt -Encoding ASCII -NoNewline
    Write-Ok "angelegt: $lokal"
}

Push-Location $repo
try {
    Write-Schritt 'kit pruefen'
    & $py -B -m kit pruefen
    if ($LASTEXITCODE -ne 0) { Write-Warnung 'kit pruefen meldet FEHLER (siehe oben) - vor dem ersten Start beheben.' }
    if ($Uebernahme) {
        Write-Schritt "Altbestand uebernehmen aus $Uebernahme"
        if ($PSCmdlet.ShouldProcess($Uebernahme, 'kit umziehen --von')) {
            & $py -B -m kit umziehen --von $Uebernahme
            if ($LASTEXITCODE -ne 0) { throw "kit umziehen fehlgeschlagen (Exit $LASTEXITCODE)." }
        }
    }
    if ($Tag) {
        Write-Schritt "kit installieren --tag $Tag"
        $app = Join-Path $env:USERPROFILE ('KI-Trading-Bot\app\' + $Tag.Replace('/', '_'))
        if ($PSCmdlet.ShouldProcess($Tag, 'installieren')) {
            if (Test-Path (Join-Path $app 'INSTALLATION.json')) { Write-Ok "$Tag ist bereits installiert" }
            else {
                & $py -B -m kit installieren --tag $Tag
                if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $app 'INSTALLATION.json'))) {
                    throw "kit installieren --tag $Tag fehlgeschlagen - aktiver Tag bleibt unveraendert."
                }
            }
            Set-Content -Path (Join-Path $env:USERPROFILE 'KI-Trading-Bot\aktiver_tag.txt') -Value $Tag -Encoding ASCII
            Write-Ok "Aktiver Tag fuer den Autostart: $Tag (bot_dienst.ps1)"
        }
    }
} finally { Pop-Location }

Write-Host @"

Naechste Schritte (Betreiber, als $($k.BotBenutzer)):
  1. MT5 starten:  & '$($k.Mt5Ordner)\terminal64.exe' /portable   -> mit DEMO-Konto anmelden, Algo Trading an.
  2. cd $repo
     .\.venv-bot\Scripts\python.exe -m kit konto-registrieren
     .\.venv-bot\Scripts\python.exe -m kit rauchtest
     .\.venv-bot\Scripts\python.exe -m kit pin-setzen
  3. Autostart einrichten: 50_aufgaben.ps1 (Administrator).
"@
