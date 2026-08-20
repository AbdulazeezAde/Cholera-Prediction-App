from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import ParameterSampler

from .constants import FEATURE_COLUMNS, MODEL_DIR, OUTPUT_DIR
from .data_pipeline import build_dataset


class CaseCountModel(BaseEstimator, RegressorMixin):
    def __init__(
        self,
        base_model: Any | None = None,
        target_mode: str = "log_cases",
        target_cap_quantile: float | None = None,
    ):
        self.base_model = base_model
        self.target_mode = target_mode
        self.target_cap_quantile = target_cap_quantile

    def fit(self, features: pd.DataFrame, target: pd.Series | np.ndarray) -> "CaseCountModel":
        if self.base_model is None:
            self.base_model_ = RandomForestRegressor(random_state=42, n_jobs=-1)
        else:
            self.base_model_ = clone(self.base_model)
        y = np.asarray(target, dtype=float)
        period_weeks = np.asarray(features["period_weeks"].clip(lower=1), dtype=float)
        self.target_cap_ = None
        if self.target_mode in {"rate", "log_rate"}:
            y = y / period_weeks
        if self.target_cap_quantile is not None:
            self.target_cap_ = float(np.quantile(y, self.target_cap_quantile))
            y = np.minimum(y, self.target_cap_)
        if self.target_mode in {"log_cases", "log_rate"}:
            y = np.log1p(y)
        self.base_model_.fit(features, y)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        predictions = np.asarray(self.base_model_.predict(features), dtype=float)
        if self.target_mode in {"log_cases", "log_rate"}:
            predictions = np.expm1(predictions)
        if self.target_mode in {"rate", "log_rate"}:
            predictions = predictions * np.asarray(features["period_weeks"].clip(lower=1), dtype=float)
        return np.maximum(predictions, 0)


