"""Create reproducible synthetic land-acquisition project data and SQL seeds."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


DATA_DIR = Path(__file__).parent
CSV_PATH = DATA_DIR / "projects.csv"
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
LAND_TYPES = ["Agricultural", "Residential", "Industrial", "Commercial", "Barren"]
WORDS = ["Greenfield", "Samriddhi", "Eastern", "Regional", "National", "River", "Deccan", "Coastal", "Frontier", "Bharat"]


def status(percentage: float, low: str, partial: str, complete: str) -> str:
    if percentage >= 95:
        return complete
    if percentage >= 35:
        return partial
    return low


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
        land_price = round(float(rng.lognormal(14.4, 0.55) * {"Agricultural": 1.0, "Residential": 1.8, "Industrial": 1.5, "Commercial": 2.2, "Barren": 0.6}[land_type]), 2)
        owners = max(3, int(rng.poisson(max(6, area * 1.7))))
        compensation = float(np.clip(98 - severity * 78 + rng.normal(0, 10), 0, 100))
        possession = float(np.clip(97 - severity * 70 - (100 - compensation) * 0.12 + rng.normal(0, 9), 0, 100))
        rehabilitation = float(np.clip(99 - severity * 82 + rng.normal(0, 11), 0, 100))
        disputes = int(np.clip(rng.poisson(0.4 + severity * 6 + (100 - compensation) / 42), 0, 18))
        base_risk = PROJECT_TYPES[project_type]
        risk = float(np.clip(base_risk + 0.34 * (100 - compensation) + 4.2 * disputes + 0.17 * (100 - possession) + 0.22 * (100 - rehabilitation) + rng.normal(0, 5), 0, 100))
        risk = round(risk, 2)
        delay = round(float(np.clip(0.08 + risk / 125 + rng.normal(0, 0.09), 0.02, 0.98)), 2)
        category = "Low" if risk <= 30 else "Medium" if risk <= 60 else "High"
        rows.append({
            "project_id": f"LAP-{index:04d}", "project_name": f"{rng.choice(WORDS)} {project_type} Project {index:03d}",
            "project_type": project_type, "country": "India", "state": state, "district": district, "land_area": area, "land_type": land_type, "land_price_per_acre": land_price,
            "number_of_owners": owners, "compensation_status": status(compensation, "Not Started", "In Progress", "Completed"),
            "compensation_percentage": round(compensation, 2), "legal_disputes": disputes,
            "land_possession_status": status(possession, "Not Possessed", "Partially Possessed", "Possessed"),
            "land_possession_percentage": round(possession, 2), "rehabilitation_status": status(rehabilitation, "Not Started", "In Progress", "Completed"),
            "rehabilitation_percentage": round(rehabilitation, 2), "risk_score": risk, "delay_probability": delay,
            "risk_category": category, "latitude": round(anchor_lat + float(rng.normal(0, 0.12)), 6), "longitude": round(anchor_lon + float(rng.normal(0, 0.12)), 6),
        })
    return pd.DataFrame(rows)


def main() -> None:
    frame = generate_projects()
    frame.to_csv(CSV_PATH, index=False)
    write_sql(frame)
    print(f"Wrote {len(frame)} projects to {CSV_PATH} and {SQL_PATH}")


if __name__ == "__main__":
    main()
