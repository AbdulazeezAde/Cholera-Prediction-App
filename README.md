# Cholera Risk Platform

Prototype weekly state-level cholera case forecasting and risk prediction for Nigeria.

## Current Data Contract

The active dataset is:

```text
data/raw/cholera_data.csv
```

For now this file contains the already-generated temporary unprocessed dataset. When the manually collected NCDC data is ready, replace this file with the real cleaned NCDC state-week data using the same filename. Do not add feature-engineered columns here; the pipeline creates those in `data/processed/modeling_dataset.csv`.

Required columns:

```text
state,year,epi_week,cases,deaths
```

`epi_week` may be a single week such as `10` or a reporting range such as `1-5` or `6-9`.

Column names are normalized case-insensitively, so `State` and `Cases` are accepted. Hyphenated state names such as `Akwa-Ibom`, `Cross-River`, and `Nassarawa` are normalized for map joins.

Accepted target column names:

```text
cases or suspected_cases
```

Optional CFR column:

```text
cfr
```

If `cfr` is missing, the pipeline computes it as `deaths / cases`.

If climate columns are not in `cholera_data.csv`, create `data/interim/climate_state_week.csv` with:

```text
state,year,epi_week,rainfall_mm,temperature_c,humidity_pct
```

WASH context variables can be collected from the free World Bank WDI Indicators API:

```bash
python -m cholera_forecast.wdi_api --start-year 2021 --end-year 2025
```

This writes:

```text
data/interim/wash_wdi_nigeria.csv
```

The file is merged automatically by `year` during processing. These are national annual Nigeria indicators, so they are useful contextual predictors but not state-week measurements. The pipeline forward-fills missing recent years because WDI indicators usually lag the current reporting year.

WDI WASH feature columns:

```text
basic_water_pct,safely_managed_water_pct,basic_sanitation_pct,safely_managed_sanitation_pct,open_defecation_pct
```

State-level WASHNORM profiles can be downloaded/scraped when UNICEF allows direct access:

```bash
python -m cholera_forecast.washnorm_api
```

This writes `data/interim/wash_state_year.csv`. If UNICEF blocks automated requests, the command writes an empty schema file and the pipeline continues with WDI WASH values. If you manually download the State WASH Profile PDF, run:

```bash
python -m cholera_forecast.washnorm_api --pdf data/raw/washnorm/washnorm_2021_state_profiles.pdf
```

Flood exposure is collected as rainfall-derived flood proxies and optional ReliefWeb flood report counts:

```bash
python -m cholera_forecast.flood_api --start-date 2021-01-01 --end-date 2025-12-31
```

This writes `data/interim/flood_state_week.csv`. If ReliefWeb blocks API access for the default app name, rainfall proxies are still written and `reliefweb_flood_reports` remains zero.

Displacement is collected from DTM when a subscription key is available, with a public UNHCR national fallback:

```bash
python -m cholera_forecast.displacement_api --start-year 2021 --end-year 2025
python -m cholera_forecast.displacement_api --start-year 2021 --end-year 2025 --dtm-subscription-key YOUR_KEY
```

This writes `data/interim/displacement_state_year.csv`. The UNHCR fallback is national and may not contain historical state-level values, so DTM Admin 1 data is preferred.

Health-system context is collected from the public GRID3/NHFR-derived ArcGIS service:

```bash
python -m cholera_forecast.health_api
```

This writes `data/interim/health_facility_state.csv` with total facility, hospital, and PHC counts by state.

State coordinates are also a dataset, not code. Keep them in:

```text
data/raw/state_coordinates.csv
```

Required columns:

```text
state,latitude,longitude
```

For the React map dashboard, add Nigeria state boundary polygons here:

```text
data/raw/nigeria_states.geojson
```

Download the default boundary file with:

```bash
python -m cholera_forecast.download_boundaries
```

The GeoJSON feature properties should include one of these state-name fields:

```text
state, NAME_1, name_1, name, State, admin1Name
```

## Project Stages

1. PDF extraction:
   ```bash
   python -m cholera_forecast.pdf_extraction --download --limit 5
   ```
   This stores PDFs in `data/raw/ncdc_cholera_reports/` and raw extracted table rows in `data/interim/cholera_extracted_raw.csv`.

2. NASA POWER climate collection:
   ```bash
   python -m cholera_forecast.climate_api --start 20210101 --end 20241231
   ```
   This writes daily and weekly climate variables for Nigerian state centroids.

