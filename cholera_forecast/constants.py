from __future__ import annotations

from pathlib import Path

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path("outputs")
MODEL_DIR = Path("models")

NCDC_REPORT_DIR = RAW_DIR / "ncdc_cholera_reports"
CHOLERA_DATA_PATH = RAW_DIR / "cholera_data.csv"
MODELING_DATASET_PATH = PROCESSED_DIR / "modeling_dataset.csv"
CLIMATE_DAILY_PATH = INTERIM_DIR / "climate_daily.csv"
CLIMATE_WEEKLY_PATH = INTERIM_DIR / "climate_state_week.csv"
WDI_WASH_PATH = INTERIM_DIR / "wash_wdi_nigeria.csv"
STATE_WASH_PATH = INTERIM_DIR / "wash_state_year.csv"
FLOOD_WEEKLY_PATH = INTERIM_DIR / "flood_state_week.csv"
DISPLACEMENT_PATH = INTERIM_DIR / "displacement_state_year.csv"
HEALTH_FACILITY_PATH = INTERIM_DIR / "health_facility_state.csv"
PDF_EXTRACTION_PATH = INTERIM_DIR / "cholera_extracted_raw.csv"
STATE_COORDINATES_PATH = RAW_DIR / "state_coordinates.csv"
STATE_BOUNDARIES_PATH = RAW_DIR / "nigeria_states.geojson"

NCDC_CHOLERA_URL = "https://ncdc.gov.ng/diseases/sitreps/?cat=7&name=An+update+of+Cholera+outbreak+in+Nigeria"

CHOLERA_REQUIRED_COLUMNS = {"state", "year", "epi_week"}

CLIMATE_COLUMNS = ["rainfall_mm", "temperature_c", "humidity_pct"]
WASH_COLUMNS = [
    "basic_water_pct",
    "safely_managed_water_pct",
    "basic_sanitation_pct",
    "safely_managed_sanitation_pct",
    "open_defecation_pct",
]
FLOOD_COLUMNS = [
    "rainfall_anomaly_mm",
    "rainfall_zscore",
    "heavy_rain_flag",
    "extreme_rain_flag",
    "rolling_4_rainfall_mm",
    "reliefweb_flood_reports",
]
DISPLACEMENT_COLUMNS = [
    "idp_population",
    "returnee_population",
    "displacement_round",
    "displacement_data_age_days",
]
HEALTH_FACILITY_COLUMNS = [
    "health_facility_count",
    "hospital_count",
    "phc_count",
]

FEATURE_COLUMNS = [
    "epi_week",
    "epi_week_start",
    "period_weeks",
    "state_code",
    "report_gap_weeks",
    "month",
    "quarter",
    "rainy_season",
    "rainfall_mm",
    "temperature_c",
    "humidity_pct",
    "basic_water_pct",
    "safely_managed_water_pct",
    "basic_sanitation_pct",
    "safely_managed_sanitation_pct",
    "open_defecation_pct",
    "rainfall_anomaly_mm",
    "rainfall_zscore",
    "heavy_rain_flag",
    "extreme_rain_flag",
    "rolling_4_rainfall_mm",
    "reliefweb_flood_reports",
    "idp_population",
    "returnee_population",
    "displacement_round",
    "displacement_data_age_days",
    "health_facility_count",
    "hospital_count",
    "phc_count",
    "lag_1_cases",
    "lag_2_cases",
    "lag_4_cases",
    "lag_8_cases",
    "lag_1_deaths",
    "lag_2_deaths",
    "lag_4_deaths",
    "lag_1_cfr",
    "lag_2_cfr",
    "lag_4_cfr",
    "rolling_4_cases",
    "rolling_8_cases",
    "rolling_4_deaths",
    "rolling_4_cfr",
]


def ensure_directories() -> None:
    for directory in [RAW_DIR, INTERIM_DIR, PROCESSED_DIR, OUTPUT_DIR, MODEL_DIR, NCDC_REPORT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