def prepare_training_frame(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    frame = dataset.dropna(subset=FEATURE_COLUMNS + ["suspected_cases"]).copy()
    X = frame[FEATURE_COLUMNS]
    y = frame["suspected_cases"]
    return X, y


def time_based_split(dataset: pd.DataFrame, test_fraction: float = 0.2) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = dataset.dropna(subset=FEATURE_COLUMNS + ["suspected_cases"]).copy()
    frame = frame.sort_values(["year", "epi_week", "state"]).reset_index(drop=True)
    periods = frame[["year", "epi_week"]].drop_duplicates().sort_values(["year", "epi_week"]).reset_index(drop=True)
    split_index = max(1, int(len(periods) * (1 - test_fraction)))
    split_index = min(split_index, len(periods) - 1)
    train_periods = periods.iloc[:split_index]
    test_periods = periods.iloc[split_index:]
    train_keys = set(zip(train_periods["year"], train_periods["epi_week"]))
    test_keys = set(zip(test_periods["year"], test_periods["epi_week"]))
    train_mask = [key in train_keys for key in zip(frame["year"], frame["epi_week"])]
    test_mask = [key in test_keys for key in zip(frame["year"], frame["epi_week"])]
    return frame[train_mask].copy(), frame[test_mask].copy()


def expanding_time_splits(dataset: pd.DataFrame, n_splits: int = 3) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    frame = dataset.dropna(subset=FEATURE_COLUMNS + ["suspected_cases"]).copy()
    frame = frame.sort_values(["year", "epi_week", "state"]).reset_index(drop=True)
    periods = frame[["year", "epi_week"]].drop_duplicates().sort_values(["year", "epi_week"]).reset_index(drop=True)
    if len(periods) < n_splits + 2:
        return [time_based_split(frame)]

    fold_size = max(1, len(periods) // (n_splits + 1))
    splits: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    for fold in range(n_splits):
        train_end = len(periods) - (n_splits - fold) * fold_size
        test_end = min(train_end + fold_size, len(periods))
        if train_end <= 0 or test_end <= train_end:
            continue
        train_periods = periods.iloc[:train_end]
        test_periods = periods.iloc[train_end:test_end]
        train_keys = set(zip(train_periods["year"], train_periods["epi_week"]))
        test_keys = set(zip(test_periods["year"], test_periods["epi_week"]))
        train_df = frame[[key in train_keys for key in zip(frame["year"], frame["epi_week"])]].copy()
        test_df = frame[[key in test_keys for key in zip(frame["year"], frame["epi_week"])]].copy()
        if not train_df.empty and not test_df.empty:
            splits.append((train_df, test_df))
    return splits or [time_based_split(frame)]


def chronological_cv_indices(frame: pd.DataFrame, n_splits: int = 3) -> list[tuple[np.ndarray, np.ndarray]]:
    ordered = frame.sort_values(["year", "epi_week", "state"]).reset_index(drop=True)
    splits = expanding_time_splits(ordered, n_splits=n_splits)
    cv: list[tuple[np.ndarray, np.ndarray]] = []
    for train_df, test_df in splits:
        train_indices = ordered.index[
            ordered[["state", "year", "epi_week"]]
            .apply(tuple, axis=1)
            .isin(train_df[["state", "year", "epi_week"]].apply(tuple, axis=1))
        ].to_numpy()
        test_indices = ordered.index[
            ordered[["state", "year", "epi_week"]]
            .apply(tuple, axis=1)
            .isin(test_df[["state", "year", "epi_week"]].apply(tuple, axis=1))
        ].to_numpy()
        if len(train_indices) and len(test_indices):
            cv.append((train_indices, test_indices))
    return cv


def smape(y_true: pd.Series | np.ndarray, y_pred: np.ndarray) -> float:
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    denominator = np.abs(y_true_arr) + np.abs(y_pred_arr)
    denominator = np.where(denominator == 0, 1, denominator)
    return float(np.mean(2 * np.abs(y_pred_arr - y_true_arr) / denominator) * 100)


def regression_metrics(y_true: pd.Series | np.ndarray, predictions: np.ndarray) -> dict[str, float]:
    clipped = np.maximum(np.asarray(predictions, dtype=float), 0)
    return {
        "mae": float(mean_absolute_error(y_true, clipped)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, clipped))),
        "smape": smape(y_true, clipped),
        "r2": float(r2_score(y_true, clipped)),
    }


def make_xgboost() -> Any | None:
    try:
        from xgboost import XGBRegressor
    except Exception:
        return None
    return XGBRegressor(
        n_estimators=160,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.85,
        colsample_bytree=0.85,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=2,
    )


def candidate_models() -> dict[str, Any]:
    models: dict[str, Any] = {
        "random_forest": RandomForestRegressor(
            n_estimators=180,
            max_depth=12,
            random_state=42,
            n_jobs=-1,
        )
    }
    xgboost = make_xgboost()
    if xgboost is not None:
        models["xgboost"] = xgboost
    return models


def candidate_estimators() -> dict[str, CaseCountModel]:
    estimators: dict[str, CaseCountModel] = {
        "random_forest": CaseCountModel(
            base_model=RandomForestRegressor(
                n_estimators=180,
                max_depth=12,
                random_state=42,
                n_jobs=-1,
            ),
            target_mode="log_cases",
        )
    }
    xgboost = make_xgboost()
    if xgboost is not None:
        estimators["xgboost"] = CaseCountModel(base_model=xgboost, target_mode="log_cases")
    return estimators


