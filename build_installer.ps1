param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64"
)

$ErrorActionPreference = "Stop"

# Dossiers
# Utiliser le dossier du script comme racine du repo pour éviter les chemins codés en dur
$repo = $PSScriptRoot
$proj = Join-Path $repo "PerformStatsSensorService\PerformStatsSensorService.csproj"
$dist = Join-Path $repo "dist"
$distApp = Join-Path $dist "PerformStatsSensorService"
$ohmSrc = Join-Path $repo "OpenHardwareMonitor"
$ohmDest = Join-Path $dist "OpenHardwareMonitor"
$iss = Join-Path $repo "installer.iss"

# Nettoyage / création dist
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist -Force | Out-Null

Write-Host "1) Publication .NET self-contained ($Configuration, $Runtime)" -ForegroundColor Cyan
& dotnet publish $proj -c $Configuration -r $Runtime --self-contained true -p:PublishSingleFile=false -o $distApp

# Vérif binaire
$exe = Join-Path $distApp "PerformStatsSensorService.exe"
if (-not (Test-Path $exe)) { throw "Publication échouée: $exe introuvable" }

Write-Host "2) Copie OpenHardwareMonitor dans dist" -ForegroundColor Cyan
if (Test-Path $ohmSrc) {
    Copy-Item -Path $ohmSrc -Destination $ohmDest -Recurse -Force
} else {
    Write-Warning "Dossier OpenHardwareMonitor non trouvé: $ohmSrc (continuer sans)"
}

Write-Host "3) Copie des scripts d'installation/désinstallation" -ForegroundColor Cyan
Copy-Item (Join-Path $repo "installer_service.ps1") -Destination (Join-Path $dist "installer_service.ps1") -Force
Copy-Item (Join-Path $repo "desinstaller_service.ps1") -Destination (Join-Path $dist "desinstaller_service.ps1") -Force

Write-Host "4) Compilation Inno Setup" -ForegroundColor Cyan
# Emplacements classiques d'ISCC.exe (Inno Setup 6)
$possibleIscc = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$ISCC = $possibleIscc | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ISCC) {
    throw "ISCC.exe introuvable. Installez Inno Setup 6 puis relancez."
}

# Compiler le script en passant le dossier dist
& $ISCC "/DSourceDir=$dist" "$iss"

Write-Host "Terminé. Le setup est généré dans: $dist (ex: $dist\Hardware_Monitor_Setup.exe)" -ForegroundColor Green