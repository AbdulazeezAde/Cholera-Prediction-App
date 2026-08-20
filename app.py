import streamlit as st
import pandas as pd
from pathlib import Path
import joblib
import plotly.express as px

from cholera_forecast.data_pipeline import build_dataset
from cholera_forecast.train_model import create_latest_forecast

st.set_page_config(page_title="Cholera Risk Dashboard", layout="wide")
st.title("Cholera Risk Forecast Dashboard")
st.caption(
    "Academic decision-support prototype based on data/raw/cholera_data.csv and generated modeling features."
)

@st.cache_data(show_spinner=False)
def load_data():
    return build_dataset()


@st.cache_resource(show_spinner=False)
def load_model():
    model_path = Path("models/best_model.joblib")
    return joblib.load(model_path) if model_path.exists() else None


dataset = load_data()
model = load_model()

states = sorted(dataset["state"].dropna().unique())
selected_state = st.sidebar.selectbox("State", states)
state_df = dataset[dataset["state"] == selected_state].sort_values(["year", "epi_week"])

st.subheader("Latest weekly risk overview")
latest = dataset.sort_values(["year", "epi_week"]).groupby("state").tail(1)

overview_cols = ["state", "year", "epi_week", "suspected_cases", "confirmed_cases", "deaths", "risk_level"]
st.dataframe(latest[overview_cols].reset_index(drop=True), use_container_width=True)

left, right = st.columns([2, 1])
with left:
    st.subheader(f"Historical suspected cases: {selected_state}")
    fig = px.line(
        state_df,
        x="date",
        y="suspected_cases",
        markers=True,
        labels={"date": "Week", "suspected_cases": "Suspected cases"},
    )
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Dataset status")
    st.metric("Rows", f"{len(dataset):,}")
    st.metric("States", dataset["state"].nunique())
    st.metric("Years", f"{int(dataset['year'].min())}-{int(dataset['year'].max())}")

st.subheader("Forecast view")
if model is None:
    st.info("Model artifact is not available yet. Run the training script first.")
else:
    forecast_path = Path("outputs/forecasts/latest_forecast.csv")
    if forecast_path.exists():
        forecast_df = pd.read_csv(forecast_path)
    else:
        forecast_df = create_latest_forecast(dataset, model)
    state_forecast = forecast_df[forecast_df["state"] == selected_state]
    st.dataframe(state_forecast, use_container_width=True)
    fig = px.bar(
        forecast_df[forecast_df["forecast_week"] == 1].sort_values("predicted_cases", ascending=False),
        x="state",
        y="predicted_cases",
        color="risk_level",
        labels={"predicted_cases": "Predicted cases", "state": "State"},
        title="One-week-ahead predicted cholera risk by state",
    )
    st.plotly_chart(fig, use_container_width=True)

metrics_path = Path("outputs/metrics/model_comparison.csv")
if metrics_path.exists():
    st.subheader("Model performance")
    st.dataframe(pd.read_csv(metrics_path), use_container_width=True)
