"""
HR Environment Scoring Engine

Composite formula:
  HR Score = 0.25 * batter_power_vs_hand
           + 0.20 * barrel_flyball_profile
           + 0.20 * directional_wind_fit      <- key differentiator
           + 0.15 * pitcher_hr_vulnerability
           + 0.10 * park_factor
           + 0.10 * weather_carry_score

All sub-scores are 0-1 before weighting. Final score is scaled to 0-100.

Directional wind fit logic:
  Wind direction is treated as FROM a compass bearing.
  The batter's primary spray bearing is estimated from handedness + pull/spray/oppo rates
  and the park's field bearings. Alignment of wind-toward with spray-bearing drives the score.
  A 15 mph tailwind perfectly aligned = maximum boost.
  A 15 mph headwind = maximum suppression.
  Perpendicular wind or calm = neutral (0.50 sub-score).
"""

import math

WEIGHTS = {
    "batter_power_vs_hand":     0.25,
    "barrel_flyball_profile":   0.20,
    "directional_wind_fit":     0.20,
    "pitcher_hr_vulnerability": 0.15,
    "park_factor":              0.10,
    "weather_carry_score":      0.10,
}

TIER_THRESHOLDS = {"Elite": 75, "Strong": 55, "Neutral": 35}


def assign_tier(score: float) -> str:
    if score >= TIER_THRESHOLDS["Elite"]:
        return "Elite"
    if score >= TIER_THRESHOLDS["Strong"]:
        return "Strong"
    if score >= TIER_THRESHOLDS["Neutral"]:
        return "Neutral"
    return "Fade"


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _normalize(value: float, lo: float, hi: float) -> float:
    return _clamp01((value - lo) / (hi - lo))


def _compass_to_bearing(direction: str) -> float:
    """Cardinal/intercardinal wind direction → degrees (0=N, 90=E, 180=S, 270=W)."""
    table = {
        "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
        "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
        "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
        "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
    }
    return table.get(direction.upper().strip(), -1)


