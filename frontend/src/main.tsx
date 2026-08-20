import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, AlertTriangle, BarChart3, RefreshCw } from "lucide-react";
import { GeoJSON, MapContainer, Marker } from "react-leaflet";
import { divIcon } from "leaflet";
import type { Layer, LatLngExpression } from "leaflet";
import type { FeatureCollection } from "geojson";
import "leaflet/dist/leaflet.css";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

type RiskLevel = "Low" | "Medium" | "High";

type Summary = {
  rows: number;
  states: number;
  years: [number, number];
  total_cases: number;
  total_deaths: number;
  cfr: number;
  latest: HistoryRow[];
};

type HistoryRow = {
  state: string;
  year: number;
  epi_week: number;
  epi_week_label?: string;
  date: string;
  suspected_cases: number;
  deaths?: number;
  cfr?: number;
  risk_level: RiskLevel;
  rainfall_mm?: number;
  temperature_c?: number;
  humidity_pct?: number;
};

type ForecastRow = {
  state: string;
  forecast_week: number;
  year: number;
  epi_week: number;
  date: string;
  predicted_cases: number;
  predicted_lower?: number;
  predicted_upper?: number;
  risk_level: RiskLevel;
};

const riskColors: Record<RiskLevel, string> = {
  Low: "#2f9e44",
  Medium: "#f08c00",
  High: "#d00000",
};

function normalizeStateName(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/^nassarawa$/, "nasarawa")
    .replace(/^federal capital territory$/, "fct");
}

function featureStateName(props: Record<string, unknown>): string {
  return String(
    props.state ||
      props.NAME_1 ||
      props.name_1 ||
      props.name ||
      props.State ||
      props.admin1Name ||
      ""
  );
}

function featureStateAbbreviation(props: Record<string, unknown>, stateName: string): string {
  const hasc = String(props.hasc_1 || props.HASC_1 || "");
  const code = hasc.includes(".") ? hasc.split(".").pop() : "";
  if (code) {
    return code.toUpperCase();
  }
  if (normalizeStateName(stateName) === "fct") {
    return "FCT";
  }
  return stateName
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
}

function polygonRingArea(ring: number[][]): number {
  let area = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [x1, y1] = ring[index];
    const [x2, y2] = ring[index + 1];
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area / 2);
}

function polygonRingCentroid(ring: number[][]): LatLngExpression | null {
  let areaFactor = 0;
  let centroidX = 0;
  let centroidY = 0;
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [x1, y1] = ring[index];
    const [x2, y2] = ring[index + 1];
    const cross = x1 * y2 - x2 * y1;
    areaFactor += cross;
    centroidX += (x1 + x2) * cross;
    centroidY += (y1 + y2) * cross;
  }

  if (Math.abs(areaFactor) < 0.000001) {
    const validPoints = ring.filter(([longitude, latitude]) => Number.isFinite(longitude) && Number.isFinite(latitude));
    if (!validPoints.length) {
      return null;
    }
    const longitude = validPoints.reduce((total, point) => total + point[0], 0) / validPoints.length;
    const latitude = validPoints.reduce((total, point) => total + point[1], 0) / validPoints.length;
    return [latitude, longitude];
  }

  const longitude = centroidX / (3 * areaFactor);
  const latitude = centroidY / (3 * areaFactor);
  return [latitude, longitude];
}

function featureLabelPosition(feature: any): LatLngExpression | null {
  const geometry = feature?.geometry;
  if (!geometry) {
    return null;
  }

  const rings =
    geometry.type === "Polygon"
      ? geometry.coordinates.map((polygon: number[][]) => polygon)
      : geometry.type === "MultiPolygon"
        ? geometry.coordinates.map((polygon: number[][][]) => polygon[0])
        : [];

  const largestRing = rings
    .filter((ring: number[][]) => Array.isArray(ring) && ring.length > 2)
    .sort((a: number[][], b: number[][]) => polygonRingArea(b) - polygonRingArea(a))[0];

  return largestRing ? polygonRingCentroid(largestRing) : null;
}

