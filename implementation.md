# IMPLEMENTATION.md

# Development of a Predictive Model for Cholera Outbreaks

## 1. Purpose of this Implementation Plan

This document explains the best and most feasible way to implement the project titled **Development of a Predictive Model for Cholera Outbreaks**. It is written as a practical implementation guide for an undergraduate Software Engineering / Computer Science project. The plan is designed to be realistic, data-driven, and achievable with a normal laptop, Python, and freely available public datasets.

The current project document already proposes the use of **NCDC cholera data**, **environmental variables**, **machine learning**, **Prophet**, **XGBoost**, and a **React dashboard**. This implementation plan keeps that direction but makes the project more feasible by narrowing the scope to a clear and measurable system:

> **A weekly state-level cholera outbreak forecasting and risk dashboard for Nigeria using historical NCDC outbreak data, lagged case features, climate variables, and machine learning models.**

The system should support public health decision-making, but it should **not** be presented as a replacement for epidemiologists, clinicians, NCDC, WHO, or state health authorities. It is a decision-support prototype.

---

## 2. Recommended Final Scope

### 2.1 Best Feasible Version of the Project

The most feasible version is:

> Build a Python-based prediction system that uses historical cholera cases and environmental variables to forecast cholera case trends for Nigerian states on a weekly basis, then display the results on a React dashboard.

This means the system will:

1. Collect and clean historical cholera outbreak records.
2. Organize the data by **state**, **year**, and **epidemiological week**.
3. Add environmental and time-based features such as rainfall, temperature, humidity, month, week number, rainy season flag, and lagged case values.
4. Train and compare simple baseline models, Prophet, Random Forest, and XGBoost.
5. Select the best-performing model based on time-aware validation.
6. Forecast short-term cholera cases, preferably **1 to 4 weeks ahead**.
7. Convert predicted cases into interpretable risk levels such as **Low**, **Medium**, and **High**.
8. Display results in a simple dashboard for public health interpretation.

### 2.2 What the Project Should Not Try to Do

To keep the project feasible, avoid claiming that the system is a national real-time surveillance system. The data is not always real-time, and cholera reports may be weekly, delayed, incomplete, or published in PDF format. The system should also not claim to predict every outbreak perfectly, because outbreaks can be affected by sudden flooding, conflict, population displacement, water supply failures, and underreporting.

The system should not attempt to automatically make health decisions. Instead, it should provide forecasts and visual insights that can help planning.

---

## 3. Research-Based Project Direction

### 3.1 Why Cholera Prediction is Suitable for Machine Learning

Cholera is strongly linked with water, sanitation, hygiene, environmental exposure, and seasonal patterns. In many places, cases increase during rainy seasons, flooding, and periods when clean water access is poor. Because these factors change over time and space, historical data and environmental variables can help identify patterns useful for forecasting.

For this project, machine learning is suitable because cholera outbreaks are not always linear. A small rainfall increase may not always cause an outbreak, but heavy rainfall combined with poor sanitation, high population density, and past cases may increase risk. Algorithms like Random Forest and XGBoost are useful because they can model nonlinear relationships in structured tabular data.

### 3.2 Why a Weekly State-Level Model is Better Than a Daily Model

A daily model may sound better, but it is not very feasible because most public cholera data in Nigeria is published as situation reports or weekly summaries. Daily confirmed case data may be difficult to obtain consistently for all states. A weekly state-level model is more realistic because:

- NCDC situation reports are usually organized around epidemiological weeks.
- Weekly data reduces noise caused by reporting delays.
- Weekly forecasting is easier to validate.
- Climate variables can be aggregated into weekly averages or totals.
- It matches how many public health outbreak summaries are reported.

Therefore, the recommended time unit is:

> **One row = one Nigerian state in one epidemiological week.**

Example:

| state | year | epi_week | suspected_cases | confirmed_cases | deaths | rainfall_mm | temperature_c | humidity | lag_1_cases | risk_level |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Lagos | 2024 | 25 | 120 | 35 | 3 | 78.4 | 27.1 | 82.0 | 90 | High |

### 3.3 Recommended Prediction Target

The project document currently focuses on confirmed cholera cases, but confirmed cases may be sparse or inconsistent because laboratory confirmation can be limited. For feasibility, the best target should be chosen based on the available data:

