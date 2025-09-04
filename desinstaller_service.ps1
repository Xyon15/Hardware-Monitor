<#
Désinstalle le service ou la tâche planifiée Hardware_Monitor
- Si Admin: arrête et supprime le service Windows, puis vérifie l'arrêt de l'API
- Sinon: stoppe et supprime la tâche planifiée, tente d'arrêter le processus, puis vérifie l'arrêt de l'API
#>

param(
    [string]$ServiceName = "Hardware_Monitor",
    [string]$ExePath = "C:\Hardware_Monitor\PerformStatsSensorService\PerformStatsSensorService.exe",
    [string]$MetricsUrl = "http://127.0.0.1:9755/metrics"
)

function Test-Admin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

function Wait-EndpointDown {
    param(
        [string]$Url,
        [int]$MaxWaitSec = 15
    )
    $deadline = (Get-Date).AddSeconds($MaxWaitSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -Method GET
            if ($resp.StatusCode -ne 200) { return $true }
        } catch {
            return $true
        }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

if (Test-Admin) {
    Write-Host "[Admin] Suppression du service Windows..."
    sc.exe stop $ServiceName 2>$null | Out-Null
    $down = Wait-EndpointDown -Url $MetricsUrl -MaxWaitSec 15
    if ($down) {
        Write-Host "[OK] L'API est arrêtée." -ForegroundColor Green
    } else {
        Write-Warning "L'API semble encore répondre après l'arrêt demandé."
    }
    sc.exe delete $ServiceName 2>$null | Out-Null
    Write-Host "Service supprimé (si présent): $ServiceName"
} else {
    Write-Host "[Utilisateur] Suppression de la tâche planifiée..."
    $taskName = $ServiceName
    # Tenter d'arrêter la tâche si elle existe
    schtasks /End /TN "$taskName" >$null 2>&1
    # Supprimer la tâche
    schtasks /Query /TN "$taskName" >$null 2>&1
    if ($LASTEXITCODE -eq 0) {
        schtasks /Delete /TN "$taskName" /F | Out-Null
        Write-Host "Tâche planifiée supprimée: $taskName"
    } else {
        Write-Host "Aucune tâche nommée $taskName trouvée."
    }
    # Si un binaire est en cours, tenter de le terminer par son chemin
    if (Test-Path $ExePath) {
        try {
            $procs = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $ExePath }
            if ($procs) {
                foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
                Write-Host "Processus arrêtés pour: $ExePath"
            }
        } catch { }
    }
    $down = Wait-EndpointDown -Url $MetricsUrl -MaxWaitSec 15
    if ($down) {
        Write-Host "[OK] L'API est arrêtée." -ForegroundColor Green
    } else {
        Write-Warning "L'API semble encore répondre. Assurez-vous qu'aucune autre instance ne tourne."
    }
}