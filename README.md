# MLB Home Run Probability Screener

A Streamlit dashboard that ranks batters in today's starting lineups by how favorable their HR environment is — with a directional wind model that accounts for batter handedness and spray tendency.

---

## Quick start

```bash
pip install streamlit pandas
cd mlb_hr_screener
streamlit run app.py
```

---

## File structure

| File | Role |
|---|---|
| `app.py` | Streamlit UI — filters, ranked cards, raw table |
| `scoring.py` | All scoring logic — self-contained, no I/O |
| `data_loader.py` | Data assembly layer — swap API implementations here |
| `sample_data.py` | Static mock data for two games (NYY@BOS, ARI@COL) |

---

## Composite score formula

```
HR Score =
  0.25 × batter_power_vs_hand      (SLG split vs pitcher handedness)
  0.20 × barrel_flyball_profile    (barrel rate + fly-ball rate + hard-hit rate)
  0.20 × directional_wind_fit      (wind vector vs spray direction — key differentiator)
  0.15 × pitcher_hr_vulnerability  (HR/9 allowed vs this batter's side)
  0.10 × park_factor               (HR park factor split by batter hand)
  0.10 × weather_carry_score       (temperature + humidity carry effect)
```

Score is normalized to 0–100 and tiered:

| Tier | Score |
|---|---|
| Elite | ≥ 75 |
| Strong | 55–74 |
| Neutral | 35–54 |
| Fade | < 35 |

---

## Directional wind model

The key differentiator vs. naive "wind blowing out = good" approaches:

1. The batter's **spray bearing** is estimated as a weighted average of their pull/center/oppo field bearings, adjusted for handedness (LHH pulls toward RF; RHH pulls toward LF).
2. The wind direction (reported as *from*) is converted to a *toward* bearing.
3. **Alignment** = cos(angle between wind_toward and spray_bearing). Ranges from +1 (perfect tailwind) to -1 (perfect headwind).
4. **Speed factor** scales the effect linearly from 3 mph (noise floor) to 20 mph (capped).
5. Output maps to 0–1, where 0.50 = calm or perpendicular wind.

> **Example:** 14 mph wind from SE blows toward NW. A LHH pull hitter at Coors sprays toward RF (~195°), but wind blows to NW (~315°). Those are ~120° apart — a poor alignment. Contrast with a RHH pull hitter whose spray goes toward LF (~255°), which is much closer to NW — so the same wind helps them meaningfully more.

---

## Connecting real APIs

Each `_load_*` function in `data_loader.py` has a TODO comment with the source and endpoint. Replace the function body and keep the same return shape.

| Function | Suggested source |
|---|---|
| `_load_games()` | MLB Stats API — `/schedule` |
| `_load_lineups()` | MLB Stats API — `/game/{gamePk}/feed/live` |
| `_load_pitchers()` | Baseball Savant pitcher splits; FanGraphs |
| `_load_batters()` | Baseball Savant Statcast; FanGraphs batter splits |
| `_load_parks()` | Baseball Savant park factors + static compass bearing lookup |
| `_load_weather()` | OpenWeatherMap (stadium lat/lon) or WeatherAPI |

---

## Key data fields

### Batter
| Field | Description |
|---|---|
| `vs_RHP_slg` / `vs_LHP_slg` | Slugging pct split vs pitcher hand |
| `barrel_rate` | Barrels / PA (Statcast) |
| `flyball_rate` | Fly ball % of batted balls |
| `hard_hit_rate` | Exit velocity ≥ 95 mph rate |
| `pull_rate` / `oppo_rate` | Spray direction tendencies |

### Pitcher
| Field | Description |
|---|---|
| `hr_per_9_vs_L` / `hr_per_9_vs_R` | HR/9 allowed split by batter side |

### Park
| Field | Description |
|---|---|
| `hr_factor_L` / `hr_factor_R` | HR park factor by batter hand |
| `lf_bearing` / `cf_bearing` / `rf_bearing` | Compass bearing from home plate to each field (degrees from North) |

### Weather
| Field | Description |
|---|---|
| `wind_speed` | mph |
| `wind_direction` | Cardinal/intercardinal — direction wind blows **from** |
| `temp` | °F |
| `humidity` | % relative humidity |