**Option A: Regression target**

Predict the number of cases for a future week.

Recommended target column:

```text
suspected_cases or confirmed_cases
```

Use suspected cases if confirmed case data is missing for many weeks. Use confirmed cases only if it is consistently available.

**Option B: Classification target**

Predict whether a state-week is Low, Medium, or High risk.

Example rule:

```text
Low risk = 0 cases or very low case count
Medium risk = above normal baseline but below outbreak threshold
High risk = top 25% of case values or above defined outbreak threshold
```

**Best approach:** use regression as the main task, then derive risk level from predicted cases. This is more useful because public health officers can see both the expected number of cases and the risk category.

---

## 4. Data Sources

### 4.1 Primary Epidemiological Data

The main data source should be:

1. **Nigeria Centre for Disease Control and Prevention (NCDC) cholera situation reports**
   - Website: https://ncdc.gov.ng/diseases/sitreps/?cat=7&name=An+update+of+Cholera+outbreak+in+Nigeria
   - Use for weekly cholera outbreak reports.
   - Expected fields: state, suspected cases, confirmed cases, deaths, case fatality ratio, week, year.

2. **NCDC Weekly Epidemiological Reports**
   - Website: https://ncdc.gov.ng/reports/weekly
   - Use as supporting source where cholera-specific situation reports are incomplete.

### 4.2 Climate and Environmental Data

Use free public data sources:

1. **NASA POWER API**
   - Website: https://power.larc.nasa.gov/docs/services/api/
   - Use for rainfall, temperature, relative humidity, wind speed, and related climate variables.
   - Recommended parameters:
     - `T2M` = temperature at 2 meters
     - `RH2M` = relative humidity at 2 meters
     - `PRECTOTCORR` = precipitation/rainfall
     - `WS2M` = wind speed at 2 meters, optional

2. **World Bank WDI / WHO-UNICEF JMP WASH Indicators**
   - Website: https://data.worldbank.org/
   - Use for annual water and sanitation indicators, especially access to safely managed drinking water and sanitation.
   - These are usually national-level or sometimes urban/rural values, so they should be treated as supporting context, not the main predictive feature.

3. **WorldPop Population Data**
   - Website: https://www.worldpop.org/ and https://wopr.worldpop.org/
   - Use for population density or estimated population, if spatial aggregation is possible.
   - For a BSc project, a simpler alternative is to use manually prepared state population estimates.

4. **GADM Administrative Boundaries**
   - Website: https://gadm.org/
   - Use for Nigeria state boundaries and state centroids.
   - If geospatial processing is too much, manually create a CSV containing state names, latitude, and longitude.

### 4.3 Feasible Data Strategy

The most practical data strategy is:

1. Download NCDC cholera situation reports.
2. Extract state-level weekly tables from PDFs.
3. Manually validate the extracted tables because PDF extraction can produce errors.
4. Create a clean CSV file called `cholera_state_week.csv`.
5. Create another file called `state_coordinates.csv` with state names, latitudes, and longitudes.
6. Use NASA POWER API to fetch climate data for each state centroid.
7. Aggregate daily climate data into epidemiological week values.
8. Merge epidemiological and climate data by `state`, `year`, and `epi_week`.

---

## 5. Proposed Dataset Schema

### 5.1 Raw Cholera Data

Create:

```text
data/raw/ncdc_cholera_reports/
```

Store the downloaded PDF files here.

After extraction, create:

```text
data/interim/cholera_extracted_raw.csv
```

Suggested columns:

| Column | Description |
|---|---|
| report_year | Year of the report |
| epi_week | Epidemiological week |
| state | Nigerian state |
| suspected_cases | Reported suspected cholera cases |
| confirmed_cases | Laboratory-confirmed cases, if available |
| deaths | Reported deaths |
| cfr | Case fatality ratio, if available |
| source_file | PDF file name or source report |

### 5.2 Climate Data

Create:

```text
data/interim/climate_state_week.csv
```

Suggested columns:

| Column | Description |
|---|---|
| state | Nigerian state |
| year | Year |
| epi_week | Epidemiological week |
| rainfall_mm | Weekly total rainfall |
| temperature_c | Weekly average temperature |
| humidity_pct | Weekly average relative humidity |
| wind_speed | Optional weekly wind speed |

### 5.3 Final Modeling Dataset

