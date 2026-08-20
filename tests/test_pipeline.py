import unittest
from pathlib import Path
import pandas as pd

from cholera_forecast.constants import CHOLERA_DATA_PATH
from cholera_forecast.data_pipeline import build_dataset, load_cholera_data
from cholera_forecast.features import build_features
from cholera_forecast.train_model import prepare_training_frame, time_based_split, train_model


class PipelineTests(unittest.TestCase):
    def test_load_cholera_data_reads_swappable_dataset(self):
        df = load_cholera_data(CHOLERA_DATA_PATH)
        self.assertIn("state", df.columns)
        self.assertIn("suspected_cases", df.columns)
        self.assertIn("deaths", df.columns)
        self.assertIn("cfr", df.columns)
        self.assertGreater(len(df), 0)

    def test_feature_engineering_creates_model_columns(self):
        raw = pd.DataFrame(
            {
                "state": ["Lagos"] * 10,
                "year": [2024] * 10,
                "epi_week": ["1-5", "6-9", "10", "11-14", "15-18", "19", "20-23", "24-27", "28", "29-32"],
                "suspected_cases": list(range(10, 20)),
                "deaths": [0, 1, 0, 0, 1, 0, 2, 0, 1, 0],
                "cfr": [0, 0.1, 0, 0, 0.0714, 0, 0.125, 0, 0.0556, 0],
                "rainfall_mm": [20] * 10,
                "temperature_c": [28] * 10,
                "humidity_pct": [70] * 10,
            }
        )
        df = build_features(raw)
        self.assertIn("suspected_cases", df.columns)
        self.assertIn("risk_level", df.columns)
        self.assertIn("epi_week_start", df.columns)
        self.assertIn("period_weeks", df.columns)
        self.assertIn("cfr", df.columns)
        self.assertIn("lag_8_cases", df.columns)
        self.assertIn("basic_water_pct", df.columns)
        self.assertIn("open_defecation_pct", df.columns)
        self.assertIn("rainfall_anomaly_mm", df.columns)
        self.assertIn("idp_population", df.columns)
        self.assertIn("health_facility_count", df.columns)

    def test_dataset_merges_wdi_wash_context(self):
        dataset = build_dataset()
        self.assertIn("basic_sanitation_pct", dataset.columns)
        self.assertIn("safely_managed_water_pct", dataset.columns)
        self.assertFalse(dataset["basic_sanitation_pct"].isna().all())
        self.assertIn("rolling_4_rainfall_mm", dataset.columns)
        self.assertIn("health_facility_count", dataset.columns)
        self.assertFalse(dataset["health_facility_count"].isna().all())

    def test_train_model_returns_metrics_and_predictions(self):
        dataset = build_dataset()
        features, target = prepare_training_frame(dataset)
        metrics, predictions = train_model(
            dataset,
            model_output_path=Path("models/test_best_model.joblib"),
            tuning_iterations=2,
            write_artifacts=False,
        )
        self.assertGreater(len(features), 0)
        self.assertGreater(len(target), 0)
        self.assertIn("mae", metrics)
        self.assertIn("rmse", metrics)
        self.assertIn("model", metrics)
        self.assertGreaterEqual(len(predictions), 1)

    def test_time_based_split_keeps_future_periods_out_of_training(self):
        dataset = build_dataset()
        train, test = time_based_split(dataset)
        train_periods = set(zip(train["year"], train["epi_week"]))
        test_periods = set(zip(test["year"], test["epi_week"]))
        last_train_period = tuple(train[["year", "epi_week"]].drop_duplicates().sort_values(["year", "epi_week"]).iloc[-1])
        first_test_period = tuple(test[["year", "epi_week"]].drop_duplicates().sort_values(["year", "epi_week"]).iloc[0])
        self.assertTrue(train_periods.isdisjoint(test_periods))
        self.assertLess(last_train_period, first_test_period)


if __name__ == "__main__":
    unittest.main()
