<#
.SYNOPSIS
  Entwickler-Aufgaben in einem Befehl (Windows PowerShell 5.1, nur ASCII). Spiegelt die CI-Schritte.
.DESCRIPTION
  tools\dev.ps1 einrichten   .venv-311 und .venv-312 aus requirements\dev.lock.txt (hash-gesperrt), Hooks aktivieren
  tools\dev.ps1 test         kit_tests (Python 3.11)
  tools\dev.ps1 kern         Kerntests der eingefrorenen Referenz (Python 3.12), schnell
  tools\dev.ps1 lint         ruff check .
  tools\dev.ps1 scan         Geheimnis-Scan ueber den Baum
  tools\dev.ps1 forschung    .venv-forschung aus requirements\forschung.lock.txt (falls fehlt) + Tests mit scikit-learn (F-05)
  tools\dev.ps1 alles        lint + test + kern + scan (vor jedem Abschluss); Forschungstests, wenn .venv-forschung existiert
  .venv-bot (Bot-Laufzeit mit MetaTrader5) legt nur der Bot-Benutzer an: deploy\windows-vps\40_bot.ps1.
#>
param([ValidateSet('einrichten', 'test', 'kern', 'lint', 'scan', 'forschung', 'alles')][string]$Aufgabe = 'alles')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py311 = Join-Path $root '.venv-311\Scripts\python.exe'
$py312 = Join-Path $root '.venv-312\Scripts\python.exe'
$pyF = Join-Path $root '.venv-forschung\Scripts\python.exe'
$forschungstests = @('kit_tests\test_meta_sklearn.py', 'kit_tests\test_richtung_sklearn.py')

function Ausfuehren([string]$Titel, [scriptblock]$Block) {
    Write-Host "==> $Titel" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Titel fehlgeschlagen (Exit $LASTEXITCODE)" }
}

switch ($Aufgabe) {
    'einrichten' {
        foreach ($v in @(@{ Py = $py311; Reihe = '3.11'; Ordner = '.venv-311' }, @{ Py = $py312; Reihe = '3.12'; Ordner = '.venv-312' })) {
            if (-not (Test-Path $v.Py)) { Ausfuehren "venv $($v.Ordner)" { & py "-$($v.Reihe)" -m venv (Join-Path $root $v.Ordner) } }
            Ausfuehren "Pakete $($v.Ordner)" { & $v.Py -m pip install --disable-pip-version-check --require-hashes -r requirements\dev.lock.txt }
        }
        Ausfuehren 'Hooks' { & git config core.hooksPath .githooks }
        Ausfuehren 'Zeilenenden' { & git config core.autocrlf false }
    }
    'test' { Ausfuehren 'kit_tests' { & $py311 -B -m pytest -q } }
    'kern' { Ausfuehren 'Kerntests' { & $py312 -B tools\kerntests.py --schnell } }
    'lint' { Ausfuehren 'ruff' { & $py312 -m ruff check . } }
    'scan' { Ausfuehren 'Scan' { & $py312 -B tools\kit_scan.py --baum } }
    'forschung' {
        if (-not (Test-Path $pyF)) { Ausfuehren 'venv .venv-forschung' { & py -3.11 -m venv (Join-Path $root '.venv-forschung') } }
        Ausfuehren 'Pakete .venv-forschung' { & $pyF -m pip install --disable-pip-version-check --require-hashes -r requirements\forschung.lock.txt }
        Ausfuehren 'Forschungstests' { & $pyF -B -m pytest -q $forschungstests }
    }
    'alles' {
        Ausfuehren 'ruff' { & $py312 -m ruff check . }
        Ausfuehren 'kit_tests' { & $py311 -B -m pytest -q }
        Ausfuehren 'Kerntests' { & $py312 -B tools\kerntests.py --schnell }
        if (Test-Path $pyF) { Ausfuehren 'Forschungstests' { & $pyF -B -m pytest -q $forschungstests } }
        else { Write-Host 'Hinweis: .venv-forschung fehlt - Forschungstests (scikit-learn) uebersprungen; einrichten: tools\dev.ps1 forschung' -ForegroundColor Yellow }
        Ausfuehren 'Scan' { & $py312 -B tools\kit_scan.py --baum }
    }
}
Write-Host "OK $Aufgabe" -ForegroundColor Green
