# Architecture

## Vue d'ensemble

```
            +---------------------------+
            |      Unreal Engine 5      |
            |  Cesium for Unreal (globe)|
            |  REST + WebSocket client  |
            +-------------+-------------+
                          |
                  +-------v--------+
                  |  FastAPI backend|
                  +--+-----------+--+
                     |           |
        +------------v---+   +---v-----------+
        | Traffic Worker |   |  Prediction   |
        | TraCI + SUMO   |   |  XGBoost      |
        +--------+-------+   +---------------+
                 |
        +--------v--------+   +-----------+  +-------+  +-------+
        | SUMO scenarios  |   | PostGIS   |  | Redis |  | MinIO |
        +-----------------+   +-----------+  +-------+  +-------+
```

## Description des composants mis en oeuvre (Milestone 1)

| Composant | Rôle dans le dépôt |
|-----------|--------------------|
| `data-pipeline/scripts/fetch_osm_network.py` | Extraction du réseau OWM par tuiles via l'API OpenStreetMap (fallback si Overpass est bloqué) |
| `netconvert` | Conversion OSM XML vers réseau SUMO |
| `simulation/sumo/scripts/generate_demand.py` | `randomTrips` + `duarouter` pour produire la demande |
| `simulation/sumo/scripts/run_scenario.py` | Génération des fichiers additionnels (fermetures, VSS pluie) et exécution SUMO |
| `simulation/sumo/scripts/export_metrics.py` | Parsing `edge_data.xml` + `tripinfo.xml` vers Parquet avec `data_mode=simulated` |
| `ai/traffic/src/train_xgboost.py` | Features temporelles, split chronologique, XGBoost vs baseline naïve |
| `backend/app/services/simulation_manager.py` | Simulation live SUMO dans un thread avec TraCI, snapshots à 1 Hz |
| `backend/app/services/traffic_store.py` | Accès aux Parquet, séries par segment |
| `backend/app/services/prediction_service.py` | Inférence XGBoost avec repli baseline naïve |

## Provenance des données

| Champ | Valeur | Signification |
|-------|--------|---------------|
| `data_mode` | `simulated` | Produit par SUMO, hypothèses expérimentales |
| `data_mode` | `predicted` | Produit par le modèle XGBoost |
| `data_mode` | `observed` | Réservé aux futures sources réelles (comptages, GPS autorisés) |

## Géoréférencement

- SUMO stocke le réseau en coordonnées locales UTM ; `sumolib.net.Net.convertXY2LonLat`
  reconstitue le WGS84 pour chaque véhicule.
- Un `edge_id` SUMO identifie le segment partout : Parquet, API, Unreal.
- Unreal convertit WGS84 vers ses coordonnées uniquement via `CesiumGeoreference`.

## Limites connues de la V1

- La demande de trafic est aléatoire (`randomTrips`) : pas de matrice OD réelle.
- Le modèle XGBoost est entraîné et évalué sur des données simulées uniquement.
- PostGIS/MinIO/Redis sont provisionnés par Docker Compose mais pas encore
  intégrés au code applicatif (état in-memory + Parquet).
- Un seul réseau pilot (Le Plateau) ; extension quartiers par quartiers.