Create:

```text
data/processed/modeling_dataset.csv
```

Suggested columns:

| Column | Description |
|---|---|
| state | Nigerian state |
| year | Year |
| epi_week | Epidemiological week |
| date | Start date of epidemiological week |
| suspected_cases | Target variable, if used |
| confirmed_cases | Alternative target variable |
| deaths | Reported deaths |
| rainfall_mm | Weekly rainfall |
| temperature_c | Weekly temperature |
| humidity_pct | Weekly humidity |
| month | Month number |
| quarter | Quarter |
| rainy_season | 1 if week falls in rainy season, else 0 |
| lag_1_cases | Previous week cases |
| lag_2_cases | Cases two weeks ago |
| lag_4_cases | Cases four weeks ago |
| rolling_4_cases | Four-week rolling average |
| rolling_8_cases | Eight-week rolling average |
| outbreak_risk | Derived risk level |

---

## 6. Model Design

### 6.1 Models to Compare

The project should not jump directly to XGBoost or Prophet. It should compare simple models first. This makes the research stronger and more credible.

Recommended models:

1. **Naive baseline**
   - Predict next week cases as the same as last week.
   - Very simple but important for comparison.

2. **Moving average baseline**
   - Predict next week cases using the average of the last 4 weeks.

3. **Prophet**
   - Good for time-series trend and seasonality.
   - Best used for national-level or state-specific time series.
   - May struggle with sudden spikes.

4. **Random Forest Regressor**
   - Good baseline machine learning model.
   - Handles nonlinear features.
   - Less sensitive to feature scaling.

5. **XGBoost Regressor**
   - Recommended main model.
   - Strong for structured tabular data.
   - Can use lagged cases, climate features, and temporal features.

6. **Hybrid Prophet-XGBoost model**
   - Optional but useful if time allows.
   - Prophet captures seasonality and trend.
   - XGBoost learns the residual error or improves predictions using additional features.

### 6.2 Recommended Main Model

The best feasible main model is:

> **XGBoost regression model using lagged cases, weekly climate variables, and time features.**

Why this is best:

- It works well with tabular data.
- It can model nonlinear relationships.
- It is easier to train than a deep learning model.
- It is feasible on a normal laptop.
- It can handle engineered features such as lag values and rolling averages.
- It can be explained using feature importance.

### 6.3 Prophet-XGBoost Hybrid Model

Use this only after the basic models are working.

There are two possible hybrid approaches:

#### Approach A: Residual Learning

1. Train Prophet on historical cases.
2. Get Prophet predictions.
3. Calculate residuals:

```text
residual = actual_cases - prophet_prediction
```

4. Train XGBoost to predict the residual using climate and lagged features.
5. Final prediction:

```text
final_prediction = prophet_prediction + xgboost_residual_prediction
```

#### Approach B: Feature Stacking

1. Train Prophet.
2. Use Prophet output columns such as `trend`, `yhat`, `weekly`, and `yearly` as features.
3. Add rainfall, temperature, lagged cases, and rolling averages.
4. Train XGBoost on the combined features.

For an undergraduate project, **Approach B** is easier to implement and explain.

---

## 7. Evaluation Strategy

### 7.1 Avoid Random Train-Test Split

Do not use ordinary random train-test split for time-series forecasting because it can leak future information into the training set. Instead, use time-based splitting.

Recommended split:

```text
Training data: earliest 80% of weeks
Validation/Test data: latest 20% of weeks
```

Better option:

```text
Walk-forward validation
```

This means training on older weeks and testing on later weeks repeatedly.

### 7.2 Regression Metrics

Use these if predicting case counts:

| Metric | Meaning |
|---|---|
| MAE | Average absolute prediction error |
| RMSE | Penalizes large errors more strongly |
| R² | Explains how much variation the model captures |
| MAPE / SMAPE | Percentage error, but be careful when actual cases are zero |

Recommended main metrics:

```text
MAE, RMSE, SMAPE, R²
```

### 7.3 Classification Metrics

Use these only if predicting outbreak risk category:

| Metric | Meaning |
|---|---|
| Accuracy | Overall correct classifications |
| Precision | How many predicted outbreaks were truly outbreaks |
| Recall | How many actual outbreaks were detected |
| F1-score | Balance between precision and recall |
| ROC-AUC | Useful for binary outbreak/non-outbreak classification |

