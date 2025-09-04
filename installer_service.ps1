<#
Installe et démarre le service Hardware_Monitor
- Si exécuté en Admin: crée un service Windows
- Sinon: crée une tâche planifiée ONLOGON (niveau utilisateur)
#>

param(
    [string]$ExePath = "C:\Hardware_Monitor\PerformStatsSensorService\PerformStatsSensorService.exe",
    [string]$ServiceName = "Hardware_Monitor",
    [string]$DisplayName = "Hardware Monitor",
    [string]$Description = "Expose les métriques via HTTP en local sur http://127.0.0.1:9755/metrics"
)

function Test-Admin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

if (-not (Test-Path $ExePath)) {
    Write-Error "Binaire introuvable: $ExePath. Assurez-vous que l'application est installée."
    exit 1
}

if (Test-Admin) {
    Write-Host "[Admin] Installation du service Windows..."
    # Crée ou met à jour le service
    $existing = sc.exe query $ServiceName 2>$null | Select-String "$ServiceName" -Quiet
    if ($existing) {
        Write-Host "Service existe déjà. Arrêt et suppression avant recréation..."
        sc.exe stop $ServiceName 2>$null | Out-Null
        sc.exe delete $ServiceName 2>$null | Out-Null
        Start-Sleep -Seconds 1
    }
    sc.exe create $ServiceName binPath= '"' + $ExePath + '"' start= auto DisplayName= '"' + $DisplayName + '"' | Out-Null
    sc.exe description $ServiceName "$Description" | Out-Null
    sc.exe start $ServiceName | Out-Null
    Write-Host "Service installé et démarré: $ServiceName"
} else {
    Write-Host "[Utilisateur] Droits admin absents. Création d'une tâche planifiée ONLOGON..."
    $taskName = $ServiceName
    # Supprimer tâche existante si présente
    schtasks /Query /TN "$taskName" >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN "$taskName" /F >$null 2>&1
    }
    $quoted = '"' + $ExePath + '"'
    schtasks /Create /SC ONLOGON /RL LIMITED /TN "$taskName" /TR $quoted /F | Out-Null
    schtasks /Run /TN "$taskName" | Out-Null
    Write-Host "Tâche planifiée créée et lancée: $taskName"
}

Write-Host "Vérification de l'endpoint: http://127.0.0.1:9755/metrics"
# Attendre quelques secondes que l'app démarre
$maxWaitSec = 15
$deadline = (Get-Date).AddSeconds($maxWaitSec)
$ok = $false
while (-not $ok -and (Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9755/metrics" -UseBasicParsing -TimeoutSec 3 -Method GET
        if ($resp.StatusCode -eq 200) {
            $ok = $true
            break
        }
    } catch {
        Start-Sleep -Milliseconds 700
    }
}
if ($ok) {
    Write-Host "[OK] L'API répond (200)." -ForegroundColor Green
} else {
    Write-Warning "L'API ne répond pas encore. Réessayez dans quelques secondes: http://127.0.0.1:9755/metrics"
}