# Client Unreal Engine 5 — Abidjan Digital Twin

Les fichiers `.uproject`, `.umap` et `.uasset` se créent dans l'éditeur Unreal
Engine ; ce dossier documente la cible d'implémentation.

## Setup (Sprint 3)

1. Installer Unreal Engine 5.4+ avec Visual Studio 2022 (composants C++ + .NET).
2. Créer un projet Blank C++ nommé `AbidjanDigitalTwin` dans ce dossier.
3. Installer [Cesium for Unreal](https://cesium.com/platform/cesium-for-unreal/)
   depuis Fab ou le marketplace, activer le plugin dans `Edit > Plugins`.
4. Ajouter `CesiumGeoreference` + `Cesium3DTileset` (terrain et OSM Buildings)
   + `CesiumSunSky`.
5. Configurer la position d'origine sur le Plateau (lat 5.3217, lon -4.0206) et
   définir l'origine comme le centre du Plateau.
6. Créer un pion de navigation (Dynamic Pawn du quickstart Cesium).

## Architecture cible

| Classe | Responsabilité |
|--------|----------------|
| `ATrafficManager` | Interrogation backend, pooling des véhicules |
| `ATrafficVehicle` | Mesh instancé, interpolation 1 Hz |
| `ARoadSegment` | Couleur congestion (M_Road_Normal/Congested/Closed) |
| `ACityController` | Scène globale, géoréférencement Cesium |
| `UCesiumCoordinateService` | WGS84 vers coordonnées UE via `CesiumGeoreference` |
| `UBackendClient` | Client HTTP REST et WebSocket (module WebSockets UE) |
| `UScenarioManager` | POST scénarios/simulations, suivi de progression |
| `UTrafficHUD` | Indicateurs vitesse/congestion/scénario |

## Convention de coordonnées

- Backend / API : WGS84 (longitude, latitude), `edge_id` commun à tous les services.
- SUMO : coordonnées locales du réseau (déjà converties en WGS84 côté backend).
- Unreal : conversion via `CesiumGeoreference->TransformLongitudeLatitudeHeightToUnreal()`.

Ne jamais positionner les véhicules par une simple multiplication des longitudes
et latitudes par une constante.

## Consommation du flux

| Requête | Usage |
|---------|-------|
| `GET /api/v1/traffic/vehicles` | Snapshot initial |
| `WS /api/v1/traffic/stream` | Snapshots à 1 Hz |
| `POST /api/v1/simulations` | Démarrer une simulation |
| `GET /api/v1/simulations/{id}` | Progression |

Rejouer les véhicules avec interpolation (lerp) entre deux snapshots pour un
mouvement fluide à 60 FPS, et réutiliser (pooling) les instances au lieu de
créer/détruire des Actors.
