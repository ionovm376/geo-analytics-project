import json
import math
import random
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

DISTRICTS_FILE = BASE_DIR / "district_population.csv"
METRO_FILE = BASE_DIR / "metro_entrances.csv"
BUS_FILE = BASE_DIR / "bus_stops.csv"
RETAIL_FILE = BASE_DIR / "retail_objects.csv"
OUTPUT_FILE = BASE_DIR / "points.json"

MOSCOW_BBOX = {
    "lat_min": 55.55,
    "lat_max": 55.90,
    "lon_min": 37.35,
    "lon_max": 37.85,
}

MOSCOW_CENTER_LAT = 55.7558
MOSCOW_CENTER_LON = 37.6176

POINTS_COUNT = 200
RADIUS = 800


def haversine(lat1, lon1, lat2, lon2):
    r = 6371000

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )

    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize(val, min_val, max_val):
    if max_val == min_val:
        return 0.0
    return (val - min_val) / (max_val - min_val)


def load_csv(path):
    df = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")

    if len(df.columns) == 1:
        raw_col = str(df.columns[0]).strip().lower()

        if ";" in raw_col:
            df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
        elif "," in raw_col:
            df = pd.read_csv(path, sep=",", encoding="utf-8-sig")

    df.columns = [str(col).strip().lower() for col in df.columns]

    print(path.name, "->", df.columns.tolist())
    return df


def count_nearby(lat, lon, df):
    count = 0
    for _, row in df.iterrows():
        d = haversine(lat, lon, float(row["lat"]), float(row["lon"]))
        if d <= RADIUS:
            count += 1
    return count


def nearest_population(lat, lon, df):
    best = float("inf")
    pop = 0.0

    for _, row in df.iterrows():
        d = haversine(lat, lon, float(row["lat"]), float(row["lon"]))
        if d < best:
            best = d
            pop = float(row["population"])

    return pop


def center_weight(lat, lon):
    distance = haversine(lat, lon, MOSCOW_CENTER_LAT, MOSCOW_CENTER_LON)
    max_distance = 30000  # 30 км
    weight = 1 - min(distance / max_distance, 1)
    return weight


def get_color(score):
    if score > 0.45:
        return "green"
    if score > 0.20:
        return "yellow"
    return "red"


def generate_real_points():
    districts = load_csv(DISTRICTS_FILE)
    metro = load_csv(METRO_FILE)
    bus = load_csv(BUS_FILE)
    retail = load_csv(RETAIL_FILE)

    required_districts = {"lat", "lon", "population"}
    required_points = {"lat", "lon"}

    if not required_districts.issubset(districts.columns):
        raise ValueError(
            f"district_population.csv должен содержать колонки {required_districts}, сейчас: {districts.columns.tolist()}"
        )

    if not required_points.issubset(metro.columns):
        raise ValueError(
            f"metro_entrances.csv должен содержать колонки {required_points}, сейчас: {metro.columns.tolist()}"
        )

    if not required_points.issubset(bus.columns):
        raise ValueError(
            f"bus_stops.csv должен содержать колонки {required_points}, сейчас: {bus.columns.tolist()}"
        )

    if not required_points.issubset(retail.columns):
        raise ValueError(
            f"retail_objects.csv должен содержать колонки {required_points}, сейчас: {retail.columns.tolist()}"
        )

    raw = []

    for _ in range(POINTS_COUNT):
        lat = random.uniform(MOSCOW_BBOX["lat_min"], MOSCOW_BBOX["lat_max"])
        lon = random.uniform(MOSCOW_BBOX["lon_min"], MOSCOW_BBOX["lon_max"])

        population = nearest_population(lat, lon, districts)
        metro_count = count_nearby(lat, lon, metro)
        bus_count = count_nearby(lat, lon, bus)
        retail_count = count_nearby(lat, lon, retail)

        center_factor = center_weight(lat, lon)

        # Чем ближе к центру — тем выше конкуренция
        competitors = retail_count + center_factor * 12
                                                
        # Трафик: метро важнее остановок
        traffic = metro_count * 2 + bus_count

        # Небольшой штраф за центр: в центре дороже и сложнее выйти на рынок
        center_penalty = center_factor * 0.15

        raw.append(
            {
                "lat": lat,
                "lon": lon,
                "p_raw": population,
                "t_raw": traffic,
                "c_raw": competitors,
                "center_penalty": center_penalty,
            }
        )

    p_vals = [p["p_raw"] for p in raw]
    t_vals = [p["t_raw"] for p in raw]
    c_vals = [p["c_raw"] for p in raw]

    p_min, p_max = min(p_vals), max(p_vals)
    t_min, t_max = min(t_vals), max(t_vals)
    c_min, c_max = min(c_vals), max(c_vals)

    result = []

    for p in raw:
        p_norm = normalize(p["p_raw"], p_min, p_max)
        t_norm = normalize(p["t_raw"], t_min, t_max)
        c_norm = normalize(p["c_raw"], c_min, c_max)

        i_norm = p_norm
        d_norm = 1 - t_norm

        score = (
            0.5 * p_norm +
            0.5 * t_norm -
            0.1 * c_norm -
            p["center_penalty"]
        )
        score += random.uniform(-0.05, 0.05)

        score = max(0, min(score, 1))

        result.append(
            {
                "lat": round(p["lat"], 10),
                "lon": round(p["lon"], 10),
                "P": round(p_norm, 4),
                "T": round(t_norm, 4),
                "C": round(c_norm, 4),
                "I": round(i_norm, 4),
                "D": round(d_norm, 4),
                "Score": round(score, 4),
                "color": get_color(score),
            }
        )

    return result


if __name__ == "__main__":
    points = generate_real_points()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(points, f, ensure_ascii=False, indent=2)

    print("points.json создан")