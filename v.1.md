# Hardware-Monitor — Notes de version

## Présentation
Outil de suivi des performances matérielles pour Windows, composé d’un service de capteurs (CPU, RAM, GPU, VRAM) et d’une interface graphique en temps réel.

## Binaires fournis
- **Hardware_Monitor_Setup.exe**: Installateur Windows (Inno Setup) qui déploie et configure le service de capteurs (PerformStatsSensorService).
- **HardwareMonitorUI.exe**: Application portable de l’interface graphique affichant les métriques exposées par le service local.

## Nouveautés / Points clés
- **API locale**: `http://127.0.0.1:9755/metrics`
- **Métriques**: charge et température CPU/GPU, utilisation RAM/VRAM (% et Go)
- **Interface**: thème sombre, rafraîchissement ~1s, jauges circulaires
- **Déploiement**: service Windows (ou tâche planifiée sans droits admin)

## Prérequis
- **OS**: Windows 10/11 64 bits
- **Droits**: admin recommandé pour installer le service comme Service Windows (sinon mode utilisateur)

## Installation
1. Exécuter `Hardware_Monitor_Setup.exe`.
2. Suivre l’assistant pour installer et démarrer le service.
3. Lancer `HardwareMonitorUI.exe` (ou via le raccourci créé).

## Utilisation
1. Vérifier que le service est démarré (port 9755).
2. Ouvrir `HardwareMonitorUI.exe` pour visualiser les métriques en temps réel.

## Vérifications rapides
- **Service actif**: `http://127.0.0.1:9755/metrics` doit renvoyer un JSON de métriques.
- **Pare-feu/Antivirus**: autoriser les exécutables si nécessaire.

## Problèmes connus
- **Données incomplètes**: si certains capteurs sont indisponibles, installer/lancer en admin et redémarrer le service.
- **Port bloqué**: s’assurer que le port local 9755 n’est pas filtré.

## Téléchargements
- Installateur: `Hardware_Monitor_Setup.exe`
- Interface portable: `HardwareMonitorUI.exe`

## Intégrité (recommandé)
Publiez les empreintes SHA256 des deux fichiers pour vérification utilisateur.