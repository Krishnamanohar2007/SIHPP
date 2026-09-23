"""Generate deterministic synthetic land-acquisition risk data."""
import csv
from pathlib import Path
from random import Random

OUTPUT = Path(__file__).parent / "generated" / "land_parcels.csv"
RANDOM = Random(26017)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index in range(1, 101):
        dispute = RANDOM.choice([0, 0, 0, 1])
        flood = RANDOM.randint(0, 100)
        encroachment = RANDOM.randint(0, 100)
        rows.append({"parcel_id": f"LP-{index:04d}", "district": RANDOM.choice(["Narmada", "Sundargarh", "Dhar", "Kalahandi"]), "area_hectares": round(RANDOM.uniform(0.5, 25), 2), "ownership_dispute": dispute, "flood_exposure": flood, "encroachment_signal": encroachment, "risk_score": min(100, dispute * 40 + flood // 3 + encroachment // 3)})
    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