function stateLabelIcon(abbreviation: string, stateName: string) {
  return divIcon({
    className: "state-label-icon",
    html: `<span class="state-label-abbr">${abbreviation}</span><span class="state-label-name">${stateName}</span>`,
    iconSize: [42, 22],
    iconAnchor: [21, 11],
  });
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function MetricCard({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <div className="metric-card">
      <div className="metric-icon">{icon}</div>
      <div>
        <div className="metric-label">{label}</div>
        <div className="metric-value">{value}</div>
      </div>
    </div>
  );
}

function formatPercent(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(2)}%`;
}

function movingAverage(values: number[], windowSize = 3): number[] {
  return values.map((_, index) => {
    const window = values.slice(Math.max(0, index - windowSize + 1), index + 1);
    return window.reduce((sum, value) => sum + value, 0) / window.length;
  });
}

function scaledPoint(
  index: number,
  value: number,
  count: number,
  maxValue: number,
  width: number,
  height: number,
  padding: { top: number; right: number; bottom: number; left: number }
): [number, number] {
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const x = padding.left + (count <= 1 ? 0 : (index / (count - 1)) * plotWidth);
  const y = padding.top + plotHeight - (value / maxValue) * plotHeight;
  return [x, y];
}

function pathFromPoints(points: [number, number][]): string {
  return points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
}

function ChartLegend({ items }: { items: { label: string; color: string; dashed?: boolean; band?: boolean }[] }) {
  return (
    <div className="chart-legend">
      {items.map((item) => (
        <span key={item.label}>
          <i
            className={item.band ? "legend-band" : item.dashed ? "legend-line dashed" : "legend-line"}
            style={{ background: item.band ? item.color : undefined, borderColor: item.band ? undefined : item.color }}
          />
          {item.label}
        </span>
      ))}
    </div>
  );
}

function CaseTrendChart({ rows }: { rows: HistoryRow[] }) {
  const chartRows = rows.slice(-18);
  const values = chartRows.map((row) => Number(row.suspected_cases ?? 0));
  const averages = movingAverage(values, 3);
  const width = 620;
  const height = 240;
  const padding = { top: 18, right: 18, bottom: 34, left: 42 };
  const maxValue = Math.max(...values, ...averages, 1) * 1.12;
  const casePoints = values.map((value, index) => scaledPoint(index, value, values.length, maxValue, width, height, padding));
  const averagePoints = averages.map((value, index) => scaledPoint(index, value, averages.length, maxValue, width, height, padding));
  const yTicks = [0, 0.5, 1].map((ratio) => Math.round(maxValue * ratio));

  if (!chartRows.length) {
    return <div className="empty-chart">No case history for selected state.</div>;
  }

  return (
    <div className="chart-shell">
      <ChartLegend
        items={[
          { label: "Cases", color: "#087f5b" },
          { label: "3-period average", color: "#d00000", dashed: true },
        ]}
      />
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Historical cholera case trend">
        {yTicks.map((tick) => {
          const [, y] = scaledPoint(0, tick, values.length, maxValue, width, height, padding);
          return (
            <g key={tick}>
              <line className="chart-grid-line" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text className="axis-label" x={padding.left - 10} y={y + 4} textAnchor="end">{tick}</text>
            </g>
          );
        })}
        <path className="trend-line average-line" d={pathFromPoints(averagePoints)} />
        <path className="trend-line case-line" d={pathFromPoints(casePoints)} />
        {casePoints.map(([x, y], index) => (
          <circle key={`${chartRows[index].year}-${chartRows[index].epi_week}-${index}`} className="case-dot" cx={x} cy={y} r="3.2">
            <title>{`${chartRows[index].year} week ${chartRows[index].epi_week_label ?? chartRows[index].epi_week}: ${values[index]} cases`}</title>
          </circle>
        ))}
        <text className="axis-label" x={padding.left} y={height - 8}>{chartRows[0].year} wk {chartRows[0].epi_week_label ?? chartRows[0].epi_week}</text>
        <text className="axis-label" x={width - padding.right} y={height - 8} textAnchor="end">
          {chartRows[chartRows.length - 1].year} wk {chartRows[chartRows.length - 1].epi_week_label ?? chartRows[chartRows.length - 1].epi_week}
        </text>
      </svg>
    </div>
  );
}

function ForecastIntervalChart({ historyRows, forecastRows }: { historyRows: HistoryRow[]; forecastRows: ForecastRow[] }) {
  const observed = historyRows.slice(-10).map((row) => ({
    label: `${row.year} wk ${row.epi_week_label ?? row.epi_week}`,
    value: Number(row.suspected_cases ?? 0),
  }));
  const forecasts = forecastRows.map((row) => ({
    label: `${row.year} wk ${row.epi_week}`,
    value: Number(row.predicted_cases ?? 0),
    lower: Number(row.predicted_lower ?? Math.max(row.predicted_cases * 0.75, 0)),
    upper: Number(row.predicted_upper ?? row.predicted_cases * 1.25),
  }));
  const width = 620;
  const height = 240;
  const padding = { top: 18, right: 18, bottom: 34, left: 42 };
  const totalCount = observed.length + forecasts.length;
  const maxValue = Math.max(...observed.map((row) => row.value), ...forecasts.map((row) => row.upper), 1) * 1.12;
  const observedPoints = observed.map((row, index) => scaledPoint(index, row.value, totalCount, maxValue, width, height, padding));
  const forecastOffset = Math.max(observed.length - 1, 0);
  const forecastLineRows = observed.length ? [{ ...observed[observed.length - 1], lower: observed[observed.length - 1].value, upper: observed[observed.length - 1].value }, ...forecasts] : forecasts;
  const forecastPoints = forecastLineRows.map((row, index) =>
    scaledPoint(forecastOffset + index, row.value, totalCount, maxValue, width, height, padding)
  );
  const upperPoints = forecastLineRows.map((row, index) =>
    scaledPoint(forecastOffset + index, row.upper, totalCount, maxValue, width, height, padding)
  );
  const lowerPoints = forecastLineRows
    .map((row, index) => scaledPoint(forecastOffset + index, row.lower, totalCount, maxValue, width, height, padding))
    .reverse();
  const bandPath = `${pathFromPoints(upperPoints)} ${lowerPoints.map(([x, y]) => `L ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ")} Z`;
  const yTicks = [0, 0.5, 1].map((ratio) => Math.round(maxValue * ratio));

  if (!observed.length && !forecasts.length) {
    return <div className="empty-chart">No forecast rows for selected state.</div>;
  }

  return (
    <div className="chart-shell">
      <ChartLegend
        items={[
          { label: "Observed", color: "#064e3b" },
          { label: "Forecast median", color: "#087f5b", dashed: true },
          { label: "Uncertainty range", color: "rgba(8, 127, 91, 0.16)", band: true },
        ]}
      />
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Cholera case forecast with uncertainty interval">
        {yTicks.map((tick) => {
          const [, y] = scaledPoint(0, tick, totalCount, maxValue, width, height, padding);
          return (
            <g key={tick}>
              <line className="chart-grid-line" x1={padding.left} x2={width - padding.right} y1={y} y2={y} />
              <text className="axis-label" x={padding.left - 10} y={y + 4} textAnchor="end">{tick}</text>
            </g>
          );
        })}
        {forecasts.length > 0 && <path className="forecast-band" d={bandPath} />}
        {observedPoints.length > 0 && <path className="trend-line observed-line" d={pathFromPoints(observedPoints)} />}
        {forecastPoints.length > 0 && <path className="trend-line forecast-line" d={pathFromPoints(forecastPoints)} />}
        {forecastPoints.slice(observed.length ? 1 : 0).map(([x, y], index) => (
          <circle key={`${forecasts[index]?.forecast_week}-${index}`} className="forecast-dot" cx={x} cy={y} r="3.2">
            <title>{`${forecasts[index]?.label}: ${forecasts[index]?.value.toFixed(1)} predicted cases`}</title>
          </circle>
        ))}
        {(observed[0] || forecasts[0]) && (
          <text className="axis-label" x={padding.left} y={height - 8}>{observed[0]?.label ?? forecasts[0]?.label}</text>
        )}
        {(forecasts[forecasts.length - 1] || observed[observed.length - 1]) && (
          <text className="axis-label" x={width - padding.right} y={height - 8} textAnchor="end">
            {forecasts[forecasts.length - 1]?.label ?? observed[observed.length - 1]?.label}
          </text>
        )}
      </svg>
    </div>
  );
}

function RiskMap({
  geojson,
  forecast,
  actualRows,
  selectedState,
  onSelectState,
}: {
  geojson: FeatureCollection | null;
  forecast: ForecastRow[];
  actualRows: HistoryRow[];
  selectedState: string;
  onSelectState: (state: string) => void;
}) {
  const forecastByState = useMemo(() => {
    const rows = forecast.filter((row) => row.forecast_week === 1);
    return new Map(rows.map((row) => [normalizeStateName(row.state), row]));
  }, [forecast]);
  const actualByState = useMemo(() => {
    return new Map(actualRows.map((row) => [normalizeStateName(row.state), row]));
  }, [actualRows]);
  const useActualRows = actualRows.length > 0;
  const actualRowsKey = actualRows.map((row) => `${row.state}:${row.year}:${row.epi_week_label ?? row.epi_week}`).join("|");
  const stateLabels = useMemo(() => {
    if (!geojson) {
      return [];
    }
    return geojson.features
      .map((feature, index) => {
        const props = feature.properties ?? {};
        const stateName = featureStateName(props);
        const position = featureLabelPosition(feature);
        if (!stateName || !position) {
          return null;
        }
        return {
          key: `${stateName}-${index}`,
          stateName,
          abbreviation: featureStateAbbreviation(props, stateName),
          position,
        };
      })
      .filter(Boolean) as Array<{
      key: string;
      stateName: string;
      abbreviation: string;
      position: LatLngExpression;
    }>;
  }, [geojson]);

  if (!geojson) {
    return (
      <div className="map-missing">
        <AlertTriangle size={22} />
        <div>
          <strong>State boundary file missing</strong>
          <p>Add Nigeria state boundaries at <code>data/raw/nigeria_states.geojson</code>. The dashboard will render the choropleth automatically.</p>
        </div>
      </div>
    );
  }

  return (
    <MapContainer
      center={[9.082, 8.6753]}
      zoom={6}
      minZoom={5}
      maxZoom={8}
      maxBounds={[[3.2, 2.2], [14.4, 14.8]]}
      maxBoundsViscosity={1}
      scrollWheelZoom
      className="map"
    >
      <GeoJSON
        key={`${selectedState}-${forecast.length}-${actualRowsKey}`}
        data={geojson}
        style={(feature) => {
          const props = feature?.properties ?? {};
          const stateName = featureStateName(props);
          const actual = actualByState.get(normalizeStateName(stateName));
          const forecastRow = forecastByState.get(normalizeStateName(stateName));
          const risk = useActualRows ? actual?.risk_level : forecastRow?.risk_level;
          const selected = normalizeStateName(selectedState) === normalizeStateName(stateName);
          const fillColor = risk ? riskColors[risk] : "#cbd5e1";
          return {
            color: selected ? "#111827" : "#ffffff",
            opacity: 1,
            weight: selected ? 2.2 : 1,
            fillColor,
            fillOpacity: risk ? 0.94 : 0.62,
            lineCap: "round",
            lineJoin: "round",
          };
        }}
        onEachFeature={(feature, layer: Layer) => {
          const props = feature.properties ?? {};
          const stateName = featureStateName(props);
          const actual = actualByState.get(normalizeStateName(stateName));
          const forecastRow = forecastByState.get(normalizeStateName(stateName));
          layer.on("click", () => onSelectState(actual?.state || forecastRow?.state || stateName));
          layer.bindPopup(
            `<strong>${stateName}</strong><br/>${
              useActualRows
                ? actual
                  ? `${actual.suspected_cases} cases<br/>${actual.risk_level} risk`
                  : "No row for selected period"
                : forecastRow
                  ? `${forecastRow.predicted_cases} predicted cases<br/>${forecastRow.risk_level} risk`
                  : "No forecast row"
            }`
          );
        }}
      />
      {stateLabels.map((label) => (
        <Marker
          key={label.key}
          position={label.position}
          icon={stateLabelIcon(label.abbreviation, label.stateName)}
          interactive={false}
        />
      ))}
    </MapContainer>
  );
}

function RiskLegend() {
  return (
    <div className="risk-legend" aria-label="Risk map legend">
      {(["Low", "Medium", "High"] as RiskLevel[]).map((risk) => (
        <span key={risk}>
          <i style={{ background: riskColors[risk] }} />
          {risk} risk
        </span>
      ))}
    </div>
  );
}

function Bars({ rows }: { rows: ForecastRow[] }) {
  const max = Math.max(...rows.map((row) => row.predicted_cases), 1);
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={`${row.state}-${row.forecast_week}`}>
          <span>Week {row.forecast_week}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(row.predicted_cases / max) * 100}%`, background: riskColors[row.risk_level] }} />
          </div>
          <strong>{row.predicted_cases.toFixed(1)}</strong>
        </div>
      ))}
    </div>
  );
}

function Sparkline({ rows, color }: { rows: HistoryRow[]; color: string }) {
  const values = rows.map((row) => Number(row.suspected_cases ?? 0));
  const width = 96;
  const height = 28;
  const maxValue = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = values.length <= 1 ? 0 : (index / (values.length - 1)) * width;
    const y = height - (value / maxValue) * (height - 4) - 2;
    return [x, y] as [number, number];
  });

  if (values.length < 2) {
    return <span className="sparkline-empty">-</span>;
  }

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Recent case trend">
      <path d={pathFromPoints(points)} style={{ stroke: color }} />
    </svg>
  );
}

function StateRiskSummary({
  rows,
  allHistory,
  selectedPeriod,
}: {
  rows: HistoryRow[];
  allHistory: HistoryRow[];
  selectedPeriod: string;
}) {
  const riskRank: Record<RiskLevel, number> = { High: 0, Medium: 1, Low: 2 };
  const maxCases = Math.max(...rows.map((row) => row.suspected_cases ?? 0), 1);
  const maxDeaths = Math.max(...rows.map((row) => row.deaths ?? 0), 1);
  const tableRows = [...rows].sort((a, b) => {
    const riskDelta = riskRank[a.risk_level] - riskRank[b.risk_level];
    return riskDelta || (b.suspected_cases ?? 0) - (a.suspected_cases ?? 0) || a.state.localeCompare(b.state);
  }).slice(0, 10);

  function trendRowsFor(row: HistoryRow): HistoryRow[] {
    const normalizedState = normalizeStateName(row.state);
    return allHistory
      .filter((historyRow) => {
        if (normalizeStateName(historyRow.state) !== normalizedState) {
          return false;
        }
        if (selectedPeriod === "__latest__") {
          return true;
        }
        return historyRow.year < row.year || (historyRow.year === row.year && historyRow.epi_week <= row.epi_week);
      })
      .sort((a, b) => a.year - b.year || a.epi_week - b.epi_week)
      .slice(-8);
  }

  return (
    <div className="risk-summary-table-wrap">
      <table className="risk-summary-table">
        <thead>
          <tr>
            <th>State</th>
            <th>Risk Level</th>
            <th>Cases</th>
            <th>Deaths</th>
            <th>CFR</th>
            <th>Trend</th>
          </tr>
        </thead>
        <tbody>
          {tableRows.map((row) => (
            <tr key={`${row.state}-${row.year}-${row.epi_week_label ?? row.epi_week}`}>
              <td>{row.state}</td>
              <td>
                <span className="risk-badge" data-risk={row.risk_level}>{row.risk_level}</span>
              </td>
              <td>
                <div className="summary-meter-cell">
                  <div className="summary-meter">
                    <span style={{ width: `${((row.suspected_cases ?? 0) / maxCases) * 100}%`, background: riskColors[row.risk_level] }} />
                  </div>
                  <strong>{row.suspected_cases ?? 0}</strong>
                </div>
              </td>
              <td>
                <div className="summary-meter-cell">
                  <div className="summary-meter deaths-meter">
                    <span style={{ width: `${((row.deaths ?? 0) / maxDeaths) * 100}%` }} />
                  </div>
                  <strong>{row.deaths ?? 0}</strong>
                </div>
              </td>
              <td>{formatPercent(row.cfr)}</td>
              <td><Sparkline rows={trendRowsFor(row)} color={riskColors[row.risk_level]} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [forecast, setForecast] = useState<ForecastRow[]>([]);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [allHistory, setAllHistory] = useState<HistoryRow[]>([]);
  const [geojson, setGeojson] = useState<FeatureCollection | null>(null);
  const [selectedState, setSelectedState] = useState("Lagos");
  const [selectedPeriod, setSelectedPeriod] = useState("__latest__");
  const [selectedKpiYear, setSelectedKpiYear] = useState("__total__");
  const [activePage, setActivePage] = useState<"overview" | "summary">("overview");
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard() {
    setError(null);
    try {
      const [summaryData, forecastData, historyData] = await Promise.all([
        fetchJson<Summary>("/summary"),
        fetchJson<ForecastRow[]>("/forecast"),
        fetchJson<HistoryRow[]>("/history"),
      ]);
      setSummary(summaryData);
      setForecast(forecastData);
      setAllHistory(historyData);
      if (!summaryData.latest.some((row) => normalizeStateName(row.state) === normalizeStateName(selectedState))) {
        setSelectedState(summaryData.latest[0]?.state ?? "Lagos");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load dashboard data.");
    }
  }

  useEffect(() => {
    loadDashboard();
    fetch(`${API_BASE}/boundaries`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => setGeojson(data))
      .catch(() => setGeojson(null));
  }, []);

  useEffect(() => {
    fetchJson<HistoryRow[]>(`/history?state=${encodeURIComponent(selectedState)}`)
      .then(setHistory)
      .catch(() => setHistory([]));
  }, [selectedState]);

  const stateForecast = forecast.filter((row) => normalizeStateName(row.state) === normalizeStateName(selectedState));
  const periodOptions = useMemo(() => {
    const byKey = new Map<string, string>();
    allHistory.forEach((row) => {
      const label = row.epi_week_label ?? String(row.epi_week);
      byKey.set(`${row.year}|${label}`, `${row.year} week ${label}`);
    });
    return Array.from(byKey.entries()).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }));
  }, [allHistory]);
  const filteredRows = useMemo(() => {
    if (selectedPeriod === "__latest__") {
      return summary?.latest ?? [];
    }
    const [year, label] = selectedPeriod.split("|");
    return allHistory.filter((row) => String(row.year) === year && String(row.epi_week_label ?? row.epi_week) === label);
  }, [allHistory, selectedPeriod, summary]);
  const yearOptions = useMemo(() => {
    return Array.from(new Set(allHistory.map((row) => row.year))).sort((a, b) => a - b);
  }, [allHistory]);
  const kpiRows = useMemo(() => {
    if (selectedKpiYear === "__total__") {
      return allHistory;
    }
    return allHistory.filter((row) => String(row.year) === selectedKpiYear);
  }, [allHistory, selectedKpiYear]);
  const kpiCases = selectedKpiYear === "__total__" && summary
    ? summary.total_cases
    : kpiRows.reduce((sum, row) => sum + (row.suspected_cases ?? 0), 0);
  const kpiDeaths = selectedKpiYear === "__total__" && summary
    ? summary.total_deaths
    : kpiRows.reduce((sum, row) => sum + (row.deaths ?? 0), 0);
  const kpiCfr = kpiCases ? kpiDeaths / kpiCases : 0;
  const latestState = filteredRows.find((row) => normalizeStateName(row.state) === normalizeStateName(selectedState));

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">Nigeria cholera intelligence</p>
          <h1>Cholera Risk Dashboard</h1>
        </div>
        <div className="header-actions">
          <div className="header-filter">
            <label htmlFor="kpi-year-filter">Summary</label>
            <select id="kpi-year-filter" value={selectedKpiYear} onChange={(event) => setSelectedKpiYear(event.target.value)}>
              <option value="__total__">Total</option>
              {yearOptions.map((year) => (
                <option key={year} value={String(year)}>{year}</option>
              ))}
            </select>
          </div>
          <div className="header-filter">
            <label htmlFor="epi-week-filter">Epi week</label>
            <select id="epi-week-filter" value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)}>
              <option value="__latest__">Latest report per state</option>
              {periodOptions.map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>
          <button className="icon-button" onClick={loadDashboard} title="Refresh dashboard data">
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <nav className="page-tabs" aria-label="Dashboard pages">
        <button type="button" className={activePage === "overview" ? "active" : ""} onClick={() => setActivePage("overview")}>
          Overview
        </button>
        <button type="button" className={activePage === "summary" ? "active" : ""} onClick={() => setActivePage("summary")}>
          State Risk Summary
        </button>
      </nav>

      {activePage === "overview" ? (
        <>
          <section className="metrics-grid">
            <MetricCard label="States Covered" value={summary ? String(summary.states) : "-"} icon={<Activity size={20} />} />
            <MetricCard label="Total Cases" value={summary ? kpiCases.toLocaleString() : "-"} icon={<BarChart3 size={20} />} />
            <MetricCard label="Total Deaths" value={summary ? kpiDeaths.toLocaleString() : "-"} icon={<AlertTriangle size={20} />} />
            <MetricCard label="CFR" value={summary ? formatPercent(kpiCfr) : "-"} icon={<AlertTriangle size={20} />} />
          </section>

          <section className="dashboard-grid">
            <div className="panel map-panel">
              <div className="panel-header">
                <div>
                  <h2>Risk Map</h2>
                  <p>State color follows the selected reporting period, or latest records by default.</p>
                </div>
              </div>
              <RiskMap geojson={geojson} forecast={forecast} actualRows={filteredRows} selectedState={selectedState} onSelectState={setSelectedState} />
              <RiskLegend />
            </div>

            <aside className="panel">
              <h2>{selectedState}</h2>
              <div className="risk-pill" data-risk={latestState?.risk_level ?? "Low"}>{latestState?.risk_level ?? "No"} current risk</div>
              <div className="detail-list">
                <span>Latest cases</span><strong>{latestState?.suspected_cases ?? "-"}</strong>
                <span>Deaths</span><strong>{latestState?.deaths ?? "-"}</strong>
                <span>CFR</span><strong>{formatPercent(latestState?.cfr)}</strong>
                <span>Reporting week</span><strong>{latestState?.epi_week_label ?? latestState?.epi_week ?? "-"}</strong>
              </div>
              <h3>Forecast</h3>
              <Bars rows={stateForecast} />
            </aside>
          </section>

          <section className="chart-grid">
            <div className="panel">
              <h2>Case Trend</h2>
              <CaseTrendChart rows={history} />
            </div>
            <div className="panel">
              <h2>Forecast</h2>
              <ForecastIntervalChart historyRows={history} forecastRows={stateForecast} />
            </div>
          </section>
        </>
      ) : (
        <section className="summary-page">
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>State Risk Summary</h2>
                <p>Top 10 states for the selected reporting period, ranked by risk level and cases.</p>
              </div>
            </div>
            <StateRiskSummary rows={filteredRows} allHistory={allHistory} selectedPeriod={selectedPeriod} />
          </div>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
