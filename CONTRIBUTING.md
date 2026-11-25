# Contribuer

## Branches

| Branche | Usage |
|---------|-------|
| `main` | Versions stables |
| `develop` | Intégration |
| `feature/data-pipeline` | Collecte et traitement |
| `feature/sumo-simulation` | Simulation routière |
| `feature/traffic-ai` | Modèles IA |
| `feature/unreal-city` | Ville 3D |
| `feature/api-integration` | Communication |

## Règles

- Tout commit relatif à la simulation doit préserver le champ `data_mode`
  (`observed`, `predicted`, `simulated`) : ne jamais présenter une donnée
  simulée comme observée.
- Les paramètres de demande (valeurs de `period`, `scale`, VSS) sont des
  hypothèses expérimentales, documentées dans le message de commit.
- Les fichiers Unreal (`.uasset`, `.umap`) ne sont jamais édités à la main ;
  les dossiers `Intermediate/`, `Saved/`, `Binaries/`, `DerivedDataCache/`
  restent ignorés par Git.
- Les PR doivent passer `pytest`.
