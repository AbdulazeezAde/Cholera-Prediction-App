from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .constants import FEATURE_COLUMNS, MODEL_DIR, MODELING_DATASET_PATH, OUTPUT_DIR, STATE_BOUNDARIES_PATH
from .data_pipeline import build_dataset
from .train_model import classify_prediction_risk, create_latest_forecast, robust_case_thresholds

MODEL_PATH = MODEL_DIR / "best_model.joblib"
BEST_MODEL_PATH = OUTPUT_DIR / "metrics" / "best_model.json"
METRICS_PATH = OUTPUT_DIR / "metrics" / "model_comparison.csv"
FORECAST_PATH = OUTPUT_DIR / "forecasts" / "latest_forecast.csv"

app = FastAPI(
    title="Cholera Risk Model API",
    version="1.0.0",
    description="Model-serving API for weekly Nigerian state-level cholera case forecasts and risk labels.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class FeaturePayload(BaseModel):
    epi_week: int = Field(..., ge=1, le=53)
    epi_week_start: int = Field(..., ge=1, le=53)
    period_weeks: int = Field(..., ge=1, le=53)
    state_code: float = Field(..., ge=0)
    report_gap_weeks: float = Field(..., ge=0)
    month: int = Field(..., ge=1, le=12)
    quarter: int = Field(..., ge=1, le=4)
    rainy_season: int = Field(..., ge=0, le=1)
    rainfall_mm: float = Field(..., ge=0)
    temperature_c: float
    humidity_pct: float = Field(..., ge=0, le=100)
    lag_1_cases: float = Field(..., ge=0)
    lag_2_cases: float = Field(..., ge=0)
    lag_4_cases: float = Field(..., ge=0)
    lag_8_cases: float = Field(..., ge=0)
    lag_1_deaths: float = Field(..., ge=0)
    lag_2_deaths: float = Field(..., ge=0)
    lag_4_deaths: float = Field(..., ge=0)
    lag_1_cfr: float = Field(..., ge=0)
    lag_2_cfr: float = Field(..., ge=0)
    lag_4_cfr: float = Field(..., ge=0)
    rolling_4_cases: float = Field(..., ge=0)
    rolling_8_cases: float = Field(..., ge=0)
    rolling_4_deaths: float = Field(..., ge=0)
    rolling_4_cfr: float = Field(..., ge=0)
    state: str | None = None


class BatchPredictionRequest(BaseModel):
    rows: list[FeaturePayload]


class PredictionResponse(BaseModel):
    predicted_cases: float
    risk_level: str
    model: str | None = None
    state: str | None = None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_model() -> Any:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Model artifact not found at {MODEL_PATH}. Run python -m cholera_forecast.train_model.")
    return joblib.load(MODEL_PATH)


@lru_cache(maxsize=1)
def load_dataset() -> pd.DataFrame:
    if MODELING_DATASET_PATH.exists():
        return pd.read_csv(MODELING_DATASET_PATH)
    return build_dataset()


def model_name() -> str | None:
    metadata = _read_json(BEST_MODEL_PATH)
    if not metadata:
        return None
    return metadata.get("best_model")


def payload_to_frame(payloads: list[FeaturePayload]) -> pd.DataFrame:
    rows = [payload.model_dump() for payload in payloads]
    frame = pd.DataFrame(rows)
    missing = [column for column in FEATURE_COLUMNS if column not in frame.columns]
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing feature columns: {missing}")
    return frame


def predict_payloads(payloads: list[FeaturePayload]) -> list[PredictionResponse]:
    try:
        model = load_model()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    dataset = load_dataset()
    frame = payload_to_frame(payloads)
    predictions = np.maximum(model.predict(frame[FEATURE_COLUMNS]), 0)
    return [
        PredictionResponse(
            predicted_cases=round(float(prediction), 2),
            risk_level=classify_prediction_risk(float(prediction), dataset["suspected_cases"]),
            model=model_name(),
            state=payload.state,
        )
        for payload, prediction in zip(payloads, predictions)
    ]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/model")
def get_model_status() -> dict[str, Any]:
    return {
        "model_artifact": str(MODEL_PATH),
        "model_available": MODEL_PATH.exists(),
        "best_model": model_name(),
        "feature_columns": FEATURE_COLUMNS,
        "modeling_dataset": str(MODELING_DATASET_PATH),
        "modeling_dataset_available": MODELING_DATASET_PATH.exists(),
    }


@app.get("/metrics")
def get_model_metrics() -> list[dict[str, Any]]:
    if not METRICS_PATH.exists():
        raise HTTPException(status_code=404, detail="Model comparison metrics not found. Train the model first.")
    return pd.read_csv(METRICS_PATH).replace({np.nan: None}).to_dict(orient="records")


@app.get("/summary")
def get_summary() -> dict[str, Any]:
    dataset = load_dataset()
    latest = dataset.sort_values(["year", "epi_week"]).groupby("state").tail(1)
    total_cases = int(dataset["suspected_cases"].sum())
    total_deaths = int(dataset["deaths"].fillna(0).sum()) if "deaths" in dataset.columns else 0
    return {
        "rows": int(len(dataset)),
        "states": int(dataset["state"].nunique()),
        "years": [int(dataset["year"].min()), int(dataset["year"].max())],
        "total_cases": total_cases,
        "total_deaths": total_deaths,
        "cfr": float(total_deaths / total_cases) if total_cases else 0.0,
        "latest": latest.replace({np.nan: None}).to_dict(orient="records"),
    }


@app.get("/history")
def get_history(
    state: str | None = Query(default=None, description="Optional state filter, e.g. Lagos."),
) -> list[dict[str, Any]]:
    dataset = load_dataset().sort_values(["state", "year", "epi_week"])
    if state:
        dataset = dataset[dataset["state"].str.lower() == state.lower()]
        if dataset.empty:
            raise HTTPException(status_code=404, detail=f"No history rows found for state: {state}")
    columns = [
        "state",
        "year",
        "epi_week",
        "epi_week_label",
        "date",
        "suspected_cases",
        "deaths",
        "cfr",
        "risk_level",
        "rainfall_mm",
        "temperature_c",
        "humidity_pct",
    ]
    available_columns = [column for column in columns if column in dataset.columns]
    return dataset[available_columns].replace({np.nan: None}).to_dict(orient="records")


@app.get("/hotspots")
def get_hotspots(limit: int = Query(default=10, ge=1, le=37)) -> list[dict[str, Any]]:
    dataset = load_dataset().sort_values(["state", "year", "epi_week"])
    latest = dataset.groupby("state").tail(1).copy()
    low_threshold, high_threshold = robust_case_thresholds(dataset["suspected_cases"])
    forecast = pd.read_csv(FORECAST_PATH) if FORECAST_PATH.exists() else pd.DataFrame()
    first_forecast = (
        forecast[forecast["forecast_week"] == 1][["state", "predicted_cases", "risk_level"]]
        if not forecast.empty and {"state", "forecast_week", "predicted_cases", "risk_level"}.issubset(forecast.columns)
        else pd.DataFrame(columns=["state", "predicted_cases", "risk_level"])
    )
    latest = latest.merge(first_forecast, on="state", how="left", suffixes=("", "_forecast"))
    trend_delta = dataset.groupby("state")["suspected_cases"].apply(
        lambda series: float(series.tail(3).mean() - series.shift(3).tail(3).mean()) if len(series.dropna()) >= 4 else 0.0
    )
    latest["trend_delta"] = latest["state"].map(trend_delta).fillna(0)
    latest["risk_score"] = (
        latest["suspected_cases"].fillna(0) / max(high_threshold, 1)
        + latest["predicted_cases"].fillna(0) / max(high_threshold, 1)
        + latest["cfr"].fillna(0) * 4
        + (latest["trend_delta"].clip(lower=0) / max(high_threshold, 1))
    )
    latest["hotspot_reason"] = np.select(
        [
            latest["risk_level"].eq("High"),
            latest["predicted_cases"].fillna(0) >= high_threshold,
            latest["trend_delta"] > 0,
        ],
        [
            "Current cases exceed the trimmed high-risk threshold.",
            "Near-term forecast exceeds the trimmed high-risk threshold.",
            "Recent cases are rising versus the previous reporting periods.",
        ],
        default="Elevated risk score from recent cases, CFR, and forecast.",
    )
    columns = [
        "state",
        "year",
        "epi_week",
        "epi_week_label",
        "suspected_cases",
        "deaths",
        "cfr",
        "risk_level",
        "predicted_cases",
        "risk_level_forecast",
        "trend_delta",
        "risk_score",
        "hotspot_reason",
    ]
    return (
        latest.sort_values(["risk_score", "suspected_cases"], ascending=False)
        .head(limit)[columns]
        .replace({np.nan: None})
        .to_dict(orient="records")
    )


@app.get("/boundaries")
def get_state_boundaries() -> JSONResponse:
    if not STATE_BOUNDARIES_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"State boundary GeoJSON not found. Add it at {STATE_BOUNDARIES_PATH}.",
        )
    data = json.loads(STATE_BOUNDARIES_PATH.read_text(encoding="utf-8"))
    features = []
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        state_name = str(
            properties.get("state")
            or properties.get("NAME_1")
            or properties.get("name_1")
            or properties.get("name")
            or properties.get("State")
            or properties.get("admin1Name")
            or ""
        ).strip()
        if not state_name or state_name.lower() == "water body":
            continue
        if str(properties.get("name_0", "Nigeria")).lower() != "nigeria":
            continue
        features.append(feature)

    return JSONResponse(
        content={"type": "FeatureCollection", "features": features},
        media_type="application/geo+json",
    )


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: FeaturePayload) -> PredictionResponse:
    return predict_payloads([payload])[0]


@app.post("/predict/batch", response_model=list[PredictionResponse])
def predict_batch(payload: BatchPredictionRequest) -> list[PredictionResponse]:
    if not payload.rows:
        raise HTTPException(status_code=422, detail="rows must contain at least one feature row.")
    return predict_payloads(payload.rows)


@app.get("/forecast")
def get_forecast(
    state: str | None = Query(default=None, description="Optional state filter, e.g. Lagos."),
    refresh: bool = Query(default=False, description="Regenerate forecasts from the current model and dataset."),
) -> list[dict[str, Any]]:
    if refresh or not FORECAST_PATH.exists():
        try:
            forecast = create_latest_forecast(load_dataset(), load_model(), output_path=FORECAST_PATH)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    else:
        forecast = pd.read_csv(FORECAST_PATH)

    if state:
        forecast = forecast[forecast["state"].str.lower() == state.lower()]
        if forecast.empty:
            raise HTTPException(status_code=404, detail=f"No forecast rows found for state: {state}")
    return forecast.replace({np.nan: None}).to_dict(orient="records")


@app.post("/reload")
def reload_artifacts() -> dict[str, str]:
    load_model.cache_clear()
    load_dataset.cache_clear()
    return {"status": "reloaded"}
