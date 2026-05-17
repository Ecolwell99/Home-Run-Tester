"""
Data loader — live API implementation.

Sources (all free, no auth):
  Schedule + lineups  : MLB Stats API  (statsapi.mlb.com)
  Batter splits       : Baseball Savant batted-ball leaderboard CSV (bulk, one call per hand)
  Pitcher splits      : Baseball Savant pitcher leaderboard CSV (bulk, one call per hand)
  Weather             : wttr.in JSON API (lat/lon per stadium)
  Park factors        : stadiums.py static registry

Stat fetch strategy — two bulk CSV calls get all qualified batters in one shot:
  Savant batted-ball leaderboard vs RHP  → SLG, barrel%, FB%, pull%, oppo%, HH%
  Savant batted-ball leaderboard vs LHP  → same
  Savant pitcher leaderboard vs RHB/LHB → HR/9 by batter side
This avoids per-player loops and rate-limiting.

Fallback chain:
  1. Try live API / CSV call
  2. On any error, log a warning and use midpoint stub so app stays runnable
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any

import requests
import pandas as pd

import sample_data as _sd
import stadiums as _stadiums

log = logging.getLogger(__name__)

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_GAME_URL     = "https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
WTTR_URL         = "https://wttr.in/{lat},{lon}?format=j1"

# Savant leaderboard CSV base — returns all qualified players in one call
SAVANT_BATTER_URL  = "https://baseballsavant.mlb.com/leaderboard/batted-ball"
SAVANT_PITCHER_URL = "https://baseballsavant.mlb.com/statcast_leaderboard"

_SAVANT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; mlb-hr-screener/1.0)"
}


# ── Public API ────────────────────────────────────────────────────────────────

def load_all(date: str | None = None) -> dict[str, Any]:
    target_date = date or datetime.date.today().isoformat()
    log.info("Loading data for %s", target_date)

    games_raw = _fetch_schedule(target_date)
    if not games_raw:
        log.warning("No games found for %s — falling back to sample data", target_date)
        return _sample_bundle()

    games, lineups, park_map = _process_schedule(games_raw)

    # Bulk stat fetches — one DataFrame per split side
    batter_vs_rhp, batter_vs_lhp = _fetch_batter_splits()
    pitcher_vs_rhb, pitcher_vs_lhb = _fetch_pitcher_splits()

    batters  = _build_batter_dict(batter_vs_rhp, batter_vs_lhp)
    pitchers = _build_pitcher_dict(pitcher_vs_rhb, pitcher_vs_lhb)

    # Sample data fills known players not yet in Savant (injured, minor league callups)
    for k, v in _sd.BATTERS.items():
        batters.setdefault(k, v)
    for k, v in _sd.PITCHERS.items():
        pitchers.setdefault(k, v)

    weather = _fetch_all_weather(games)
    parks   = {abbr: _stadiums.STADIUMS[abbr] for abbr in park_map.values()
               if abbr in _stadiums.STADIUMS}

    return dict(games=games, lineups=lineups, pitchers=pitchers,
                parks=parks, weather=weather, batters=batters)


# ── Schedule + lineups ────────────────────────────────────────────────────────

def _fetch_schedule(date: str) -> list[dict]:
    params = {
        "sportId": 1,
        "date":    date,
        "hydrate": "team,venue,probablePitcher(note)",
    }
    try:
        r = requests.get(MLB_SCHEDULE_URL, params=params, timeout=10)
        r.raise_for_status()
        dates = r.json().get("dates", [])
        return dates[0].get("games", []) if dates else []
    except Exception as exc:
        log.warning("Schedule fetch failed: %s", exc)
        return []


def _process_schedule(games_raw: list[dict]) -> tuple[list[dict], dict, dict[str, str]]:
    games, lineups, park_map = [], {}, {}
    for g in games_raw:
        detail = g.get("status", {}).get("detailedState", "")
        if detail in ("Postponed", "Cancelled", "Suspended"):
            continue

        gid       = str(g["gamePk"])
        away_abbr = g["teams"]["away"]["team"].get("abbreviation", "UNK")
        home_abbr = g["teams"]["home"]["team"].get("abbreviation", "UNK")
        venue     = g.get("venue", {}).get("name", "Unknown Park")
        game_time = g.get("gameDate", "TBD")

        games.append({
            "game_id":  gid,
            "away":     away_abbr,
            "home":     home_abbr,
            "park_id":  home_abbr,
            "time":     game_time,
            "label":    f"{away_abbr} @ {home_abbr} — {venue}",
        })
        park_map[gid] = home_abbr
        lineups[gid]  = _fetch_lineup(gid, g, away_abbr, home_abbr)

    return games, lineups, park_map


def _fetch_lineup(game_pk: str, game_meta: dict, away_abbr: str, home_abbr: str) -> dict:
    url = MLB_GAME_URL.format(gamePk=game_pk)
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        feed = r.json()
    except Exception as exc:
        log.warning("Live feed fetch failed for %s: %s", game_pk, exc)
        return _probable_only_lineup(game_meta, away_abbr, home_abbr)

    game_data = feed.get("gameData", {})
    live_data = feed.get("liveData", {})
    players   = game_data.get("players", {})
    teams_box = live_data.get("boxscore", {}).get("teams", {})

    result = {}
    for side, abbr in [("away", away_abbr), ("home", home_abbr)]:
        side_box     = teams_box.get(side, {})
        batters_ids  = side_box.get("batters", [])
        pitchers_ids = side_box.get("pitchers", [])

        batting_order = []
        for pos, pid in enumerate(batters_ids, start=1):
            pdata = players.get(f"ID{pid}", {})
            name  = pdata.get("fullName", str(pid))
            hand  = pdata.get("batSide", {}).get("code", "R")
            key   = _player_key(name)
            batting_order.append((key, pos))
            _ensure_batter_stub(key, name, abbr, hand)

        pitcher_id_mlb = (pitchers_ids[0] if pitchers_ids
                          else game_data.get("probablePitchers", {}).get(side, {}).get("id"))

        pitcher_key = "unknown"
        if pitcher_id_mlb:
            pdata       = players.get(f"ID{pitcher_id_mlb}", {})
            pname       = pdata.get("fullName", str(pitcher_id_mlb))
            phand       = pdata.get("pitchHand", {}).get("code", "R")
            pitcher_key = _player_key(pname)
            _ensure_pitcher_stub(pitcher_key, pname, phand)

        result[abbr] = {
            "pitcher_id":    pitcher_key,
            "batting_order": batting_order or [],
        }
    return result


def _probable_only_lineup(game_meta: dict, away_abbr: str, home_abbr: str) -> dict:
    result = {}
    for side, abbr in [("away", away_abbr), ("home", home_abbr)]:
        prob  = game_meta.get("teams", {}).get(side, {}).get("probablePitcher", {})
        pname = prob.get("fullName", "TBD")
        pkey  = _player_key(pname)
        result[abbr] = {"pitcher_id": pkey, "batting_order": []}
    return result


# ── Savant bulk stat fetches ──────────────────────────────────────────────────

def _fetch_batter_splits() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Two calls to Savant batted-ball leaderboard — one vs RHP, one vs LHP.
    Returns (vs_rhp_df, vs_lhp_df). Both empty on failure.

    Key columns returned by Savant batted-ball CSV:
      player_id, last_name, first_name, player_name,
      b_ab, b_home_run, b_k_percent, b_bb_percent,
      slg_percent, on_base_plus_slg,
      barrel_batted_rate (barrels/BBE),
      hard_hit_percent (EV >= 95 mph),
      anglesweetspotpercent (sweet spot %),
      pull_percent, straightaway_percent, opposite_percent
    """
    year = datetime.date.today().year
    vs_rhp = _savant_batted_ball_csv(year, pitcher_hand="R")
    time.sleep(1.0)
    vs_lhp = _savant_batted_ball_csv(year, pitcher_hand="L")
    return vs_rhp, vs_lhp