For public health, **recall is very important** because missing a true outbreak is more dangerous than raising a false alarm. However, false alarms should still be controlled.

### 7.4 Important Correction for the Existing Project Document

The current document mixes regression metrics like MAE and RMSE with classification metrics like accuracy, precision, and recall. This is not wrong if both tasks are implemented, but the report must clearly separate them:

- If predicting **case count**, use regression metrics.
- If predicting **outbreak risk**, use classification metrics.

Do not report statistical values such as p-values, confidence intervals, or model performance numbers unless they are actually computed from the dataset.

---

## 8. Dashboard Design

### 8.1 Recommended Dashboard Pages

Use Streamlit because it is simple, Python-based, and suitable for undergraduate prototypes.

Recommended pages:

1. **Home / Project Overview**
   - Explain the project aim.
   - Explain that the system is decision-support, not a replacement for health experts.

2. **Data Overview**
   - Show dataset size.
   - Show states covered.
   - Show years covered.
   - Show missing values summary.

3. **Historical Trend Analysis**
   - Line chart of cholera cases over time.
   - Filter by state.
   - Show rainy season periods.

4. **Model Performance**
   - Compare MAE, RMSE, SMAPE, and R² across models.
   - Show actual vs predicted chart.

5. **Forecast Dashboard**
   - Show next 1-4 week predictions.
   - Show risk category.
   - Filter by state.

6. **Risk Map**
   - Optional.
   - Display state-level risk on a Nigeria map.
   - If mapping is difficult, use a bar chart ranking states by predicted risk.

### 8.2 Minimum Dashboard Features

The dashboard should include:

- State filter
- Date/week filter
- Actual vs predicted chart
- Forecast table
- Risk level indicator
- Model metrics table
- Feature importance chart for XGBoost

---

## 9. Proposed System Architecture

```text
                  +-------------------------+
                  | NCDC Cholera Reports    |
                  | PDF / CSV / Web Tables  |
                  +-----------+-------------+
                              |
                              v
                  +-------------------------+
                  | Data Extraction         |
                  | pdfplumber / manual CSV |
                  +-----------+-------------+
                              |
                              v
+------------------+   +-------------------------+   +-------------------+
| NASA POWER API   |-->| Data Cleaning & Merge   |<--| State Coordinates |
| Climate Data     |   | state + year + week     |   | lat/lon CSV       |
+------------------+   +-----------+-------------+   +-------------------+
                                  |
                                  v
                      +-------------------------+
                      | Feature Engineering     |
                      | lags, rolling averages, |
                      | rainy season, climate   |
                      +-----------+-------------+
                                  |
                                  v
                      +-------------------------+
                      | Model Training          |
                      | Baseline, Prophet, RF,  |
                      | XGBoost, Hybrid optional|
                      +-----------+-------------+
                                  |
                                  v
                      +-------------------------+
                      | Evaluation              |
                      | MAE, RMSE, SMAPE, R²    |
                      +-----------+-------------+
                                  |
                                  v
                      +-------------------------+
                      | Streamlit Dashboard     |
                      | Trends, forecast, risk  |
                      +-------------------------+
```

---

## 10. Recommended Folder Structure

```text
cholera-prediction-project/
│
├── data/
│   ├── raw/
│   │   ├── ncdc_cholera_reports/
│   │   └── state_coordinates.csv
│   ├── interim/
│   │   ├── cholera_extracted_raw.csv
│   │   └── climate_state_week.csv
│   └── processed/
│       └── modeling_dataset.csv
│
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_climate_data_collection.ipynb
│   ├── 03_feature_engineering.ipynb
│   ├── 04_model_training.ipynb
│   └── 05_model_evaluation.ipynb
│
├── src/
│   ├── data_extraction.py
│   ├── climate_api.py
│   ├── preprocessing.py
│   ├── features.py
│   ├── train_models.py
│   ├── evaluate.py
│   └── utils.py
│
├── models/
│   ├── xgboost_model.pkl
│   ├── random_forest_model.pkl
│   └── prophet_model.pkl
│
├── dashboard/
│   ├── app.py
│   └── pages/
│       ├── 1_Data_Overview.py
│       ├── 2_Historical_Trends.py
│       ├── 3_Model_Performance.py
│       └── 4_Forecast.py
│
├── outputs/
│   ├── figures/
│   ├── metrics/
│   └── forecasts/
│
├── requirements.txt
├── README.md
└── implementation.md
```