def _angular_diff_degrees(a: float, b: float) -> float:
    """Smallest absolute angle between two bearings."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ---------------------------------------------------------------------------
# Sub-score functions
# ---------------------------------------------------------------------------

def compute_batter_power_vs_hand(batter: dict, pitcher_hand: str) -> float:
    """
    SLG split vs pitcher handedness.
    SLG range assumed 0.150 (feeble) … 0.700 (elite power).
    """
    key = "vs_LHP_slg" if pitcher_hand == "L" else "vs_RHP_slg"
    slg = batter.get(key, 0.370)
    return _normalize(slg, 0.150, 0.700)


def compute_barrel_flyball_profile(batter: dict) -> float:
    """
    Weighted composite of barrel rate, fly-ball rate, and hard-hit rate.
    Barrel rate 0-20%, fly-ball rate 20-55%, hard-hit rate 20-55%.
    Barrel is weighted most heavily — it's the strongest HR predictor.
    """
    barrel   = batter.get("barrel_rate",   0.08)
    flyball  = batter.get("flyball_rate",  0.35)
    hard_hit = batter.get("hard_hit_rate", 0.38)

    b = _normalize(barrel,   0.00, 0.20)
    f = _normalize(flyball,  0.20, 0.55)
    h = _normalize(hard_hit, 0.20, 0.55)

    return 0.50 * b + 0.30 * f + 0.20 * h


def compute_directional_wind_fit(
    batter: dict,
    park: dict,
    wind_speed: float,
    wind_direction: str,
) -> float:
    """
    Estimates whether the wind helps THIS batter based on their spray profile.

    Steps:
    1. Identify the park's field bearings (LF, CF, RF from home plate).
    2. Determine batter's weighted spray bearing from pull/center/oppo rates
       and handedness.
    3. Convert wind direction (FROM) → wind direction (TOWARD).
    4. Alignment = cos(angle between wind_toward and spray_bearing).
    5. Scale by wind speed (cap effect at ~20 mph).

    Returns 0-1:
      0.50 = calm or perpendicular wind (neutral)
      1.00 = strong tailwind perfectly aligned with batter's spray
      0.00 = strong headwind perfectly opposing batter's spray
    """
    if wind_speed < 1 or wind_direction.upper() in ("CALM", ""):
        return 0.50

    wind_from = _compass_to_bearing(wind_direction)
    if wind_from < 0:
        return 0.50

    wind_toward = (wind_from + 180) % 360  # direction wind is blowing toward

    hand     = batter.get("batter_hand", "R")
    pull_pct = batter.get("pull_rate",   0.40)
    oppo_pct = batter.get("oppo_rate",   0.25)
    cent_pct = max(0.0, 1.0 - pull_pct - oppo_pct)

    lf_b = park.get("lf_bearing", 270)
    cf_b = park.get("cf_bearing", 315)
    rf_b = park.get("rf_bearing",  45)

    # LHH pulls to RF, goes oppo to LF; RHH is mirrored
    if hand == "L":
        pull_b, oppo_b = rf_b, lf_b
    else:
        pull_b, oppo_b = lf_b, rf_b

    # Circular (unit-vector) weighted average of spray directions
    def _v(deg):
        r = math.radians(deg)
        return math.cos(r), math.sin(r)

    vx = pull_pct * _v(pull_b)[0] + cent_pct * _v(cf_b)[0] + oppo_pct * _v(oppo_b)[0]
    vy = pull_pct * _v(pull_b)[1] + cent_pct * _v(cf_b)[1] + oppo_pct * _v(oppo_b)[1]
    spray_bearing = math.degrees(math.atan2(vy, vx)) % 360

    angle_diff = _angular_diff_degrees(wind_toward, spray_bearing)
    alignment  = math.cos(math.radians(angle_diff))  # -1.0 … +1.0

    # Speed factor: meaningful above 5 mph, caps at 20 mph
    speed_factor = _clamp01((wind_speed - 3) / 17)

    # Map [-1,1] alignment × [0,1] speed → [0,1] output centered at 0.5
    return _clamp01(0.50 + 0.50 * alignment * speed_factor)


def compute_pitcher_hr_vulnerability(pitcher: dict, batter_hand: str) -> float:
    """
    HR/9 allowed split vs this batter's side.
    Range assumed 0.3 (suppressor) … 3.0 (very vulnerable).
    """
    key = "hr_per_9_vs_L" if batter_hand == "L" else "hr_per_9_vs_R"
    hr9 = pitcher.get(key, pitcher.get("hr_per_9", 1.2))
    return _normalize(hr9, 0.30, 3.00)


def compute_park_factor(park: dict, batter_hand: str) -> float:
    """
    HR park factor split by batter hand where available.
    1.00 = neutral, range ~0.70 … 1.40.
    """
    if batter_hand == "L":
        factor = park.get("hr_factor_L", park.get("hr_factor", 1.00))
    else:
        factor = park.get("hr_factor_R", park.get("hr_factor", 1.00))
    return _normalize(factor, 0.70, 1.40)


def compute_weather_carry_score(temp: float, humidity: float = 50.0) -> float:
    """
    Hot, dry air increases fly-ball carry; cold or humid air reduces it.
    Temp range: 35°F (suppressed) … 95°F (aided).
    Humidity has a secondary inverse effect.
    """
    t = _normalize(temp, 35.0, 95.0)
    h = _normalize(100 - humidity, 40, 90)
    return 0.80 * t + 0.20 * h


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_hr_score(
    batter: dict,
    pitcher: dict,
    park: dict,
    weather: dict,
    pitcher_hand: str,
) -> dict:
    """
    Compute full HR environment score for one batter.
    Switch hitters bat opposite the pitcher hand.
    Returns dict with all sub-scores, composite score, tier, and effective hand.
    """
    hand = batter.get("batter_hand", "R")
    if hand == "S":
        hand = "L" if pitcher_hand == "R" else "R"

    wind_speed = weather.get("wind_speed", 0)
    wind_dir   = weather.get("wind_direction", "CALM")
    temp       = weather.get("temp", 72)
    humidity   = weather.get("humidity", 50)

    sub = {
        "batter_power_vs_hand":     compute_batter_power_vs_hand(batter, pitcher_hand),
        "barrel_flyball_profile":   compute_barrel_flyball_profile(batter),
        "directional_wind_fit":     compute_directional_wind_fit(batter, park, wind_speed, wind_dir),
        "pitcher_hr_vulnerability": compute_pitcher_hr_vulnerability(pitcher, hand),
        "park_factor":              compute_park_factor(park, hand),
        "weather_carry_score":      compute_weather_carry_score(temp, humidity),
    }

    raw   = sum(WEIGHTS[k] * v for k, v in sub.items())
    score = round(raw * 100, 1)

    return {
        **sub,
        "hr_score":      score,
        "tier":          assign_tier(score),
        "effective_hand": hand,
    }


def generate_explanation(
    batter: dict,
    pitcher: dict,
    park: dict,
    weather: dict,
    scores: dict,
) -> str:
    """Build a concise pipe-delimited explanation string for the score."""
    hand        = scores["effective_hand"]
    pitcher_hand = pitcher.get("hand", "R")
    wind_speed  = weather.get("wind_speed", 0)
    wind_dir    = weather.get("wind_direction", "CALM")
    temp        = weather.get("temp", 72)
    parts       = []

    pvh = scores["batter_power_vs_hand"]
    slg_key = "vs_LHP_slg" if pitcher_hand == "L" else "vs_RHP_slg"
    slg = batter.get(slg_key, 0.370)
    if pvh >= 0.65:
        parts.append(f"Strong vs {pitcher_hand}HP (SLG {slg:.3f})")
    elif pvh <= 0.30:
        parts.append(f"Weak vs {pitcher_hand}HP (SLG {slg:.3f})")

    bfp = scores["barrel_flyball_profile"]
    barrel  = batter.get("barrel_rate", 0.08)
    flyball = batter.get("flyball_rate", 0.35)
    if bfp >= 0.65:
        parts.append(f"Elite profile — barrel {barrel:.1%} / FB {flyball:.1%}")
    elif bfp <= 0.30:
        parts.append(f"Weak profile — barrel {barrel:.1%} / FB {flyball:.1%}")

    dwf = scores["directional_wind_fit"]
    if wind_speed >= 5:
        park_name = park.get("name", "this park")
        pull_side = "RF" if hand == "L" else "LF"
        if dwf >= 0.65:
            parts.append(f"Wind {wind_speed} mph {wind_dir} aligns with {hand}HB pull spray → {pull_side} at {park_name}")
        elif dwf <= 0.38:
            parts.append(f"Wind {wind_speed} mph {wind_dir} works against {hand}HB spray at {park_name}")
        else:
            parts.append(f"Wind {wind_speed} mph {wind_dir} roughly neutral for this hitter")

    phv = scores["pitcher_hr_vulnerability"]
    hr9_key = "hr_per_9_vs_L" if hand == "L" else "hr_per_9_vs_R"
    hr9 = pitcher.get(hr9_key, pitcher.get("hr_per_9", 1.2))
    p_name = pitcher.get("name", "Pitcher")
    if phv >= 0.60:
        parts.append(f"{p_name} vulnerable vs {hand}HB (HR/9 {hr9:.2f})")
    elif phv <= 0.30:
        parts.append(f"{p_name} suppresses HR vs {hand}HB (HR/9 {hr9:.2f})")

    pf  = scores["park_factor"]
    pfv = park.get("hr_factor_L" if hand == "L" else "hr_factor_R", park.get("hr_factor", 1.00))
    if pf >= 0.65:
        parts.append(f"{park.get('name', 'Park')} HR-friendly (factor {pfv:.2f})")
    elif pf <= 0.35:
        parts.append(f"{park.get('name', 'Park')} suppresses HR (factor {pfv:.2f})")

    wcs = scores["weather_carry_score"]
    if wcs >= 0.65:
        parts.append(f"Warm ({temp}°F) aids carry")
    elif wcs <= 0.35:
        parts.append(f"Cold ({temp}°F) reduces carry")

    if not parts:
        parts.append("Average across all factors — no standout signal")

    return " | ".join(parts)

