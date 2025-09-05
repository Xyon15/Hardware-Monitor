# Hardware-Monitor — Notes de version v1.1

## Résumé
Cette version améliore la fiabilité des métriques CPU/GPU et met à jour l’installateur. Elle corrige notamment l’absence de température CPU sur certaines machines et facilite l’exécution du service dans la session utilisateur (recommandé pour les capteurs GPU).

## Modifications principales
- **Service (PerformStatsSensorService)**
  - **Activation des capteurs carte mère (Super I/O)** pour récupérer la température CPU lorsque non exposée directement par le nœud CPU.
  - **Fallback température CPU via Motherboard**: scan des capteurs `Temperature` sous `Motherboard` (noms contenant `CPU`, `Package`, `Tctl`, `Tdie`, `Die`) avec sélection du meilleur candidat.
  - **Lecture GPU/VRAM**: logique conservée avec amélioration de robustesse (mise à jour des sous-capteurs, compatibilité NVIDIA/AMD/Intel).
  - **Fréquence de rafraîchissement**: cache interne avec intervalle minimal de 500ms pour limiter la charge.

- **Scripts d’installation**
  - `installer_service.ps1` et `desinstaller_service.ps1` utilisables avec un chemin d’exécutable personnalisé via `-ExePath`.
  - Recommandation d’installation en **tâche planifiée utilisateur (sans Admin)** pour de meilleures métriques GPU (certains drivers ne remontent pas les capteurs en Session 0/service Windows).

- **Installateur (Inno Setup)**
  - Reconstruction complète de l’installateur: `dist/Hardware_Monitor_Setup.exe`.
  - Copie des ressources OpenHardwareMonitor et des scripts d’aide dans le dossier d’installation (`C:\Hardware_Monitor`).

## Chemins et binaires
- **EXE service publié (référence)**: `c:\Dev\Hardware-Monitor\out\PerformStatsSensorService\PerformStatsSensorService.exe`
- **Installateur généré**: `c:\Dev\Hardware-Monitor\dist\Hardware_Monitor_Setup.exe`

## Conseils d’installation
- Pour des capteurs GPU fiables:
  1. Désinstaller le service s’il est installé comme Service Windows:
     ```powershell
     Set-Location "c:\Dev\Hardware-Monitor"
     .\desinstaller_service.ps1
     ```
  2. Installer le service comme **tâche planifiée utilisateur** en pointant vers l’EXE installé ou celui du repo:
     ```powershell
     .\installer_service.ps1 -ExePath "c:\Dev\Hardware-Monitor\out\PerformStatsSensorService\PerformStatsSensorService.exe"
     ```

## Vérifications rapides
- Santé de l’API:
  ```powershell
  Invoke-WebRequest http://127.0.0.1:9755/healthz -UseBasicParsing
  ```
- Métriques courantes:
  ```powershell
  Invoke-WebRequest http://127.0.0.1:9755/metrics -UseBasicParsing
  ```
- Diagnostic capteurs (noms/types/valeurs):
  ```powershell
  Invoke-WebRequest http://127.0.0.1:9755/sensors -UseBasicParsing
  ```

## Changements de code notables
- `PerformStatsSensorService/Program.cs`
  - `IsMotherboardEnabled = true` pour activer la lecture Super I/O.
  - Nouveau bloc de fallback sur `HardwareType.Motherboard` pour dériver `cpu.temp_c`.

## Problèmes connus
- Certains pilotes GPU ne remontent pas toutes les valeurs en mode service Windows. Préférez l’exécution en session utilisateur.
- Les noms de capteurs peuvent varier selon les cartes mères/CPU: la logique couvre les cas les plus fréquents mais peut nécessiter des ajustements mineurs.

## Divers
- L’interface `performance_gui.py` affichera désormais correctement la température CPU si le service l’expose via l’un des chemins supportés.