---

## 11. Environment Setup

### 11.1 Python Version

Use Python 3.10 or 3.11.

### 11.2 requirements.txt

```text
pandas
numpy
scikit-learn
xgboost
prophet
matplotlib
plotly
requests
pdfplumber
openpyxl
joblib
python-dateutil
```

Optional geospatial libraries:

```text
geopandas
shapely
folium
streamlit-folium
```

For feasibility, avoid geospatial libraries at the beginning. Add them only after the basic dashboard works.

### 11.3 Installation

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

---

## 12. Step-by-Step Implementation Plan

## Phase 1: Data Collection

### Step 1: Download NCDC Cholera Reports

Download available cholera situation reports from the NCDC cholera situation report page. Store all PDFs in:

```text
data/raw/ncdc_cholera_reports/
```

### Step 2: Extract Tables from PDFs

Start with `pdfplumber`. If the PDF tables are difficult to extract, use manual cleaning in Excel after extraction.

Example extraction code:

```python
import pdfplumber
import pandas as pd
from pathlib import Path

pdf_dir = Path("data/raw/ncdc_cholera_reports")
rows = []

for pdf_path in pdf_dir.glob("*.pdf"):
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            for table in tables:
                if table:
                    df = pd.DataFrame(table)
                    df["source_file"] = pdf_path.name
                    df["page"] = page_num
                    rows.append(df)

raw_tables = pd.concat(rows, ignore_index=True)
raw_tables.to_csv("data/interim/cholera_extracted_raw.csv", index=False)
```

After extraction, manually inspect the file and convert it into a clean format.

### Step 3: Prepare State Coordinates

Create:

```text
data/raw/state_coordinates.csv
```

Example columns:

```text
state,latitude,longitude,zone
Lagos,6.5244,3.3792,South West
Kano,12.0022,8.5920,North West
FCT,9.0765,7.3986,North Central
```

This avoids early geospatial complexity.

---

## Phase 2: Climate Data Collection

### Step 4: Fetch NASA POWER Data

Use state coordinates to fetch daily climate data, then aggregate into epidemiological weeks.

Example API approach:

```python
import requests
import pandas as pd

NASA_PARAMS = "T2M,RH2M,PRECTOTCORR"

def fetch_nasa_power(lat, lon, start_date, end_date):
    url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "parameters": NASA_PARAMS,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_date,
        "end": end_date,
        "format": "JSON"
    }
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    data = response.json()["properties"]["parameter"]
    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.reset_index().rename(columns={"index": "date"})
    return df
```

### Step 5: Convert Daily Climate Data to Weekly Data

```python
def add_epi_week(df):
    iso = df["date"].dt.isocalendar()
    df["year"] = iso.year.astype(int)
    df["epi_week"] = iso.week.astype(int)
    return df

weekly_climate = (
    climate_df
    .pipe(add_epi_week)
    .groupby(["state", "year", "epi_week"], as_index=False)
    .agg({
        "PRECTOTCORR": "sum",
        "T2M": "mean",
        "RH2M": "mean"
    })
    .rename(columns={
        "PRECTOTCORR": "rainfall_mm",
        "T2M": "temperature_c",
        "RH2M": "humidity_pct"
    })
)
```

---

## Phase 3: Data Cleaning and Feature Engineering

### Step 6: Merge Cholera and Climate Data

```python
cholera = pd.read_csv("data/interim/cholera_clean.csv")
climate = pd.read_csv("data/interim/climate_state_week.csv")

model_df = cholera.merge(
    climate,
    on=["state", "year", "epi_week"],
    how="left"
)

model_df.to_csv("data/processed/modeling_dataset_base.csv", index=False)
```

### Step 7: Handle Missing Values

Recommended strategy:

- For case counts: fill missing with 0 only if it means no reported cases. If unknown, keep as missing and investigate.
- For climate values: interpolate or fill using state-level weekly averages.
- For static state variables: fill using available state value.

Example:

```python
for col in ["rainfall_mm", "temperature_c", "humidity_pct"]:
    model_df[col] = model_df.groupby("state")[col].transform(lambda s: s.interpolate().ffill().bfill())
```

