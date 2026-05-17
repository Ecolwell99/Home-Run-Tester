"""
Static stadium registry — all 30 MLB parks.

Field bearings: compass degrees from home plate looking toward each field zone.
  0 = North, 90 = East, 180 = South, 270 = West.
  These drive the directional wind model in scoring.py.
  Values are approximate; calibrate from satellite imagery if needed.

Park HR factors: 2024 season (5-yr rolling FanGraphs/Savant values).
  1.00 = neutral, >1 = HR-friendly, <1 = suppressed.
  Split by batter hand where data supports it.

venue_id: MLB Stats API venue identifier (used to match schedule API response).
"""

# keyed by team abbreviation (matches what the MLB Stats schedule API returns)
STADIUMS: dict = {
    "ARI": {
        "venue_id": 15,  "name": "Chase Field",
        "lat": 33.4455,  "lon": -112.0667,
        "hr_factor": 1.05, "hr_factor_L": 1.07, "hr_factor_R": 1.03,
        "lf_bearing": 252, "cf_bearing": 305,  "rf_bearing": 38,
    },
    "ATL": {
        "venue_id": 4705, "name": "Truist Park",
        "lat": 33.8908,  "lon": -84.4678,
        "hr_factor": 1.08, "hr_factor_L": 1.10, "hr_factor_R": 1.06,
        "lf_bearing": 248, "cf_bearing": 302,  "rf_bearing": 42,
    },
    "BAL": {
        "venue_id": 2,    "name": "Oriole Park at Camden Yards",
        "lat": 39.2838,  "lon": -76.6218,
        "hr_factor": 1.06, "hr_factor_L": 1.08, "hr_factor_R": 1.04,
        "lf_bearing": 258, "cf_bearing": 312,  "rf_bearing": 48,
    },
    "BOS": {
        "venue_id": 3,    "name": "Fenway Park",
        "lat": 42.3467,  "lon": -71.0972,
        "hr_factor": 0.92, "hr_factor_L": 0.80, "hr_factor_R": 1.05,
        "lf_bearing": 268, "cf_bearing": 318,  "rf_bearing": 32,
    },
    "CHC": {
        "venue_id": 17,   "name": "Wrigley Field",
        "lat": 41.9484,  "lon": -87.6553,
        "hr_factor": 1.04, "hr_factor_L": 1.04, "hr_factor_R": 1.04,
        "lf_bearing": 250, "cf_bearing": 305,  "rf_bearing": 40,
    },
    "CWS": {
        "venue_id": 4,    "name": "Guaranteed Rate Field",
        "lat": 41.8300,  "lon": -87.6339,
        "hr_factor": 1.03, "hr_factor_L": 1.04, "hr_factor_R": 1.02,
        "lf_bearing": 255, "cf_bearing": 308,  "rf_bearing": 42,
    },
    "CIN": {
        "venue_id": 2602, "name": "Great American Ball Park",
        "lat": 39.0979,  "lon": -84.5067,
        "hr_factor": 1.20, "hr_factor_L": 1.22, "hr_factor_R": 1.18,
        "lf_bearing": 260, "cf_bearing": 310,  "rf_bearing": 40,
    },
    "CLE": {
        "venue_id": 5,    "name": "Progressive Field",
        "lat": 41.4962,  "lon": -81.6852,
        "hr_factor": 0.97, "hr_factor_L": 0.96, "hr_factor_R": 0.98,
        "lf_bearing": 252, "cf_bearing": 308,  "rf_bearing": 44,
    },
    "COL": {
        "venue_id": 19,   "name": "Coors Field",
        "lat": 39.7559,  "lon": -104.9942,
        "hr_factor": 1.38, "hr_factor_L": 1.40, "hr_factor_R": 1.36,
        "lf_bearing": 255, "cf_bearing": 308,  "rf_bearing": 42,
    },
    "DET": {
        "venue_id": 2394, "name": "Comerica Park",
        "lat": 42.3390,  "lon": -83.0485,
        "hr_factor": 0.94, "hr_factor_L": 0.93, "hr_factor_R": 0.95,
        "lf_bearing": 250, "cf_bearing": 310,  "rf_bearing": 48,
    },
    "HOU": {
        "venue_id": 2392, "name": "Minute Maid Park",
        "lat": 29.7573,  "lon": -95.3555,
        "hr_factor": 1.12, "hr_factor_L": 1.18, "hr_factor_R": 1.08,
        "lf_bearing": 255, "cf_bearing": 315,  "rf_bearing": 50,
    },
    "KC":  {
        "venue_id": 7,    "name": "Kauffman Stadium",
        "lat": 39.0517,  "lon": -94.4803,
        "hr_factor": 0.95, "hr_factor_L": 0.94, "hr_factor_R": 0.96,
        "lf_bearing": 260, "cf_bearing": 315,  "rf_bearing": 45,
    },
    "LAA": {
        "venue_id": 1,    "name": "Angel Stadium",
        "lat": 33.8003,  "lon": -117.8827,
        "hr_factor": 0.97, "hr_factor_L": 0.97, "hr_factor_R": 0.97,
        "lf_bearing": 250, "cf_bearing": 305,  "rf_bearing": 38,
    },
    "LAD": {
        "venue_id": 22,   "name": "Dodger Stadium",
        "lat": 34.0739,  "lon": -118.2400,
        "hr_factor": 0.96, "hr_factor_L": 0.96, "hr_factor_R": 0.96,
        "lf_bearing": 248, "cf_bearing": 302,  "rf_bearing": 40,
    },
    "MIA": {
        "venue_id": 4169, "name": "loanDepot Park",
        "lat": 25.7781,  "lon": -80.2197,
        "hr_factor": 0.84, "hr_factor_L": 0.83, "hr_factor_R": 0.85,
        "lf_bearing": 255, "cf_bearing": 310,  "rf_bearing": 42,
    },
    "MIL": {
        "venue_id": 32,   "name": "American Family Field",
        "lat": 43.0280,  "lon": -87.9712,
        "hr_factor": 1.06, "hr_factor_L": 1.08, "hr_factor_R": 1.04,
        "lf_bearing": 252, "cf_bearing": 306,  "rf_bearing": 40,
    },
    "MIN": {
        "venue_id": 3312, "name": "Target Field",
        "lat": 44.9817,  "lon": -93.2781,
        "hr_factor": 1.02, "hr_factor_L": 1.03, "hr_factor_R": 1.01,
        "lf_bearing": 255, "cf_bearing": 310,  "rf_bearing": 45,
    },
    "NYM": {
        "venue_id": 3289, "name": "Citi Field",
        "lat": 40.7570,  "lon": -73.8458,
        "hr_factor": 0.95, "hr_factor_L": 0.93, "hr_factor_R": 0.97,
        "lf_bearing": 250, "cf_bearing": 305,  "rf_bearing": 40,
    },
    "NYY": {
        "venue_id": 3313, "name": "Yankee Stadium",
        "lat": 40.8296,  "lon": -73.9262,
        "hr_factor": 1.15, "hr_factor_L": 1.28, "hr_factor_R": 1.05,
        "lf_bearing": 250, "cf_bearing": 305,  "rf_bearing": 45,
    },
    "OAK": {
        "venue_id": 10,   "name": "Oakland Coliseum",
        "lat": 37.7516,  "lon": -122.2005,
        "hr_factor": 0.88, "hr_factor_L": 0.87, "hr_factor_R": 0.89,
        "lf_bearing": 248, "cf_bearing": 305,  "rf_bearing": 40,
    },
    "PHI": {
        "venue_id": 2681, "name": "Citizens Bank Park",
        "lat": 39.9057,  "lon": -75.1665,
        "hr_factor": 1.10, "hr_factor_L": 1.12, "hr_factor_R": 1.08,
        "lf_bearing": 252, "cf_bearing": 308,  "rf_bearing": 44,
    },
    "PIT": {
        "venue_id": 31,   "name": "PNC Park",
        "lat": 40.4469,  "lon": -80.0057,
        "hr_factor": 0.93, "hr_factor_L": 0.92, "hr_factor_R": 0.94,
        "lf_bearing": 248, "cf_bearing": 302,  "rf_bearing": 38,
    },
    "SD":  {
        "venue_id": 2680, "name": "Petco Park",
        "lat": 32.7073,  "lon": -117.1566,
        "hr_factor": 0.88, "hr_factor_L": 0.90, "hr_factor_R": 0.86,
        "lf_bearing": 245, "cf_bearing": 300,  "rf_bearing": 355,
    },
    "SEA": {
        "venue_id": 680,  "name": "T-Mobile Park",
        "lat": 47.5914,  "lon": -122.3325,
        "hr_factor": 0.94, "hr_factor_L": 0.94, "hr_factor_R": 0.94,
        "lf_bearing": 250, "cf_bearing": 308,  "rf_bearing": 42,
    },
    "SF":  {
        "venue_id": 2395, "name": "Oracle Park",
        "lat": 37.7786,  "lon": -122.3893,
        "hr_factor": 0.82, "hr_factor_L": 0.80, "hr_factor_R": 0.84,
        "lf_bearing": 240, "cf_bearing": 295,  "rf_bearing": 350,
    },
    "STL": {
        "venue_id": 2889, "name": "Busch Stadium",
        "lat": 38.6226,  "lon": -90.1928,
        "hr_factor": 0.96, "hr_factor_L": 0.95, "hr_factor_R": 0.97,
        "lf_bearing": 252, "cf_bearing": 308,  "rf_bearing": 44,
    },
    "TB":  {
        "venue_id": 12,   "name": "Tropicana Field",
        "lat": 27.7682,  "lon": -82.6534,
        "hr_factor": 0.95, "hr_factor_L": 0.94, "hr_factor_R": 0.96,
        "lf_bearing": 255, "cf_bearing": 310,  "rf_bearing": 45,
        # dome — wind model not applicable; directional_wind_fit will return 0.50
    },
    "TEX": {
        "venue_id": 5325, "name": "Globe Life Field",
        "lat": 32.7473,  "lon": -97.0845,
        "hr_factor": 1.13, "hr_factor_L": 1.15, "hr_factor_R": 1.11,
        "lf_bearing": 252, "cf_bearing": 308,  "rf_bearing": 44,
        # retractable roof — wind model disabled when roof is closed
    },
    "TOR": {
        "venue_id": 14,   "name": "Rogers Centre",
        "lat": 43.6414,  "lon": -79.3894,
        "hr_factor": 1.04, "hr_factor_L": 1.06, "hr_factor_R": 1.02,
        "lf_bearing": 252, "cf_bearing": 308,  "rf_bearing": 44,
        # retractable roof — wind model disabled when roof is closed
    },
    "WSH": {
        "venue_id": 3309, "name": "Nationals Park",
        "lat": 38.8730,  "lon": -77.0074,
        "hr_factor": 1.02, "hr_factor_L": 1.03, "hr_factor_R": 1.01,
        "lf_bearing": 250, "cf_bearing": 308,  "rf_bearing": 44,
    },
}

# Dome/retractable-roof parks: wind model is suppressed (returns 0.50) when roof is closed.
# The schedule API doesn't reliably report roof state so we conservatively flag all
# fully enclosed parks; partially open/retractable remain user-configurable.
DOME_PARKS = {"TB"}                        # always indoors
RETRACTABLE_PARKS = {"TEX", "TOR", "MIA", "ARI", "HOU", "MIL", "SEA"}

# MLB Stats API venue_id → team abbreviation (reverse lookup)
VENUE_TO_TEAM: dict[int, str] = {v["venue_id"]: k for k, v in STADIUMS.items()}