def randomized_search_spaces() -> dict[str, dict[str, list[Any]]]:
    spaces: dict[str, dict[str, list[Any]]] = {
        "random_forest": {
            "target_mode": ["log_cases", "log_rate"],
            "target_cap_quantile": [None, 0.98, 0.99],
            "base_model__n_estimators": [180, 300, 450, 650],
            "base_model__max_depth": [6, 10, 14, None],
            "base_model__min_samples_leaf": [1, 2, 4, 6],
            "base_model__min_samples_split": [2, 5, 10],
            "base_model__max_features": ["sqrt", 0.55, 0.75, 1.0],
        }
    }
    if make_xgboost() is not None:
        spaces["xgboost"] = {
            "target_mode": ["log_cases", "log_rate"],
            "target_cap_quantile": [None, 0.98, 0.99],
            "base_model__n_estimators": [120, 180, 260, 360, 500],
            "base_model__learning_rate": [0.015, 0.03, 0.05, 0.08],
            "base_model__max_depth": [2, 3, 4, 5],
            "base_model__min_child_weight": [1, 3, 6, 10],
            "base_model__subsample": [0.65, 0.8, 0.9, 1.0],
            "base_model__colsample_bytree": [0.65, 0.8, 0.9, 1.0],
            "base_model__reg_alpha": [0, 0.05, 0.2, 0.8],
            "base_model__reg_lambda": [1, 3, 8, 15],
            "base_model__gamma": [0, 0.1, 0.5, 1.0],
        }
    return spaces


def robust_case_thresholds(historical_cases: pd.Series) -> tuple[float, float]:
    cases = pd.to_numeric(historical_cases, errors="coerce").dropna()
    if cases.empty:
        return 5.0, 25.0
    q1 = cases.quantile(0.25)
    q3 = cases.quantile(0.75)
    upper_fence = q3 + (1.5 * (q3 - q1))
    trimmed = cases[cases <= upper_fence]
    if trimmed.empty:
        trimmed = cases
    q50 = float(trimmed.quantile(0.50))
    q75 = float(trimmed.quantile(0.75))
    if pd.isna(q50) or pd.isna(q75) or q50 == q75:
        return 5.0, 25.0
    return q50, q75


def prophet_predictions(train_df: pd.DataFrame, test_df: pd.DataFrame) -> np.ndarray | None:
    try:
        from prophet import Prophet
    except Exception:
        return None

    predictions = pd.Series(index=test_df.index, dtype=float)
    for state, state_test in test_df.groupby("state"):
        state_train = train_df[train_df["state"] == state][["date", "suspected_cases"]].dropna()
        if len(state_train) < 12:
            continue
        prophet_train = state_train.rename(columns={"date": "ds", "suspected_cases": "y"})
        model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        model.fit(prophet_train)
        future = state_test[["date"]].rename(columns={"date": "ds"})
        forecast = model.predict(future)
        predictions.loc[state_test.index] = np.maximum(forecast["yhat"].to_numpy(), 0)

    if predictions.isna().any():
        fallback = test_df["rolling_4_cases"].fillna(test_df["lag_1_cases"])
        predictions = predictions.fillna(fallback)
    return predictions.to_numpy(dtype=float)


def classify_prediction_risk(predicted_cases: float, historical_cases: pd.Series) -> str:
    q50, q75 = robust_case_thresholds(historical_cases)
    if predicted_cases < q50:
        return "Low"
    if predicted_cases < q75:
        return "Medium"
    return "High"


def fit_case_model(model: Any, X_train: pd.DataFrame, y_train: pd.Series) -> CaseCountModel:
    if isinstance(model, CaseCountModel):
        estimator = clone(model)
    else:
        estimator = CaseCountModel(base_model=model, target_mode="log_cases", target_cap_quantile=0.98)
    estimator.fit(X_train, y_train)
    return estimator


def evaluate_estimator_cv(
    estimator: CaseCountModel,
    dataset: pd.DataFrame,
    splits: list[tuple[pd.DataFrame, pd.DataFrame]] | None = None,
) -> dict[str, float]:
    rows = []
    for train_df, test_df in splits or expanding_time_splits(dataset):
        fitted = clone(estimator)
        fitted.fit(train_df[FEATURE_COLUMNS], train_df["suspected_cases"])
        predictions = fitted.predict(test_df[FEATURE_COLUMNS])
        rows.append(regression_metrics(test_df["suspected_cases"], predictions))
    metrics = pd.DataFrame(rows)
    return {
        "folds": int(len(metrics)),
        "mae": float(metrics["mae"].mean()),
        "rmse": float(metrics["rmse"].mean()),
        "smape": float(metrics["smape"].mean()),
        "r2": float(metrics["r2"].mean()),
        "rmse_std": float(metrics["rmse"].std(ddof=0)),
    }