### Step 8: Create Time and Lag Features

```python
model_df = model_df.sort_values(["state", "year", "epi_week"])

model_df["date"] = pd.to_datetime(model_df["date"])
model_df["month"] = model_df["date"].dt.month
model_df["quarter"] = model_df["date"].dt.quarter
model_df["rainy_season"] = model_df["month"].isin([4, 5, 6, 7, 8, 9, 10]).astype(int)

TARGET = "suspected_cases"

for lag in [1, 2, 4, 8]:
    model_df[f"lag_{lag}_cases"] = model_df.groupby("state")[TARGET].shift(lag)

model_df["rolling_4_cases"] = (
    model_df.groupby("state")[TARGET]
    .shift(1)
    .rolling(window=4, min_periods=1)
    .mean()
    .reset_index(level=0, drop=True)
)

model_df["rolling_8_cases"] = (
    model_df.groupby("state")[TARGET]
    .shift(1)
    .rolling(window=8, min_periods=1)
    .mean()
    .reset_index(level=0, drop=True)
)

model_df = model_df.dropna(subset=["lag_1_cases", "lag_2_cases", "lag_4_cases"])
```

Important: always shift lag and rolling features so the model does not see the current target value while predicting.

---

## Phase 4: Modeling

### Step 9: Baseline Model

```python
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import numpy as np

actual = test_df[TARGET]
pred_naive = test_df["lag_1_cases"]

mae = mean_absolute_error(actual, pred_naive)
rmse = np.sqrt(mean_squared_error(actual, pred_naive))
r2 = r2_score(actual, pred_naive)

print(mae, rmse, r2)
```

### Step 10: XGBoost Model

```python
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import numpy as np
import joblib

features = [
    "epi_week", "month", "quarter", "rainy_season",
    "rainfall_mm", "temperature_c", "humidity_pct",
    "lag_1_cases", "lag_2_cases", "lag_4_cases", "lag_8_cases",
    "rolling_4_cases", "rolling_8_cases"
]

X_train = train_df[features]
y_train = train_df[TARGET]
X_test = test_df[features]
y_test = test_df[TARGET]

model = XGBRegressor(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=4,
    subsample=0.8,
    colsample_bytree=0.8,
    objective="reg:squarederror",
    random_state=42
)

model.fit(X_train, y_train)
preds = model.predict(X_test)
preds = np.maximum(preds, 0)  # case predictions cannot be negative

metrics = {
    "MAE": mean_absolute_error(y_test, preds),
    "RMSE": np.sqrt(mean_squared_error(y_test, preds)),
    "R2": r2_score(y_test, preds)
}

print(metrics)
joblib.dump(model, "models/xgboost_model.pkl")
```

### Step 11: Prophet Model

Prophet requires columns named:

```text
ds = date
y = target cases
```

Example for one state:

```python
from prophet import Prophet

state_df = model_df[model_df["state"] == "Lagos"][["date", TARGET, "rainfall_mm", "temperature_c"]]
state_df = state_df.rename(columns={"date": "ds", TARGET: "y"})

m = Prophet(yearly_seasonality=True, weekly_seasonality=False)
m.add_regressor("rainfall_mm")
m.add_regressor("temperature_c")
m.fit(state_df)

future = m.make_future_dataframe(periods=4, freq="W")

# For future regressors, use recent averages as a simple baseline.
future["rainfall_mm"] = state_df["rainfall_mm"].rolling(4).mean().iloc[-1]
future["temperature_c"] = state_df["temperature_c"].rolling(4).mean().iloc[-1]

forecast = m.predict(future)
```

Because Prophet with regressors needs future values of those regressors, avoid overclaiming if future rainfall is not available. For the undergraduate prototype, using recent averages is acceptable, but state it clearly as a limitation.

### Step 12: Hybrid Model

Only implement this after the XGBoost model works.

Simple stacking approach:

1. Fit Prophet per state or nationally.
2. Add Prophet predictions to the dataset as a new feature.
3. Train XGBoost using Prophet prediction plus climate and lag features.

```python
features = [
    "prophet_yhat",
    "epi_week", "month", "rainy_season",
    "rainfall_mm", "temperature_c", "humidity_pct",
    "lag_1_cases", "lag_2_cases", "lag_4_cases",
    "rolling_4_cases"
]
```