def _savant_batted_ball_csv(year: int, pitcher_hand: str) -> pd.DataFrame:
    """
    Savant batted-ball leaderboard CSV — all qualified batters, filtered by pitcher hand.
    min_pa=25 keeps callups with small samples; app will still rank them lower
    because their raw stats won't be elite.
    """
    params = {
        "csv":           "true",
        "type":          "batter",
        "year":          year,
        "min_pa":        25,
        "pitcher_hand":  pitcher_hand,   # "R" or "L"
    }
    try:
        r = requests.get(
            SAVANT_BATTER_URL,
            params=params,
            headers=_SAVANT_HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant batter vs %sHP: %d rows", pitcher_hand, len(df))
        return df
    except Exception as exc:
        log.warning("Savant batter vs %sHP fetch failed: %s", pitcher_hand, exc)
        return pd.DataFrame()


def _fetch_pitcher_splits() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Two calls to Savant pitcher leaderboard — one vs RHB, one vs LHB.
    Returns (vs_rhb_df, vs_lhb_df).
    """
    year = datetime.date.today().year
    vs_rhb = _savant_pitcher_csv(year, batter_hand="R")
    time.sleep(1.0)
    vs_lhb = _savant_pitcher_csv(year, batter_hand="L")
    return vs_rhb, vs_lhb


def _savant_pitcher_csv(year: int, batter_hand: str) -> pd.DataFrame:
    """
    Savant pitcher leaderboard CSV filtered by batter hand.
    Key columns: player_id, player_name, b_home_run, p_formatted_ip,
                 slg_percent, hard_hit_percent, barrel_batted_rate
    """
    params = {
        "csv":          "true",
        "type":         "pitcher",
        "year":         year,
        "min_pa":       20,
        "batter_hand":  batter_hand,   # "R" or "L"
    }
    try:
        r = requests.get(
            SAVANT_PITCHER_URL,
            params=params,
            headers=_SAVANT_HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant pitcher vs %sHB: %d rows", batter_hand, len(df))
        return df
    except Exception as exc:
        log.warning("Savant pitcher vs %sHB fetch failed: %s", batter_hand, exc)
        return pd.DataFrame()


# ── Stat dict builders ────────────────────────────────────────────────────────

# Column name candidates — Savant occasionally renames columns across seasons
_SLG_COLS       = ["slg_percent", "slg"]
_BARREL_COLS    = ["barrel_batted_rate", "brl_pa", "brl_percent"]
_HARD_HIT_COLS  = ["hard_hit_percent", "ev95percent"]
_FB_COLS        = ["flyballs_percent", "fb_percent", "anglesweetspotpercent"]
_PULL_COLS      = ["pull_percent", "pull_rate"]
_OPPO_COLS      = ["opposite_percent", "oppo_percent"]
_HR_COLS        = ["b_home_run", "home_run", "hr"]
_IP_COLS        = ["p_formatted_ip", "ip", "IP"]
_NAME_COLS      = ["player_name", "name", "Name"]
_ID_COLS        = ["player_id", "batter", "pitcher", "mlb_id"]


def _col(row, candidates: list[str], default):
    for c in candidates:
        if c in row.index and pd.notna(row[c]):
            try:
                return float(row[c])
            except (ValueError, TypeError):
                continue
    return default


def _name_from_row(row) -> str:
    for c in _NAME_COLS:
        if c in row.index and pd.notna(row[c]):
            return str(row[c]).strip()
    # fallback: last_name, first_name columns
    last  = str(row.get("last_name",  "")).strip()
    first = str(row.get("first_name", "")).strip()
    if last:
        return f"{first} {last}".strip()
    return "Unknown"


def _ip_to_float(ip_str) -> float:
    """'15.1' → 15.333, '15' → 15.0"""
    try:
        s = str(ip_str).strip()
        if "." in s:
            whole, frac = s.split(".", 1)
            return float(whole) + float(frac) / 3
        return float(s)
    except Exception:
        return 1.0


def _build_batter_dict(
    vs_rhp: pd.DataFrame,
    vs_lhp: pd.DataFrame,
) -> dict:
    """
    Merge vs-RHP and vs-LHP DataFrames into per-batter dicts.
    For each batter, use the split SLG directly for vs_RHP_slg / vs_LHP_slg.
    Barrel, flyball, hard-hit, pull, oppo: average of both splits (full-season profile).
    """
    out: dict[str, dict] = {}

    def _ingest(df: pd.DataFrame, slg_key: str) -> None:
        if df.empty:
            return
        for _, row in df.iterrows():
            name = _name_from_row(row)
            key  = _player_key(name)

            slg      = _col(row, _SLG_COLS,      0.450) / (1 if _col(row, _SLG_COLS, 0.450) <= 1 else 1000)
            barrel   = _col(row, _BARREL_COLS,   10.5)
            hard_hit = _col(row, _HARD_HIT_COLS, 41.5)
            flyball  = _col(row, _FB_COLS,        37.5)
            pull     = _col(row, _PULL_COLS,      40.0)
            oppo     = _col(row, _OPPO_COLS,      24.0)

            # Savant reports rates as 0–100; normalise to 0–1
            barrel   = barrel   / 100 if barrel   > 1 else barrel
            hard_hit = hard_hit / 100 if hard_hit > 1 else hard_hit
            flyball  = flyball  / 100 if flyball  > 1 else flyball
            pull     = pull     / 100 if pull     > 1 else pull
            oppo     = oppo     / 100 if oppo     > 1 else oppo
            slg      = slg      / 1000 if slg     > 1 else slg  # sometimes stored as integer

            if key not in out:
                out[key] = {
                    "player_id":     key,
                    "name":          _short_name(name),
                    "team":          str(row.get("team_name", row.get("team", "MLB"))),
                    "batter_hand":   str(row.get("stand", row.get("b_stand", "R"))),
                    "vs_RHP_slg":    0.450,
                    "vs_LHP_slg":    0.450,
                    "barrel_rate":   barrel,
                    "flyball_rate":  flyball,
                    "hard_hit_rate": hard_hit,
                    "pull_rate":     pull,
                    "oppo_rate":     oppo,
                    "hr_rate":       0.035,
                }
            # Set the split-specific SLG
            out[key][slg_key] = slg
            # Average the profile stats if we already have one side
            for stat, val in [("barrel_rate", barrel), ("flyball_rate", flyball),
                               ("hard_hit_rate", hard_hit), ("pull_rate", pull),
                               ("oppo_rate", oppo)]:
                out[key][stat] = (out[key][stat] + val) / 2

    _ingest(vs_rhp, "vs_RHP_slg")
    _ingest(vs_lhp, "vs_LHP_slg")
    return out


def _build_pitcher_dict(
    vs_rhb: pd.DataFrame,
    vs_lhb: pd.DataFrame,
) -> dict:
    """
    Build pitcher dicts with split HR/9 vs RHB and vs LHB.
    HR/9 = (HR allowed / IP) * 9
    """
    out: dict[str, dict] = {}

    def _hr9(row) -> float:
        hrs = _col(row, _HR_COLS, 0)
        ip  = _ip_to_float(row.get("p_formatted_ip", row.get("ip", row.get("IP", 1))))
        return round((hrs / max(ip, 0.33)) * 9, 3)

    def _ingest(df: pd.DataFrame, hr9_key: str) -> None:
        if df.empty:
            return
        for _, row in df.iterrows():
            name = _name_from_row(row)
            key  = _player_key(name)
            hr9  = _hr9(row)
            hand = str(row.get("p_throws", row.get("throws", "R")))

            if key not in out:
                out[key] = {
                    "pitcher_id":    key,
                    "name":          _short_name(name),
                    "hand":          hand,
                    "hr_per_9":      hr9,
                    "hr_per_9_vs_L": 1.35,
                    "hr_per_9_vs_R": 1.35,
                }
            out[key][hr9_key] = hr9
            out[key]["hr_per_9"] = (out[key].get("hr_per_9", hr9) + hr9) / 2

    _ingest(vs_rhb, "hr_per_9_vs_R")
    _ingest(vs_lhb, "hr_per_9_vs_L")
    return out


# ── Weather ───────────────────────────────────────────────────────────────────

def _fetch_all_weather(games: list[dict]) -> dict:
    weather = {}
    for game in games:
        gid       = game["game_id"]
        home_abbr = game["home"]
        park      = _stadiums.STADIUMS.get(home_abbr, {})
        lat, lon  = park.get("lat"), park.get("lon")

        if home_abbr in _stadiums.DOME_PARKS or lat is None:
            weather[gid] = _dome_weather() if home_abbr in _stadiums.DOME_PARKS else _neutral_weather()
            continue

        weather[gid] = _fetch_wttr(lat, lon)
        time.sleep(0.3)

    return weather


def _fetch_wttr(lat: float, lon: float) -> dict:
    try:
        r = requests.get(WTTR_URL.format(lat=lat, lon=lon), timeout=8, headers=_SAVANT_HEADERS)
        r.raise_for_status()
        cond = r.json()["current_condition"][0]
        return {
            "temp":           int(cond.get("temp_F",          "72")),
            "humidity":       int(cond.get("humidity",         "50")),
            "wind_speed":     int(cond.get("windspeedMiles",    "0")),
            "wind_direction": str(cond.get("winddir16Point", "CALM")),
            "conditions":     str(cond.get("weatherDesc", [{}])[0].get("value", "")),
        }
    except Exception as exc:
        log.warning("Weather fetch failed %.4f,%.4f: %s", lat, lon, exc)
        return _neutral_weather()


def _neutral_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Unknown"}


def _dome_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Dome"}


# ── Player key / name helpers ─────────────────────────────────────────────────

def _player_key(name: str) -> str:
    return (name.lower()
            .replace(" ", "_").replace(".", "").replace("'", "")
            .replace("-", "_").replace(",", ""))


def _short_name(full: str) -> str:
    parts = full.strip().split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else full


# ── Stub registries (populated during lineup fetch) ───────────────────────────

_BATTER_REGISTRY:  dict[str, dict] = {}
_PITCHER_REGISTRY: dict[str, dict] = {}


def _ensure_batter_stub(key: str, name: str, team: str, hand: str) -> None:
    if key not in _BATTER_REGISTRY:
        _BATTER_REGISTRY[key] = {
            "player_id":     key,    "name":          _short_name(name),
            "team":          team,   "batter_hand":   hand,
            "vs_RHP_slg":    0.450,  "vs_LHP_slg":    0.450,
            "barrel_rate":   0.105,  "flyball_rate":   0.375,
            "hard_hit_rate": 0.415,  "pull_rate":      0.40,
            "oppo_rate":     0.24,   "hr_rate":        0.030,
        }


def _ensure_pitcher_stub(key: str, name: str, hand: str) -> None:
    if key not in _PITCHER_REGISTRY:
        _PITCHER_REGISTRY[key] = {
            "pitcher_id":    key,    "name":          _short_name(name),
            "hand":          hand,
            "hr_per_9":      1.35,   "hr_per_9_vs_L": 1.42,
            "hr_per_9_vs_R": 1.28,
        }


# ── Assembly ──────────────────────────────────────────────────────────────────

def build_rows(data: dict) -> list[dict]:
    rows = []
    for game in data["games"]:
        gid     = game["game_id"]
        park    = data["parks"].get(game["park_id"])
        if park is None:
            log.warning("No park entry for %s — skipping %s", game["park_id"], gid)
            continue
        weather = data["weather"].get(gid, _neutral_weather())
        lineup  = data["lineups"].get(gid, {})
        away, home = game["away"], game["home"]

        for batting_team, opp_team in [(away, home), (home, away)]:
            side     = lineup.get(batting_team, {})
            opp_side = lineup.get(opp_team, {})
            if not side or not opp_side:
                continue

            pitcher_id = opp_side.get("pitcher_id", "unknown")
            pitcher = (data["pitchers"].get(pitcher_id)
                       or _PITCHER_REGISTRY.get(pitcher_id)
                       or _sd.PITCHERS.get(pitcher_id)
                       or {"pitcher_id": pitcher_id, "name": pitcher_id,
                           "hand": "R", "hr_per_9": 1.35,
                           "hr_per_9_vs_L": 1.42, "hr_per_9_vs_R": 1.28})

            for player_id, order in side.get("batting_order", []):
                batter = (data["batters"].get(player_id)
                          or _BATTER_REGISTRY.get(player_id)
                          or _sd.BATTERS.get(player_id))
                if batter is None:
                    continue
                rows.append({
                    "batter":        batter,
                    "pitcher":       pitcher,
                    "park":          park,
                    "weather":       weather,
                    "pitcher_hand":  pitcher["hand"],
                    "game_id":       gid,
                    "game_label":    game["label"],
                    "batting_team":  batting_team,
                    "opp_team":      opp_team,
                    "batting_order": order,
                })
    return rows


# ── Sample data fallback ──────────────────────────────────────────────────────

def _sample_bundle() -> dict[str, Any]:
    parks = {abbr: _stadiums.STADIUMS.get(abbr, v) for abbr, v in _sd.PARKS.items()}
    return dict(games=_sd.GAMES, lineups=_sd.LINEUPS, pitchers=_sd.PITCHERS,
                parks=parks, weather=_sd.WEATHER, batters=_sd.BATTERS)
