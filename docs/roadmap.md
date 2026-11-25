# Roadmap

## Fait (Milestone 1)

- Réseau OSM du Plateau extrait et converti en réseau SUMO valide.
- 5 scénarios SUMO exécutés (baseline, high_demand, road_closure, accident, rain).
- Dataset Parquet 60 s / segment avec congestion et provenance.
- Modèle XGBoost horizon 15 min, meilleur que la baseline naïve (MAE −9,1 %).
- Backend FastAPI : REST + WebSocket, simulation live TraCI, prédictions IA.
- Tests pytest (13) + smoke test d'intégration serveur complet.

## Milestone 2 — Données et calibration

1. Étendre l'extraction OSM (Treichville, Adjamé, Cocody) quartier par quartier.
2. Charger le réseau dans PostGIS, exposer `GET /api/v1/city/edges` géomatique.
3. Stocker les runs SUMO dans MinIO (Parquet + configs), historisation.
4. Obtenir une première source `observed` (comptages municipaux ou e-Fares GTFS~)
   et calibrer le `speed_ratio` par type de route.
5. Implémenter `real_observations/` dans la qualité de données (docs/data-dictionary).

## Milestone 3 — Client Unreal

1. Projet UE5 + Cesium for Unreal, géoréférencement sur le Plateau.
2. `UBackendClient` HTTP/WS consommation des snapshots 1 Hz.
3. Pooling et instancing des véhicules (cible : 1 000 véhicules fluides).
4. Matériaux de congestion par `edge_id`.
5. Scenario Lab : lancer baseline / fermeture depuis l'UI UE.

## Milestone 4 — IA avancée

1. Comparer LSTM vs XGBoost sur le même split chronologique.
2. ST-GCN exploitant le graphe du réseau (adjacence `edge_id`).
3. Court terme : Multi-horizons 5/15/30/60 min.
4. Évaluation systématique MAE/RMSE par type de route et heure.
