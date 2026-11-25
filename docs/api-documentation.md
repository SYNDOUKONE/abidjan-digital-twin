# API — documentation

La référence interactive complète est générée automatiquement par FastAPI :

- Swagger UI : `http://localhost:8000/docs`
- OpenAPI JSON : `http://localhost:8000/openapi.json`

## Conventions

- Toutes les réponses de trafic portent `data_mode` :
  - `simulated` : issu de SUMO (hypothèses expérimentales)
  - `predicted` : issu du modèle IA
- Erreurs : 404 ressource inconnue, 400 paramètre invalide, 503 SUMO indisponible.

## Endpoints

### `GET /health`
`{"status": "ok", "data_mode": "simulated", "version": "v1"}`

### `GET /api/v1/city/overview`
Résumé du district, des scénarios disponibles, segments surveillés, répartition
de la congestion.

### `GET /api/v1/traffic/edges`
Query : `scenario` (défaut `baseline`), `time` (défaut dernière période),
`congestion_level` (free|moderate|high), `limit` (défaut 500).
Retour : indicateurs par segment triés par nombre de véhicules.

### `GET /api/v1/traffic/vehicles`
Query : `simulation_id` (défaut : simulation active la plus récente).
Retour : liste des positions WGS84 (vide si aucune simulation live).

### `WS /api/v1/traffic/stream`
Envoie un snapshot JSON par seconde (véhicules + `edge_metrics`), ou un message
`{"status": "no_live_simulation"}`.

### `POST /api/v1/simulations`
Body : `{"scenario": "baseline", "duration_s": 600}` (durée 30..3600 s).
Réponse 202 avec `simulation_id`.

### `GET /api/v1/simulations/{id}`
État : `queued` / `running` / `completed` / `failed`, temps de simulation,
nombre de véhicules.

### `POST /api/v1/scenarios`
Body :

```json
{
  "name": "Fermeture bd Lagunaire",
  "base_scenario": "road_closure",
  "closed_edge_ids": ["1165426094#0"],
  "demand_scale": 1.0,
  "description": "Hypothèse expérimentale"
}
```

### `GET /api/v1/predictions/traffic`
Query : `edge_id` (URL-encodé, ex. `-1165426094%230`), `scenario`.
Retour : vitesse prédite à 15 min, niveau de congestion attendu, version du modèle.