def randomized_cv_search(
    dataset: pd.DataFrame,
    n_iter: int = 16,
    random_state: int = 42,
) -> tuple[dict[str, CaseCountModel], pd.DataFrame]:
    tuned_estimators: dict[str, CaseCountModel] = {}
    search_rows: list[dict[str, object]] = []
    splits = expanding_time_splits(dataset)
    for model_name, estimator in candidate_estimators().items():
        space = randomized_search_spaces().get(model_name, {})
        sampled_params = list(ParameterSampler(space, n_iter=n_iter, random_state=random_state))
        default_params: dict[str, Any] = {}
        best_r2 = -np.inf
        best_rmse = np.inf
        best_estimator = clone(estimator)
        for search_index, params in enumerate([default_params, *sampled_params], start=1):
            candidate = clone(estimator)
            candidate.set_params(**params)
            metrics = evaluate_estimator_cv(candidate, dataset, splits=splits)
            row = {
                "model": model_name,
                "search_index": search_index,
                "params": json.dumps(params, sort_keys=True),
                **metrics,
            }
            search_rows.append(row)
            if metrics["r2"] > best_r2 or (np.isclose(metrics["r2"], best_r2) and metrics["rmse"] < best_rmse):
                best_r2 = metrics["r2"]
                best_rmse = metrics["rmse"]
                best_estimator = candidate
        tuned_estimators[model_name] = best_estimator
    return tuned_estimators, pd.DataFrame(search_rows)


def cross_validate_candidate_models(
    dataset: pd.DataFrame,
    tuned_estimators: dict[str, CaseCountModel] | None = None,
) -> pd.DataFrame:
    metric_rows: list[dict[str, object]] = []
    fold_predictions: dict[str, list[dict[str, float]]] = {}
    splits = expanding_time_splits(dataset)
    estimators = tuned_estimators or candidate_estimators()
    for fold_index, (train_df, test_df) in enumerate(splits, start=1):
        y_test = test_df["suspected_cases"]
        candidates: dict[str, np.ndarray] = {
            "naive_lag_1": test_df["lag_1_cases"].to_numpy(dtype=float),
            "moving_average_4_week": test_df["rolling_4_cases"].to_numpy(dtype=float),
        }
        for model_name, model in estimators.items():
            wrapped_model = fit_case_model(model, train_df[FEATURE_COLUMNS], train_df["suspected_cases"])
            candidates[model_name] = wrapped_model.predict(test_df[FEATURE_COLUMNS])
        prophet_preds = prophet_predictions(train_df, test_df)
        if prophet_preds is not None:
            candidates["prophet"] = prophet_preds

        for model_name, predictions in candidates.items():
            metrics = regression_metrics(y_test, predictions)
            fold_predictions.setdefault(model_name, []).append(metrics)
            metric_rows.append({"model": model_name, "fold": fold_index, **metrics})

    aggregate_rows = []
    for model_name, rows in fold_predictions.items():
        fold_metrics = pd.DataFrame(rows)
        status = "tuned_cv" if model_name in estimators.keys() else "evaluated_cv"
        aggregate_rows.append(
            {
                "model": model_name,
                "status": status,
                "folds": int(len(fold_metrics)),
                "mae": float(fold_metrics["mae"].mean()),
                "rmse": float(fold_metrics["rmse"].mean()),
                "smape": float(fold_metrics["smape"].mean()),
                "r2": float(fold_metrics["r2"].mean()),
                "rmse_std": float(fold_metrics["rmse"].std(ddof=0)),
            }
        )
    if "prophet" not in fold_predictions:
        aggregate_rows.append({"model": "prophet", "status": "skipped_missing_dependency", "folds": 0})
    return pd.DataFrame(aggregate_rows)


