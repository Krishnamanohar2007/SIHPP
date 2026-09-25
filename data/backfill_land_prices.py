"""Replace placeholder CSV land prices while preserving all project rows."""

from __future__ import annotations

import csv
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


CSV_PATH = Path(__file__).with_name("projects.csv")
BASE_PRICE = {"Agricultural": 1_500_000, "Residential": 5_000_000, "Industrial": 3_500_000, "Commercial": 7_000_000, "Barren": 800_000}
STATE_FACTOR = {"Maharashtra": 1.65, "Delhi": 1.90, "Karnataka": 1.45, "Tamil Nadu": 1.35, "Telangana": 1.30, "Gujarat": 1.25, "Kerala": 1.35, "Uttar Pradesh": 1.05, "Rajasthan": 0.85, "Madhya Pradesh": 0.80, "Bihar": 0.70, "Odisha": 0.75}


def varied_price(project_id: str, land_type: str, state: str) -> str:
    spread = 0.80 + (int(hashlib.sha256(project_id.encode()).hexdigest()[:8], 16) % 41) / 100
    value = Decimal(str(BASE_PRICE.get(land_type, BASE_PRICE["Agricultural"]) * STATE_FACTOR.get(state, 1.0) * spread))
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main() -> None:
    with CSV_PATH.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
        fields = source.seek(0) or csv.DictReader(source).fieldnames
    changed = 0
    for row in rows:
        if Decimal(row["land_price_per_acre"]) == Decimal("2500000.00"):
            row["land_price_per_acre"] = varied_price(row["project_id"], row["land_type"], row["state"])
            changed += 1
    with CSV_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated {changed} placeholder land prices in {CSV_PATH}")


if __name__ == "__main__":
    main()
