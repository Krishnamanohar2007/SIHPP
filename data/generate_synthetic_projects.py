"""Create reproducible synthetic land-acquisition project data and SQL seeds.

Two artifacts are produced:

``projects.csv``
    Operational register that matches the API project schema exactly, so the
    file stays valid for the bulk-upload endpoint and the CSV export.

``training_history.csv``
    Supervised learning table. It repeats every operational column and adds the
    labels the predictive platform needs: a portfolio-level ``delayed`` flag,
    one ``delayed_<stage>`` flag per lifecycle stage, and the realised schedule
    (``expected_completion_days`` / ``actual_completion_days``) for the subset
    of historical projects that have already closed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(__file__).parent
CSV_PATH = DATA_DIR / "projects.csv"
HISTORY_PATH = DATA_DIR / "training_history.csv"
SQL_PATH = DATA_DIR / "seed.sql"
RANDOM_SEED = 26017
PROJECT_COUNT = 750

# District anchor coordinates and conservative local spreads keep points plausible.
LOCATIONS = {
    "Maharashtra": [("Pune", 18.5204, 73.8567), ("Nagpur", 21.1458, 79.0882), ("Nashik", 19.9975, 73.7898)],
    "Uttar Pradesh": [("Lucknow", 26.8467, 80.9462), ("Prayagraj", 25.4358, 81.8463), ("Gautam Buddha Nagar", 28.5355, 77.3910)],
    "Rajasthan": [("Jaipur", 26.9124, 75.7873), ("Udaipur", 24.5854, 73.7125), ("Kota", 25.2138, 75.8648)],
    "Gujarat": [("Ahmedabad", 23.0225, 72.5714), ("Kutch", 23.7337, 69.8597), ("Surat", 21.1702, 72.8311)],
    "Karnataka": [("Bengaluru Urban", 12.9716, 77.5946), ("Mysuru", 12.2958, 76.6394), ("Belagavi", 15.8497, 74.4977)],
    "Tamil Nadu": [("Chengalpattu", 12.6918, 79.9767), ("Coimbatore", 11.0168, 76.9558), ("Tiruchirappalli", 10.7905, 78.7047)],
    "Madhya Pradesh": [("Indore", 22.7196, 75.8577), ("Bhopal", 23.2599, 77.4126), ("Dhar", 22.5971, 75.3030)],
    "Odisha": [("Khordha", 20.2961, 85.8245), ("Sundargarh", 22.1167, 84.0333), ("Kalahandi", 19.9137, 83.1649)],
    "Bihar": [("Patna", 25.5941, 85.1376), ("Gaya", 24.7955, 84.9994), ("Muzaffarpur", 26.1209, 85.3647)],
    "Telangana": [("Rangareddy", 17.3850, 78.4867), ("Warangal", 17.9689, 79.5941), ("Nalgonda", 17.0575, 79.2684)],
}
PROJECT_TYPES = {
    "National Highway": 9, "Railway Corridor": 12, "Irrigation Canal": 7,
    "Industrial Corridor": 16, "Solar Park": 5, "Transmission Line": 8,
    "Metro Rail": 18, "Logistics Park": 11, "Airport Expansion": 15,
}
# Sanctioned acquisition duration in days, used as the schedule baseline.
BASELINE_DAYS = {
    "National Highway": 540, "Railway Corridor": 720, "Irrigation Canal": 480,
    "Industrial Corridor": 900, "Solar Park": 360, "Transmission Line": 420,
    "Metro Rail": 1080, "Logistics Park": 480, "Airport Expansion": 960,
}
LAND_TYPES = ["Agricultural", "Residential", "Industrial", "Commercial", "Barren"]
LIFECYCLE_STAGES = ["Pre-notification", "Notification", "Compensation", "Possession", "Rehabilitation", "Completed"]
# Stage names used by the per-stage delay models, in lifecycle order.
STAGES = ["Notification", "Compensation", "Possession", "Rehabilitation", "Legal resolution"]
STAGE_LABELS = [f"delayed_{stage.lower().replace(' ', '_')}" for stage in STAGES]
WORDS = ["Greenfield", "Samriddhi", "Eastern", "Regional", "National", "River", "Deccan", "Coastal", "Frontier", "Bharat"]

# Columns that mirror the operational API schema, in API field order.
PROJECT_COLUMNS = [
    "project_id", "project_name", "project_type", "country", "state", "district",
    "land_area", "land_type", "land_price_per_acre", "number_of_owners", "affected_families",
    "approval_timeline_days", "documentation_completeness", "stakeholder_responsiveness",
    "historical_performance_score", "lifecycle_stage", "compensation_status",
    "compensation_percentage", "legal_disputes", "land_possession_status",
    "land_possession_percentage", "rehabilitation_status", "rehabilitation_percentage",
    "risk_score", "delay_probability", "risk_category", "latitude", "longitude",
]
HISTORY_COLUMNS = PROJECT_COLUMNS + ["delayed", *STAGE_LABELS, "expected_completion_days", "actual_completion_days", "is_closed"]


def status(percentage: float, low: str, partial: str, complete: str) -> str:
    if percentage >= 95:
        return complete
    if percentage >= 35:
        return partial
    return low


def risk_from_rule(project_type: str, compensation: float, disputes: int, possession: float, rehabilitation: float,
                   documentation: float, stakeholder: float, historical: float, approval_days: int) -> float:
    """Transparent risk rule shared with the training pipeline and the API."""
    base = PROJECT_TYPES.get(project_type, 10)
    return float(np.clip(
        base
        + 0.30 * (100 - compensation)
        + 3.8 * disputes
        + 0.15 * (100 - possession)
        + 0.19 * (100 - rehabilitation)
        + 0.11 * (100 - documentation)
        + 0.09 * (100 - stakeholder)
        + 0.08 * (100 - historical)
        + 0.010 * approval_days,
        0, 100,
    ))


def sql_value(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, (bool, np.bool_)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.4f}"
    return str(value)


def write_sql(frame: pd.DataFrame) -> None:
    columns = ", ".join(frame.columns)
    statements = [
        "-- Synthetic data only. Do not use for operational or legal decisions.",
        "BEGIN;",
    ]
    for row in frame.itertuples(index=False, name=None):
        statements.append(f"INSERT INTO projects ({columns}) VALUES ({', '.join(sql_value(value) for value in row)});")
    statements.append("COMMIT;")
    SQL_PATH.write_text("\n".join(statements) + "\n", encoding="utf-8")


def generate_projects(count: int = PROJECT_COUNT, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Return the full training table; the operational columns are a subset."""
    rng = np.random.default_rng(seed)
    states = list(LOCATIONS)
    types = list(PROJECT_TYPES)
    rows: list[dict[str, object]] = []
    for index in range(1, count + 1):
        project_type = str(rng.choice(types))
        state = str(rng.choice(states))
        district, anchor_lat, anchor_lon = LOCATIONS[state][int(rng.integers(0, len(LOCATIONS[state])))]
        land_type = str(rng.choice(LAND_TYPES, p=[0.52, 0.16, 0.14, 0.08, 0.10]))
        severity = float(rng.beta(2.3, 3.0))
        area = round(float(rng.lognormal(5.2, 0.75)), 2)
        state_factor = {"Maharashtra": 1.65, "Uttar Pradesh": 1.05, "Rajasthan": 0.85, "Gujarat": 1.25, "Karnataka": 1.45, "Tamil Nadu": 1.35, "Madhya Pradesh": 0.80, "Odisha": 0.75, "Bihar": 0.70, "Telangana": 1.30}[state]
        base_price = {"Agricultural": 1_500_000, "Residential": 5_000_000, "Industrial": 3_500_000, "Commercial": 7_000_000, "Barren": 800_000}[land_type]
        land_price = round(float(base_price * state_factor * rng.uniform(0.80, 1.20)), 2)
        owners = max(3, int(rng.poisson(max(6, area * 1.7))))
        families = max(0, int(owners * rng.uniform(0.55, 1.35)))
        compensation = float(np.clip(98 - severity * 78 + rng.normal(0, 10), 0, 100))
        possession = float(np.clip(97 - severity * 70 - (100 - compensation) * 0.12 + rng.normal(0, 9), 0, 100))
        rehabilitation = float(np.clip(99 - severity * 82 + rng.normal(0, 11), 0, 100))
        disputes = int(np.clip(rng.poisson(0.4 + severity * 6 + (100 - compensation) / 42), 0, 18))
        # Administrative drivers. Severe cases wait longer for approvals and
        # carry weaker paperwork, stakeholder response and past performance.
        approval_days = int(np.clip(rng.normal(90 + severity * 320, 55), 0, 900))
        documentation = float(np.clip(99 - severity * 55 + rng.normal(0, 9), 0, 100))
        stakeholder = float(np.clip(97 - severity * 62 + rng.normal(0, 11), 0, 100))
        historical = float(np.clip(96 - severity * 48 + rng.normal(0, 12), 0, 100))
        progress = (compensation + possession + rehabilitation) / 3
        stage = ("Completed" if progress >= 96 else "Rehabilitation" if progress >= 75
                 else "Possession" if progress >= 50 else "Compensation" if progress >= 25
                 else "Notification" if progress >= 8 else "Pre-notification")
        risk = round(risk_from_rule(project_type, compensation, disputes, possession, rehabilitation, documentation, stakeholder, historical, approval_days), 2)
        # Logistic map from the risk rule keeps the probability spread wide enough
        # that a classifier trained on sampled outcomes can recover real signal.
        delay = round(float(np.clip(1 / (1 + np.exp(-(risk - 52) / 11)) + rng.normal(0, 0.03), 0.02, 0.98)), 4)
        category = "Low" if risk <= 30 else "Medium" if risk <= 60 else "High"

        # Ground truth. ``delayed`` is drawn from the modelled probability so a
        # classifier trained on it recovers a calibrated delay probability.
        delayed = int(rng.random() < delay)
        expected_days = int(BASELINE_DAYS[project_type] * rng.uniform(0.9, 1.1))
        overrun = rng.uniform(1.12, 1.95) if delayed else rng.uniform(0.82, 1.08)
        actual_days = int(expected_days * overrun)
        # Only mature projects have a realised schedule to learn from.
        is_closed = bool(stage in {"Completed", "Rehabilitation"} and rng.random() < 0.75)

        # Stage-specific hazards. Each stage is driven by the parameters that
        # actually govern it, so per-stage models learn distinct signals.
        stage_pressure = {
            "Notification": np.clip(0.04 + approval_days / 1400 + (100 - documentation) / 190 + (100 - historical) / 320, 0.02, 0.97),
            "Compensation": np.clip(0.04 + (100 - compensation) / 135 + (100 - stakeholder) / 260 + families / 900, 0.02, 0.97),
            "Possession": np.clip(0.04 + (100 - possession) / 130 + disputes / 26 + (100 - compensation) / 320, 0.02, 0.97),
            "Rehabilitation": np.clip(0.03 + (100 - rehabilitation) / 125 + families / 700 + (100 - stakeholder) / 300, 0.02, 0.97),
            "Legal resolution": np.clip(0.02 + disputes / 16 + (100 - documentation) / 300, 0.02, 0.97),
        }
        row: dict[str, object] = {
            "project_id": f"LAP-{index:04d}", "project_name": f"{rng.choice(WORDS)} {project_type} Project {index:03d}",
            "project_type": project_type, "country": "India", "state": state, "district": district,
            "land_area": area, "land_type": land_type, "land_price_per_acre": land_price,
            "number_of_owners": owners, "affected_families": families,
            "approval_timeline_days": approval_days,
            "documentation_completeness": round(documentation, 2),
            "stakeholder_responsiveness": round(stakeholder, 2),
            "historical_performance_score": round(historical, 2),
            "lifecycle_stage": stage,
            "compensation_status": status(compensation, "Not Started", "In Progress", "Completed"),
            "compensation_percentage": round(compensation, 2), "legal_disputes": disputes,
            "land_possession_status": status(possession, "Not Possessed", "Partially Possessed", "Possessed"),
            "land_possession_percentage": round(possession, 2),
            "rehabilitation_status": status(rehabilitation, "Not Started", "In Progress", "Completed"),
            "rehabilitation_percentage": round(rehabilitation, 2), "risk_score": risk, "delay_probability": delay,
            "risk_category": category,
            "latitude": round(anchor_lat + float(rng.normal(0, 0.12)), 6),
            "longitude": round(anchor_lon + float(rng.normal(0, 0.12)), 6),
            "delayed": delayed,
            "expected_completion_days": expected_days,
            "actual_completion_days": actual_days if is_closed else "",
            "is_closed": is_closed,
        }
        for stage_name, label in zip(STAGES, STAGE_LABELS):
            row[label] = int(rng.random() < float(stage_pressure[stage_name]))
        rows.append(row)
    return pd.DataFrame(rows)[HISTORY_COLUMNS]


def main() -> None:
    history = generate_projects()
    history.to_csv(HISTORY_PATH, index=False)
    operational = history[PROJECT_COLUMNS]
    operational.to_csv(CSV_PATH, index=False)
    write_sql(operational)
    print(f"Wrote {len(history)} projects to {CSV_PATH}, labels to {HISTORY_PATH}, seed to {SQL_PATH}")


if __name__ == "__main__":
    main()