def train_and_compare_models(
    dataset: pd.DataFrame,
    tuning_iterations: int = 16,
) -> tuple[pd.DataFrame, pd.DataFrame, Any, str, pd.DataFrame]:
    tuned_estimators, search_results = randomized_cv_search(dataset, n_iter=tuning_iterations)
    metrics = cross_validate_candidate_models(dataset, tuned_estimators=tuned_estimators)
    train_df, test_df = time_based_split(dataset)
    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["suspected_cases"]
    X_test = test_df[FEATURE_COLUMNS]

    trained_models: dict[str, Any] = {}
    validation_predictions: dict[str, np.ndarray] = {}
    for model_name, model in tuned_estimators.items():
        wrapped_model = fit_case_model(model, X_train, y_train)
        predictions = wrapped_model.predict(X_test)
        trained_models[model_name] = wrapped_model
        validation_predictions[model_name] = predictions

    trained_metrics = metrics[metrics["model"].isin(trained_models.keys())].sort_values(
        ["r2", "rmse"],
        ascending=[False, True],
    )
    if trained_metrics.empty:
        raise RuntimeError("No trainable machine learning model was available.")
    best_model_name = str(trained_metrics.iloc[0]["model"])
    best_model = trained_models[best_model_name]

    best_predictions = validation_predictions[best_model_name]
    validation = test_df[["state", "year", "epi_week", "date", "suspected_cases", "risk_level"]].copy()
    validation = validation.rename(columns={"suspected_cases": "actual_cases", "risk_level": "actual_risk_level"})
    validation["predicted_cases"] = np.round(best_predictions, 2)
    validation["absolute_error"] = (validation["actual_cases"] - validation["predicted_cases"]).abs()
    validation["predicted_risk_level"] = [
        classify_prediction_risk(value, train_df["suspected_cases"]) for value in best_predictions
    ]
    validation["model"] = best_model_name
    return metrics, search_results, best_model, best_model_name, validation


