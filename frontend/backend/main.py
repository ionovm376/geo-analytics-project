from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import json
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
POINTS_FILE = BASE_DIR / "data" / "points.json"

with open(POINTS_FILE, "r", encoding="utf-8") as f:
    points = json.load(f)


class Location(BaseModel):
    lat: float
    lon: float


class BusinessRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    budget: float


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


def get_nearby_points(lat, lon, radius=800):
    nearby = []

    for p in points:
        distance = haversine(lat, lon, p["lat"], p["lon"])
        if distance <= radius:
            nearby.append(p)

    return nearby


def calculate_area_metrics(lat, lon, radius=800):
    nearby = get_nearby_points(lat, lon, radius)

    if not nearby:
        return None

    avg_p = sum(p["P"] for p in nearby) / len(nearby)
    avg_t = sum(p["T"] for p in nearby) / len(nearby)
    avg_i = sum(p["I"] for p in nearby) / len(nearby)
    avg_d = sum(p["D"] for p in nearby) / len(nearby)
    avg_c = sum(p["C"] for p in nearby) / len(nearby)

    score = (
        0.4 * avg_p +
        0.3 * avg_t -
        0.2 * avg_c +
        0.1 * avg_i -
        0.1 * avg_d
    )
    score = max(0, min(score, 1))

    return {
        "radius_m": radius,
        "points_in_radius": len(nearby),
        "avg_population": round(avg_p, 3),
        "avg_traffic": round(avg_t, 3),
        "avg_income": round(avg_i, 3),
        "avg_distance": round(avg_d, 3),
        "avg_competition": round(avg_c, 3),
        "score": round(score, 3),
    }


def estimate_rent_by_location(lat, lon, p, t):
    center_lat = 55.7558
    center_lon = 37.6176

    distance_to_center = haversine(lat, lon, center_lat, center_lon)

    # Чем ближе к центру, тем выше аренда
    center_factor = max(0, 1 - distance_to_center / 20000)

    base_rent = 70000
    center_rent = center_factor * 120000
    area_rent = p * 40000 + t * 25000

    return base_rent + center_rent + area_rent


@app.get("/")
def root():
    return {"message": "Geo Analytics API is running"}


@app.get("/points")
def get_points():
    return points


@app.get("/top_points")
def get_top_points():
    top = sorted(points, key=lambda p: p["Score"], reverse=True)[:10]
    return top


@app.post("/analyze")
def analyze_location(location: Location):
    metrics = calculate_area_metrics(location.lat, location.lon, radius=800)

    if not metrics:
        return {"message": "No data in radius"}

    competitors = sum(
        1 for p in get_nearby_points(location.lat, location.lon, 800)
        if p["C"] > 0.5
    )

    return {
        "radius_m": metrics["radius_m"],
        "points_in_radius": metrics["points_in_radius"],
        "avg_population": metrics["avg_population"],
        "avg_traffic": metrics["avg_traffic"],
        "competitors": competitors,
        "avg_income": metrics["avg_income"],
        "score": metrics["score"],
    }


@app.post("/simulate_business")
def simulate_business(request: BusinessRequest):
    metrics = calculate_area_metrics(request.lat, request.lon, radius=800)

    if not metrics:
        return {"message": "No data in radius"}

    p = metrics["avg_population"]
    t = metrics["avg_traffic"]
    c = metrics["avg_competition"]

    business_configs = {
        "coffee_shop": {
            "name": "Coffee Shop",
            "avg_check": 420,
            "conversion": 0.12,
            "cost_share": 0.45,
        },
        "grocery_store": {
            "name": "Grocery Store",
            "avg_check": 950,
            "conversion": 0.10,
            "cost_share": 0.65,
        },
        "pharmacy": {
            "name": "Pharmacy",
            "avg_check": 750,
            "conversion": 0.08,
            "cost_share": 0.50,
        },
        "bakery": {
            "name": "Bakery",
            "avg_check": 320,
            "conversion": 0.14,
            "cost_share": 0.48,
        },
    }

    cfg = business_configs.get(request.business_type, business_configs["coffee_shop"])

    # Клиентский поток:
    # traffic влияет сильнее, population чуть слабее
    daily_clients = (t * 500 + p * 250) * cfg["conversion"]

    # конкуренция уменьшает поток
    daily_clients *= max(0.55, 1 - c * 0.35)

    # бюджет влияет на масштаб бизнеса
    budget_factor = max(0.7, min(request.budget / 3000000, 1.6))

    monthly_revenue = daily_clients * cfg["avg_check"] * 30 * budget_factor

    # аренда зависит от расположения
    estimated_rent = estimate_rent_by_location(request.lat, request.lon, p, t)

    # прочие расходы
    estimated_costs = monthly_revenue * cfg["cost_share"]

    estimated_profit = monthly_revenue - estimated_rent - estimated_costs

    suitability_score = 0.45 * p + 0.40 * t - 0.15 * c
    suitability_score = max(0, min(suitability_score, 1))

    payback_months = None
    if estimated_profit > 0:
        payback_months = round(request.budget / estimated_profit, 1)

    if estimated_profit > 200000:
        recommendation = "Good option for opening"
    elif estimated_profit > 50000:
        recommendation = "Possible, but needs careful planning"
    elif estimated_profit > 0:
        recommendation = "Low profit, risky investment"
    else:
        recommendation = "Risky location for this business"

    return {
        "business_name": cfg["name"],
        "suitability_score": round(suitability_score, 3),
        "estimated_monthly_revenue": round(monthly_revenue, 0),
        "estimated_monthly_rent": round(estimated_rent, 0),
        "estimated_monthly_costs": round(estimated_costs, 0),
        "estimated_monthly_profit": round(estimated_profit, 0),
        "estimated_payback_months": payback_months,
        "recommendation": recommendation,
    }