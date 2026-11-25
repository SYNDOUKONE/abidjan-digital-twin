# Abidjan Digital Twin

Jumeau numérique 3D d'Abidjan : moteur de simulation de trafic **SUMO**, prévisions **XGBoost**, client 3D **Unreal Engine 5 + Cesium for Unreal**, backend **FastAPI**.

## Principe fondamental

Trois types de données, jamais mélangés :

| `data_mode` | Signification | Source |
|-------------|---------------|--------|
| `observed`  | Mesure réelle, autorisée | Comptages, GPS partenaires (à intégrer) |
| `predicted` | Sortie d'un modèle IA (horizon 15 min) | XGBoost sur données simulées |
| `simulated` | Résultat d'un scénario SUMO | Ce dépôt, tous les cas |

**Aucune donnée de ce dépôt ne représente le trafic réel d'Abidjan.** Le réseau OSM est réel ; la demande de véhicules et tous les indicateurs sont des hypothèses expérimentales.

## État actuel (Milestone 1)

- [x] Réseau OSM extrait (zone pilote : Le Plateau, 3514 nœuds / 771 ways highways) via l'API OpenStreetMap
- [x] Réseau SUMO généré avec `netconvert` (`simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml`)
- [x] Demande de trafic (~1000 véhicules, `randomTrips` + `duarouter`)
- [x] 5 scénarios simulés : `baseline`, `high_demand` (+20 %), `road_closure`, `accident`, `rain` (VSS ×0,7)
- [x] Dataset Parquet : 79 676 enregistrements / 1 390 segments (`data/processed/traffic_60s_*.parquet`)
- [x] Modèle XGBoost : horizon 15 min, **MAE 9.75 km/h vs baseline naïve 10.73 (−9,1 %)** (`ai/traffic/evaluation/`)
- [x] Backend FastAPI : REST + WebSocket, gestionnaire de simulation live (TraCI), service de prédiction
- [ ] Client Unreal Engine 5 (structure documentée dans `unreal/` — à construire dans l'éditeur)

## Démarrage rapide

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                    # backend + data-pipeline
uvicorn backend.app.main:app --reload
# http://localhost:8000/docs
```

### SUMO headless sans environnement graphique

Si `libX11.so.6` est absent (serveur, conteneur minimal) :

```bash
sudo apt install libx11-6 libxext6 libxrender1 libgl1   # Debian/Ubuntu
```

### Pipeline complet de bout en bout

```bash
# 1. Réseau OSM (tuiles de 0.005° via l'API OSM officielle)
python data-pipeline/scripts/fetch_osm_network.py \
    --bbox 5.330 -4.040 5.310 -4.000 --out data/raw/abidjan_pilot.osm.xml

# 2. Conversion SUMO
netconvert --osm-files data/raw/abidjan_pilot.osm.xml \
    --output-file simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
    --geometry.remove true --ramps.guess true --junctions.join true \
    --tls.guess-signals true --tls.discard-simple true --tls.join true

# 3. Demande de véhicules
python simulation/sumo/scripts/generate_demand.py \
    --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
    --outdir simulation/sumo/abidjan_pilot/demand --period 3.5

# 4. Scénarios (baseline, high_demand, road_closure, accident, rain)
for s in baseline high_demand road_closure accident rain; do
python simulation/sumo/scripts/run_scenario.py --scenario $s \
    --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
    --routes simulation/sumo/abidjan_pilot/demand/vehicles.rou.xml
done

# 5. Export Parquet
python simulation/sumo/scripts/export_metrics.py \
    --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml \
    --scenarios-root simulation/sumo/scenarios --out data/processed

# 6. Entraînement XGBoost
python ai/traffic/src/train_xgboost.py \
    --dataset data/processed/traffic_60s_all.parquet \
    --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml
```

### Infrastructure (optionnel, Docker)

```bash
cp .env.example .env   # puis adapter
docker compose up -d   # PostGIS + Redis + MinIO + backend
```

## Voir le projet

Visuels générés depuis les données du pilot (dossier [`docs/visuals/`](docs/visuals/)) :

- [`congestion_baseline.png`](docs/visuals/congestion_baseline.png) — carte du réseau teintée par niveau de congestion (5 scénarios disponibles)
- [`traffic_animation.gif`](docs/visuals/traffic_animation.gif) — replay animé de la circulation SUMO sur 6 minutes
- [`scenario_comparison.png`](docs/visuals/scenario_comparison.png) — comparaison de la congestion et des volumes entre scénarios

Régénérer : `python visualization/render_visuals.py --net simulation/sumo/abidjan_pilot/network/abidjan_pilot.net.xml [--animation]`

## API (extrait)

| Méthode | Endpoint | Fonction |
|---------|----------|----------|
| GET | `/health` | Santé du backend |
| GET | `/api/v1/city/overview` | Statistiques générales |
| GET | `/api/v1/traffic/status` | État de la simulation live |
| GET | `/api/v1/traffic/edges?scenario=&congestion_level=` | Indicateurs par segment |
| GET | `/api/v1/traffic/vehicles?simulation_id=` | Positions WGS84 des véhicules |
| WS  | `/api/v1/traffic/stream` | Flux de snapshots (1 s) |
| POST | `/api/v1/simulations` | Démarrer une simulation live |
| GET | `/api/v1/simulations/{id}` | Progression d'une simulation |
| POST | `/api/v1/scenarios` | Créer une définition de scénario |
| GET | `/api/v1/predictions/traffic?edge_id=` | Prévision IA à 15 min |

Toutes les réponses portent un champ `data_mode` (`simulated` ou `predicted`).

## Structure du dépôt

```
abidjan-digital-twin/
├── data-pipeline/        # extraction OSM, conversion, scripts de préparation
├── simulation/sumo/      # réseau pilot, demande, scénarios SUMO, export métriques
├── ai/traffic/           # entraînement XGBoost, modèles, évaluation
├── backend/              # API FastAPI (REST + WebSocket)
├── unreal/               # documentation du client UE5 + Cesium (à construire dans l'éditeur)
├── infrastructure/       # Dockerfile backend, config services
└── docs/                 # architecture, dictionnaire de données, roadmap
```

## Licences et données

- Code : MIT (voir [LICENSE](LICENSE))
- Données OSM : (c) contributeurs d'[OpenStreetMap](https://www.openstreetmap.org/copyright), licence ODbL
- SUMO : EPL-2.0 — Unreal : licence Epic Games — Cesium for Unreal : Apache 2.0

## Prochaines étapes

Voir [docs/roadmap.md](docs/roadmap.md).