def create_latest_forecast(
    dataset: pd.DataFrame,
    model: Any,
    horizon_weeks: int = 4,
    output_path: Path | None = None,
) -> pd.DataFrame:
    forecasts: list[dict[str, object]] = []
    history = dataset.sort_values(["state", "year", "epi_week"]).copy()
    state_codes = history.groupby("state")["state_code"].max().to_dict() if "state_code" in history.columns else {}
    for state, state_df in history.groupby("state"):
        case_history = list(state_df["suspected_cases"].astype(float))
        death_history = list(state_df.get("deaths", pd.Series([0] * len(state_df))).astype(float))
        cfr_history = list(state_df.get("cfr", pd.Series([0] * len(state_df))).astype(float))
        recent_cases = state_df["suspected_cases"].astype(float).tail(12)
        state_volatility = float(recent_cases.std()) if len(recent_cases) >= 2 else 0.0
        climate_recent = state_df[["rainfall_mm", "temperature_c", "humidity_pct"]].tail(4).mean()
        latest = state_df.iloc[-1]
        latest_date = pd.to_datetime(latest["date"])
        for step in range(1, horizon_weeks + 1):
            forecast_date = latest_date + pd.to_timedelta(step * 7, unit="D")
            iso = forecast_date.isocalendar()
            feature_row = pd.DataFrame(
                [
                    {
                        "epi_week": int(iso.week),
                        "epi_week_start": int(iso.week),
                        "period_weeks": 1,
                        "state_code": float(state_codes.get(state, 0)),
                        "report_gap_weeks": 0,
                        "month": forecast_date.month,
                        "quarter": forecast_date.quarter,
                        "rainy_season": int(forecast_date.month in [4, 5, 6, 7, 8, 9, 10]),
                        "rainfall_mm": climate_recent["rainfall_mm"],
                        "temperature_c": climate_recent["temperature_c"],
                        "humidity_pct": climate_recent["humidity_pct"],
                        "lag_1_cases": case_history[-1],
                        "lag_2_cases": case_history[-2] if len(case_history) >= 2 else case_history[-1],
                        "lag_4_cases": case_history[-4] if len(case_history) >= 4 else case_history[-1],
                        "lag_8_cases": case_history[-8] if len(case_history) >= 8 else case_history[-1],
                        "lag_1_deaths": death_history[-1],
                        "lag_2_deaths": death_history[-2] if len(death_history) >= 2 else death_history[-1],
                        "lag_4_deaths": death_history[-4] if len(death_history) >= 4 else death_history[-1],
                        "lag_1_cfr": cfr_history[-1],
                        "lag_2_cfr": cfr_history[-2] if len(cfr_history) >= 2 else cfr_history[-1],
                        "lag_4_cfr": cfr_history[-4] if len(cfr_history) >= 4 else cfr_history[-1],
                        "rolling_4_cases": float(np.mean(case_history[-4:])),
                        "rolling_8_cases": float(np.mean(case_history[-8:])),
                        "rolling_4_deaths": float(np.mean(death_history[-4:])),
                        "rolling_4_cfr": float(np.mean(cfr_history[-4:])),
                    }
                ]
            )
            for column in FEATURE_COLUMNS:
                if column not in feature_row.columns:
                    feature_row[column] = latest[column] if column in latest.index else 0
                feature_row[column] = pd.to_numeric(feature_row[column], errors="coerce").fillna(0)
            predicted_cases = float(max(model.predict(feature_row[FEATURE_COLUMNS])[0], 0))
            interval_width = max(2.0, state_volatility, predicted_cases * 0.25) * np.sqrt(step)
            predicted_lower = max(predicted_cases - interval_width, 0)
            predicted_upper = predicted_cases + interval_width
            case_history.append(predicted_cases)
            death_history.append(death_history[-1] if death_history else 0)
            cfr_history.append(cfr_history[-1] if cfr_history else 0)
            forecasts.append(
                {
                    "state": state,
                    "forecast_week": step,
                    "year": int(iso.year),
                    "epi_week": int(iso.week),
                    "date": forecast_date.date().isoformat(),
                    "predicted_cases": round(predicted_cases, 2),
                    "predicted_lower": round(predicted_lower, 2),
                    "predicted_upper": round(predicted_upper, 2),
                    "risk_level": classify_prediction_risk(predicted_cases, history["suspected_cases"]),
                }
            )

    forecast = pd.DataFrame(forecasts)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        forecast.to_csv(output_path, index=False)
    return forecast


def train_model(
    dataset: pd.DataFrame,
    model_output_path: Path | None = None,
    tuning_iterations: int = 16,
    write_artifacts: bool = True,
) -> tuple[dict[str, object], np.ndarray]:
    metrics, search_results, best_model, best_model_name, validation = train_and_compare_models(
        dataset,
        tuning_iterations=tuning_iterations,
    )
    if model_output_path is not None:
        model_output_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(best_model, model_output_path)
    if write_artifacts:
        metrics_dir = OUTPUT_DIR / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        metrics.to_csv(metrics_dir / "model_comparison.csv", index=False)
        search_results.to_csv(metrics_dir / "hyperparameter_search_results.csv", index=False)
        validation.to_csv(metrics_dir / "validation_predictions.csv", index=False)
        validation.sort_values("absolute_error", ascending=False).head(25).to_csv(
            metrics_dir / "outlier_error_analysis.csv",
            index=False,
        )
        (metrics_dir / "best_model.json").write_text(
            json.dumps({"best_model": best_model_name}, indent=2),
            encoding="utf-8",
        )
    best_metrics = metrics[metrics["model"] == best_model_name].iloc[0].to_dict()
    return best_metrics, validation["predicted_cases"].to_numpy()


def main() -> None:
    dataset = build_dataset()
    metrics, _ = train_model(dataset, model_output_path=MODEL_DIR / "best_model.joblib")
    model = joblib.load(MODEL_DIR / "best_model.joblib")
    create_latest_forecast(dataset, model, output_path=OUTPUT_DIR / "forecasts" / "latest_forecast.csv")
    print("Training completed")
    print(metrics)


if __name__ == "__main__":
    main()