3. World Bank WDI WASH collection:
   ```bash
   python -m cholera_forecast.wdi_api --start-year 2021 --end-year 2025
   ```
   This writes national annual water, sanitation, and open-defecation indicators used as contextual predictors.

4. Flood, displacement, WASHNORM, and health-system enrichment:
   ```bash
   python -m cholera_forecast.flood_api --start-date 2021-01-01 --end-date 2025-12-31
   python -m cholera_forecast.displacement_api --start-year 2021 --end-year 2025
   python -m cholera_forecast.health_api
   python -m cholera_forecast.washnorm_api
   ```

5. Data pipeline and feature engineering:
   ```bash
   python -m cholera_forecast.train_model
   ```
   This builds `data/processed/modeling_dataset.csv`, adds lag and rolling features, compares models, selects the best trained model, and writes forecasts.

## Model Outputs

- `outputs/metrics/model_comparison.csv`: naive baseline, moving average, RandomForest, XGBoost, and Prophet if installed.
- `outputs/metrics/validation_predictions.csv`: actual cases, predicted cases, actual risk, and predicted risk.
- `outputs/metrics/outlier_error_analysis.csv`: largest validation errors for outbreak-spike review.
- `outputs/metrics/best_model.json`: selected best trainable model.
- `models/best_model.joblib`: saved best model.
- `outputs/forecasts/latest_forecast.csv`: recursive 1-4 week forecasts and risk labels.

## Model Serving API

Start the API after training:

```bash
uvicorn cholera_forecast.api:app --reload
```

Routes:

- `GET /health`: service health check.
- `GET /model`: model artifact status, selected best model, and required feature columns.
- `GET /metrics`: model comparison metrics.
- `POST /predict`: predict one feature row.
- `POST /predict/batch`: predict multiple feature rows.
- `GET /forecast`: latest 1-4 week forecasts. Use `?state=Lagos` to filter or `?refresh=true` to regenerate.
- `GET /summary`: dashboard totals and latest state records.
- `GET /history`: historical rows. Use `?state=Lagos` to filter.
- `GET /boundaries`: serves `data/raw/nigeria_states.geojson` for the React map.
- `POST /reload`: clear cached model and dataset after retraining.

Example `POST /predict` body:

```json
{
  "state": "Lagos",
  "epi_week": 30,
  "epi_week_start": 30,
  "period_weeks": 1,
  "state_code": 24,
  "report_gap_weeks": 0,
  "month": 7,
  "quarter": 3,
  "rainy_season": 1,
  "rainfall_mm": 85.0,
  "temperature_c": 27.4,
  "humidity_pct": 82.0,
  "basic_water_pct": 82.25,
  "safely_managed_water_pct": 29.90,
  "basic_sanitation_pct": 47.90,
  "safely_managed_sanitation_pct": 32.21,
  "open_defecation_pct": 17.96,
  "rainfall_anomaly_mm": 12.4,
  "rainfall_zscore": 1.2,
  "heavy_rain_flag": 1,
  "extreme_rain_flag": 0,
  "rolling_4_rainfall_mm": 240.0,
  "reliefweb_flood_reports": 0,
  "idp_population": 0,
  "returnee_population": 0,
  "displacement_round": 0,
  "displacement_data_age_days": 365,
  "health_facility_count": 900,
  "hospital_count": 30,
  "phc_count": 760,
  "lag_1_cases": 20,
  "lag_2_cases": 16,
  "lag_4_cases": 12,
  "lag_8_cases": 8,
  "lag_1_deaths": 1,
  "lag_2_deaths": 0,
  "lag_4_deaths": 0,
  "lag_1_cfr": 0.05,
  "lag_2_cfr": 0.0,
  "lag_4_cfr": 0.0,
  "rolling_4_cases": 15.5,
  "rolling_8_cases": 11.2,
  "rolling_4_deaths": 0.25,
  "rolling_4_cfr": 0.0125
}
```

## React Dashboard

Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

The dashboard expects the FastAPI backend on `http://127.0.0.1:8000`. Override with:

```bash
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

The React dashboard includes:

- State choropleth map driven by `data/raw/nigeria_states.geojson`.
- Latest risk and case/death/CFR summary cards.
- Click-to-select map interaction for state forecasts.
- Epi-week/reporting-period filter using the periods present in the data.
- One-to-four week forecast panel.
- Case trend and forecast charts with uncertainty interval.
- Top 10 state risk summary on the second page.