---

## Phase 5: Forecasting Future Weeks

### Step 13: Create Forecast Input

To forecast the next 4 weeks:

1. Take the latest state-week row.
2. Generate future week numbers.
3. Use available climate forecast if available; otherwise use recent climate averages.
4. Update lag features using the latest actual and predicted values.
5. Predict one week at a time.

This is called recursive forecasting.

Example logic:

```text
Week +1 prediction uses latest actual lag values.
Week +2 prediction uses Week +1 predicted value as lag_1.
Week +3 prediction uses Week +2 predicted value as lag_1.
Week +4 prediction uses Week +3 predicted value as lag_1.
```

### Step 14: Convert Prediction to Risk Level

Example simple rule:

```python
def classify_risk(predicted_cases):
    if predicted_cases < 5:
        return "Low"
    elif predicted_cases < 25:
        return "Medium"
    else:
        return "High"
```

Better rule:

Use quantiles from the historical data:

```python
q50 = model_df[TARGET].quantile(0.50)
q75 = model_df[TARGET].quantile(0.75)

risk = "Low" if pred < q50 else "Medium" if pred < q75 else "High"
```

This makes the threshold more data-driven.

---

## Phase 6: React Dashboard

### Step 15: Basic App

Create:

```text
dashboard/app.py
```

Example:

```python
import streamlit as st
import pandas as pd
import joblib
import plotly.express as px

st.set_page_config(page_title="Cholera Outbreak Prediction", layout="wide")

st.title("Cholera Outbreak Prediction Dashboard")
st.write("This dashboard provides decision-support forecasts for cholera outbreak trends in Nigeria.")

DATA_PATH = "data/processed/modeling_dataset.csv"
MODEL_PATH = "models/xgboost_model.pkl"

df = pd.read_csv(DATA_PATH)
model = joblib.load(MODEL_PATH)

states = sorted(df["state"].dropna().unique())
selected_state = st.sidebar.selectbox("Select State", states)

state_df = df[df["state"] == selected_state].copy()

fig = px.line(
    state_df,
    x="date",
    y="suspected_cases",
    title=f"Historical Cholera Cases in {selected_state}"
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Dataset Preview")
st.dataframe(state_df.tail(20))
```

### Step 16: Model Performance Page

Show metrics in a table:

```python
metrics_df = pd.read_csv("outputs/metrics/model_comparison.csv")
st.dataframe(metrics_df)
```

### Step 17: Forecast Page

Show forecast table:

```python
forecast_df = pd.read_csv("outputs/forecasts/latest_forecast.csv")
st.dataframe(forecast_df)

fig = px.bar(
    forecast_df,
    x="state",
    y="predicted_cases",
    color="risk_level",
    title="Predicted Cholera Risk by State"
)
st.plotly_chart(fig, use_container_width=True)
```

---

## 13. Suggested Project Timeline

A feasible 6-week timeline:

| Week | Main Task | Output |
|---|---|---|
| Week 1 | Collect NCDC reports and prepare raw data | Raw PDFs and extracted CSV |
| Week 2 | Clean cholera data and collect NASA climate data | Clean merged dataset |
| Week 3 | Feature engineering and exploratory analysis | EDA charts and modeling dataset |
| Week 4 | Train baseline, Prophet, Random Forest, and XGBoost | Model metrics and saved models |
| Week 5 | Build React dashboard | Working dashboard prototype |
| Week 6 | Testing, documentation, screenshots, chapter 4/5 updates | Final project artefact and report evidence |

---

## 14. Feasibility Assessment

### 14.1 Why This Project is Feasible

The project is feasible because:

- It uses free public data sources.
- It uses Python libraries that are common in machine learning projects.
- The dataset size is manageable on a normal laptop.
- React allows fast dashboard development without advanced frontend coding.
- The prediction task can be scoped to weekly forecasts rather than unrealistic real-time alerts.
- XGBoost and Random Forest are suitable for structured data and do not require GPU resources.

### 14.2 Main Risks and Solutions

