# Dictionnaire de données

## `data/processed/traffic_60s_*.parquet`

Une ligne = un segment (`edge_id`) sur une période de 60 s de simulation.

| Colonne | Type | Description |
|---------|------|-------------|
| `simulation_time_s` | float | Fin de la période dans la simulation |
| `interval_begin_s` | float | Début de la période |
| `interval_end_s` | float | Fin de la période |
| `edge_id` | str | Identifiant du segment SUMO (= OSM way transformé) |
| `mean_speed_m_s` | float | Vitesse moyenne des véhicules (m/s) |
| `mean_speed_kmh` | float | Vitesse moyenne (km/h) |
| `occupancy_pct` | float | Taux d'occupation des voies (%) |
| `vehicle_count` | int | Véhicules `departed + left` pendant la période |
| `sampled_vehicle_seconds` | float | Somme des secondes-véhicules observées |
| `free_flow_speed_kmh` | float | Vitesse libre du segment (réseau SUMO) |
| `speed_ratio` | float | `mean_speed_kmh / free_flow_speed_kmh` |
| `congestion_level` | str | `free` (ratio >= 0,7), `moderate` (>= 0,4), `high` (< 0,4) |
| `scenario_id` | str | Nom du scénario (baseline, high_demand, road_closure, accident, rain) |
| `source` | str | Toujours `sumo` dans la V1 |
| `data_mode` | str | Toujours `simulated` dans la V1 |
| `generated_at_utc` | str | Horodatage de l'export |

## Message snapshot (REST `/traffic/vehicles`, WS `/traffic/stream`)

| Champ | Description |
|-------|-------------|
| `simulation_id` | Identifiant de la simulation live |
| `simulation_time` | Temps de simulation courant (s) |
| `data_mode` | `simulated` |
| `vehicle_count` | Nombre de véhicules actifs |
| `vehicles[].vehicle_id` | Identifiant du véhicule |
| `vehicles[].edge_id` | Segment courant |
| `vehicles[].longitude` / `latitude` | Position WGS84 |
| `vehicles[].heading_deg` | Cap en degrés |
| `vehicles[].speed_kmh` | Vitesse instantanée |
| `edge_metrics[]` | Indicateurs par segment actif (vitesse, congestion) |

## Réponse prédiction (`GET /api/v1/predictions/traffic`)

| Champ | Description |
|-------|-------------|
| `edge_id` | Segment concerné |
| `prediction_horizon_minutes` | 15 |
| `predicted_speed_kmh` | Vitesse moyenne prédite |
| `predicted_congestion` | free / moderate / high |
| `data_mode` | `predicted` |
| `model_version` | Ex. `traffic-xgb-v1` ou `naive-persistence-v1` |

## Qualité des sources (futur, niveau 3)

| Champ | Description |
|-------|-------------|
| `source_id` / `source_name` | Identité de la source |
| `collection_timestamp` | Date de collecte |
| `geographic_coverage` | Zone couverte |
| `temporal_resolution` | Résolution temporelle |
| `license` | Licence d'utilisation |
| `data_mode` | `observed` |
| `quality_status` | brut / validé / rejeté |
