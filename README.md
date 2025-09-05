# Hardware-Monitor

**Version actuelle**: v1.1

## Description
Hardware-Monitor est un outil de surveillance des performances matérielles pour Windows. Il permet de visualiser en temps réel les métriques système telles que l'utilisation du CPU, de la RAM, du GPU et de la VRAM, ainsi que leurs températures.

## Fonctionnalités
- Surveillance en temps réel des performances matérielles
- Affichage des métriques CPU (charge, température)
- Affichage des métriques RAM (utilisation en % et Go)
- Affichage des métriques GPU (charge, température)
- Affichage des métriques VRAM (utilisation en % et Go)
- Interface graphique avec thème sombre
- Service Windows fonctionnant en arrière-plan

## Architecture
Le projet se compose de deux parties principales :
1. **Service de capteurs** (C# / .NET 8.0) - Collecte les données matérielles et les expose via une API HTTP locale
2. **Interface graphique** (Python 3.10+ / PySide6) - Affiche les métriques en temps réel avec des indicateurs visuels

## Prérequis
- Windows 10/11
- .NET 8.0 Runtime
- Python 3.10+ (pour l'interface graphique)
- Droits administrateur (pour l'installation du service)

## Installation

### Option 1 : Installateur
Utilisez l'installateur Windows fourni dans les releases :
1. Téléchargez le dernier fichier .exe depuis la section Releases (version v1.1)
2. Exécutez l'installateur et suivez les instructions

### Option 2 : Installation manuelle
```powershell
# Compiler le service
dotnet publish PerformStatsSensorService\PerformStatsSensorService.csproj -c Release -r win-x64 --self-contained true

# Installer le service Windows
.\installer_service.ps1

# Installer les dépendances Python
pip install PySide6
```

## Utilisation
1. Le service démarre automatiquement après l'installation
2. Lancez l'interface graphique via le raccourci du menu Démarrer ou en exécutant :
   ```
   python performance_gui.py
   ```
3. L'interface affiche les métriques système en temps réel avec une mise à jour chaque seconde

## Désinstallation
```powershell
.\desinstaller_service.ps1
```

## Développement

### Compilation du service
```powershell
dotnet build PerformStatsSensorService\PerformStatsSensorService.csproj
```

### Création de l'installateur
```powershell
.\build_installer.ps1 -Configuration Release -Runtime win-x64
```

### API du service
Le service expose une API HTTP locale accessible à l'adresse :
```
http://127.0.0.1:9755/metrics
```

## Technologies utilisées
- C# / .NET 8.0
- LibreHardwareMonitor (LibreHardwareMonitorLib 0.9.3)
- ASP.NET Core pour l'API REST
- Python 3.10+ avec PySide6
- Inno Setup pour l'installateur Windows