| Risk | Impact | Solution |
|---|---|---|
| NCDC PDFs are hard to extract | Data cleaning takes longer | Use pdfplumber first, then manually validate CSV |
| Confirmed cases are missing | Weak target variable | Use suspected cases as primary target and confirmed cases as secondary |
| Future rainfall is unknown | Forecast uncertainty | Use recent averages and clearly state limitation |
| Some states have few records | Poor state-level prediction | Train one national model with state encoded as a feature |
| Model overfits outbreak spikes | Poor generalization | Use time-based validation and regularization |
| Dashboard map is difficult | Delay | Use bar charts first, add map only if time allows |

### 14.3 Minimum Viable Product

The minimum viable project should include:

1. Clean state-week cholera dataset.
2. Merged climate dataset.
3. EDA charts.
4. Baseline model.
5. XGBoost model.
6. Evaluation table.
7. React dashboard with trends and forecast.
8. Clear limitations.

### 14.4 Optional Enhancements

Add these only after the MVP works:

- Prophet-XGBoost hybrid model.
- Nigeria map visualization.
- Feature importance explanation.
- Downloadable forecast CSV.
- Automated PDF scraper.
- Walk-forward validation.

---

## 15. Report Writing Guidance

### 15.1 Chapter Four Should Contain

1. Introduction to implementation.
2. Dataset description.
3. Data preprocessing results.
4. Exploratory analysis.
5. Model training process.
6. Model evaluation table.
7. Actual vs predicted charts.
8. Dashboard screenshots.
9. Discussion of results.
10. Limitations.

### 15.2 Avoid Unsupported Claims

Do not include numbers like:

```text
MAE = 20.11
RMSE = 26.89
p-value = 0.028
correlation = 0.89
```

unless those values are actually generated from the final code and dataset.

### 15.3 Better Result Statement Example

Instead of saying:

> The hybrid model significantly outperformed all models.

Say:

> Based on the validation results, the XGBoost model produced the lowest MAE and RMSE among the tested models. This suggests that lagged cases and environmental variables improved short-term cholera case prediction compared with the baseline model.

This is safer and more academically honest.

---

## 16. Ethical and Practical Considerations

This project uses public and aggregated disease surveillance data. It should not use personal patient records, names, addresses, phone numbers, or identifiable health details.

The dashboard should include a disclaimer:

> This dashboard is an academic prototype for decision-support. It should not be used as the sole basis for public health action. Final decisions should be made by qualified public health professionals using verified surveillance data.

---

## 17. Final Recommended Implementation Route

The best practical route is:

1. Start with a clean weekly state-level dataset.
2. Use suspected cases as the target if confirmed cases are incomplete.
3. Add climate variables from NASA POWER.
4. Engineer lag and rolling features.
5. Train baseline, Random Forest, XGBoost, and Prophet.
6. Use time-based validation.
7. Select XGBoost as the main model if it performs best.
8. Build a React dashboard.
9. Present forecasts as decision-support, not absolute truth.
10. Clearly discuss limitations caused by missing data, reporting delays, and uncertain future climate conditions.

---

## 18. References and Useful Sources

1. Nigeria Centre for Disease Control and Prevention. Cholera Situation Reports. https://ncdc.gov.ng/diseases/sitreps/?cat=7&name=An+update+of+Cholera+outbreak+in+Nigeria
2. Nigeria Centre for Disease Control and Prevention. Weekly Epidemiological Reports. https://ncdc.gov.ng/reports/weekly
3. World Health Organization. Cholera Fact Sheet. https://www.who.int/news-room/fact-sheets/detail/cholera
4. NASA POWER Data Services API. https://power.larc.nasa.gov/docs/services/api/
5. WorldPop Open Population Repository. https://wopr.worldpop.org/
6. World Bank Open Data. Nigeria WASH indicators. https://data.worldbank.org/
7. GADM Administrative Boundaries. https://gadm.org/
8. Prophet Documentation. https://facebook.github.io/prophet/docs/diagnostics.html
9. Scikit-learn TimeSeriesSplit Documentation. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
10. XGBoost Python API Documentation. https://xgboost.readthedocs.io/en/latest/python/python_api.html
11. Streamlit Documentation. https://docs.streamlit.io/

---

## 19. Final Note

The project is achievable if the scope remains focused. The strongest version is not the one with the most complex model, but the one with clean data, honest evaluation, good visual explanation, and clear limitations. A well-implemented XGBoost forecasting model with a simple React dashboard is more feasible and defensible than an overcomplicated deep learning or real-time system with weak data.

