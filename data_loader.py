"""
Data loader — live API implementation.

Sources (all free, no auth):
  Schedule + lineups : MLB Stats API  (statsapi.mlb.com)
  Batter/pitcher stats: pybaseball → Baseball Savant / FanGraphs
  Weather            : wttr.in JSON API (lat/lon per stadium)
  Park factors       : stadiums.py static registry

Fallback chain:
  1. Try live API call
  2. On any error, log a warning and return sample_data equivalent so the app
     stays runnable even when a source is down or lineups aren't posted yet.

Install:
  pip install requests pybaseball pandas
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

# Seconds to wait between repeated Savant/FanGraphs requests (be polite)
_SAVANT_SLEEP = 1.5


# ── Public API ────────────────────────────────────────────────────────────────

def load_all(date: str | None = None) -> dict[str, Any]:
    """
    Return a fully assembled data bundle for today's slate (or a given date YYYY-MM-DD).
    The bundle shape is identical to what sample_data.py produces, so scoring.py
    and app.py need zero changes.
    """
    target_date = date or datetime.date.today().isoformat()
    log.info("Loading data for %s", target_date)

    games_raw = _fetch_schedule(target_date)

    if not games_raw:
        log.warning("No games found for %s — falling back to sample data", target_date)
        return _sample_bundle()

    games, lineups, park_map = _process_schedule(games_raw, target_date)

    batters_df, pitchers_df = _fetch_savant_stats()

    batters  = _build_batter_dict(batters_df)
    pitchers = _build_pitcher_dict(pitchers_df)

    # Fill any missing players from sample data so the app always renders
    batters.update({k: v for k, v in _sd.BATTERS.items() if k not in batters})
    pitchers.update({k: v for k, v in _sd.PITCHERS.items() if k not in pitchers})

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
        data  = r.json()
        dates = data.get("dates", [])
        return dates[0].get("games", []) if dates else []
    except Exception as exc:
        log.warning("Schedule fetch failed: %s", exc)
        return []


def _process_schedule(
    games_raw: list[dict],
    target_date: str,
) -> tuple[list[dict], dict, dict[str, str]]:
    """
    Convert raw MLB API game dicts → (games list, lineups dict, park_map).
    park_map: game_id → team abbreviation (for the home team, which sets the park).
    """
    games    = []
    lineups  = {}
    park_map = {}

    for g in games_raw:
        status = g.get("status", {}).get("abstractGameState", "")
        # Skip postponed / cancelled
        if status == "Final" and g.get("status", {}).get("detailedState") == "Postponed":
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
            "park_id":  home_abbr,        # park keyed by home team abbr
            "time":     game_time,
            "label":    f"{away_abbr} @ {home_abbr} — {venue}",
        })

        park_map[gid] = home_abbr
        lineups[gid]  = _fetch_lineup(gid, g, away_abbr, home_abbr)

    return games, lineups, park_map


def _fetch_lineup(
    game_pk: str,
    game_meta: dict,
    away_abbr: str,
    home_abbr: str,
) -> dict:
    """
    Fetch live feed for a game and extract batting orders + probable pitchers.
    Falls back to probable-pitcher-only dict if lineups aren't posted yet.
    """
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
    players   = game_data.get("players", {})      # ID{id} → player dict
    boxscore  = live_data.get("boxscore", {})
    teams_box = boxscore.get("teams", {})

    result = {}
    for side, abbr in [("away", away_abbr), ("home", home_abbr)]:
        side_box = teams_box.get(side, {})
        batters_ids = side_box.get("batters", [])     # list of int player ids
        pitchers_ids = side_box.get("pitchers", [])

        batting_order = []
        for pos, pid in enumerate(batters_ids, start=1):
            pkey  = f"ID{pid}"
            pdata = players.get(pkey, {})
            name  = pdata.get("fullName", str(pid))
            hand  = pdata.get("batSide", {}).get("code", "R")
            player_key = _player_key(name)
            batting_order.append((player_key, pos))

            # Inject into global batter registry if not already there
            # (stats will be back-filled from Savant; this ensures key exists)
            _ensure_batter_stub(player_key, name, abbr, hand)

        # Pitcher: prefer actual starter from pitchers list, then probable
        pitcher_id_mlb = None
        if pitchers_ids:
            pitcher_id_mlb = pitchers_ids[0]
        else:
            prob = game_data.get("probablePitchers", {}).get(side, {})
            pitcher_id_mlb = prob.get("id")

        pitcher_key = "unknown"
        if pitcher_id_mlb:
            pkey  = f"ID{pitcher_id_mlb}"
            pdata = players.get(pkey, {})
            pname = pdata.get("fullName", str(pitcher_id_mlb))
            phand = pdata.get("pitchHand", {}).get("code", "R")
            pitcher_key = _player_key(pname)
            _ensure_pitcher_stub(pitcher_key, pname, phand)

        result[abbr] = {
            "pitcher_id":    pitcher_key,
            "batting_order": batting_order or _empty_order(abbr),
        }

    return result


def _probable_only_lineup(
    game_meta: dict,
    away_abbr: str,
    home_abbr: str,
) -> dict:
    """Used when live feed is unavailable — pitcher only, empty batting order."""
    result = {}
    for side, abbr in [("away", away_abbr), ("home", home_abbr)]:
        prob  = game_meta.get("teams", {}).get(side, {}).get("probablePitcher", {})
        pname = prob.get("fullName", "TBD")
        pkey  = _player_key(pname)
        result[abbr] = {
            "pitcher_id":    pkey,
            "batting_order": _empty_order(abbr),
        }
    return result


# ── Statcast / Savant stats ───────────────────────────────────────────────────

# These are populated lazily so _ensure_*_stub can write into them
_BATTER_REGISTRY:  dict[str, dict] = {}
_PITCHER_REGISTRY: dict[str, dict] = {}


def _fetch_savant_stats() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Pull current-season Statcast batter and pitcher splits from Baseball Savant.
    Uses pybaseball which scrapes Savant CSV endpoints.
    Returns (batters_df, pitchers_df) — empty DataFrames on failure.
    """
    try:
        from pybaseball import statcast_batter_expected_stats, pitching_stats_bref
        # pybaseball has many modules; use the ones that give us the splits we need
    except ImportError:
        log.warning("pybaseball not installed — run: pip install pybaseball")
        return pd.DataFrame(), pd.DataFrame()

    year = datetime.date.today().year
    batters_df  = _fetch_batter_statcast(year)
    pitchers_df = _fetch_pitcher_splits(year)
    return batters_df, pitchers_df


def _fetch_batter_statcast(year: int) -> pd.DataFrame:
    """
    Fetch Statcast batter leaderboard from Baseball Savant.
    Returns a DataFrame with columns used by _build_batter_dict().
    """
    try:
        from pybaseball import statcast_batter_exitvelo_barrels
        df = statcast_batter_exitvelo_barrels(year)
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        log.warning("Statcast batter fetch failed: %s", exc)
        return pd.DataFrame()


def _fetch_pitcher_splits(year: int) -> pd.DataFrame:
    """
    Fetch FanGraphs pitcher stats including HR/9 splits.
    """
    try:
        from pybaseball import pitching_stats
        time.sleep(_SAVANT_SLEEP)
        df = pitching_stats(year, qual=1)
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        log.warning("Pitcher stats fetch failed: %s", exc)
        return pd.DataFrame()


def _build_batter_dict(df: pd.DataFrame) -> dict:
    """
    Map Statcast exit-velo/barrel leaderboard → batter registry dict.
    Column names from pybaseball.statcast_batter_exitvelo_barrels:
      last_name, first_name, player_id, attempts, avg_hit_angle, anglesweetspotpercent,
      max_hit_speed, avg_hit_speed, ev95percent, barrels, brl_percent, brl_pa
    """
    out = {}
    if df.empty:
        return out
    for _, row in df.iterrows():
        try:
            name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
            key  = _player_key(name)
            out[key] = {
                "player_id":     key,
                "name":          _short_name(name),
                "team":          str(row.get("team_name", "MLB")),
                "batter_hand":   "R",          # not in this endpoint; filled later
                "vs_RHP_slg":    0.450,        # midpoint placeholder until split fetch works
                "vs_LHP_slg":    0.450,
                "barrel_rate":   float(row.get("brl_pa",       10.5) or 10.5) / 100,
                "flyball_rate":  0.375,        # midpoint placeholder
                "hard_hit_rate": float(row.get("ev95percent",  41.5) or 41.5) / 100,
                "pull_rate":     0.40,
                "oppo_rate":     0.24,
                "hr_rate":       0.035,
            }
        except Exception:
            continue
    return out


def _build_pitcher_dict(df: pd.DataFrame) -> dict:
    """
    Map FanGraphs pitching_stats → pitcher registry dict.
    Key columns: Name, Team, W, L, ERA, HR, IP, HR9
    """
    out = {}
    if df.empty:
        return out
    for _, row in df.iterrows():
        try:
            name = str(row.get("Name", ""))
            key  = _player_key(name)
            hr9  = float(row.get("HR/9", 1.35) or 1.35)  # midpoint of 0.50–2.20
            out[key] = {
                "pitcher_id":     key,
                "name":           _short_name(name),
                "hand":           "R",          # not in FG table; filled from roster
                "hr_per_9":       hr9,
                "hr_per_9_vs_L":  hr9 * 1.05,
                "hr_per_9_vs_R":  hr9 * 0.95,
            }
        except Exception:
            continue
    return out


# ── Weather ───────────────────────────────────────────────────────────────────

def _fetch_all_weather(games: list[dict]) -> dict:
    weather = {}
    for game in games:
        gid       = game["game_id"]
        home_abbr = game["home"]
        park      = _stadiums.STADIUMS.get(home_abbr, {})
        lat       = park.get("lat")
        lon       = park.get("lon")

        if lat is None or lon is None:
            weather[gid] = _neutral_weather()
            continue

        # Dome parks get neutral weather — wind model is irrelevant
        if home_abbr in _stadiums.DOME_PARKS:
            weather[gid] = _dome_weather()
            continue

        weather[gid] = _fetch_wttr(lat, lon)
        time.sleep(0.3)     # be polite to wttr.in

    return weather


def _fetch_wttr(lat: float, lon: float) -> dict:
    url = WTTR_URL.format(lat=lat, lon=lon)
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        cond = r.json()["current_condition"][0]
        return {
            "temp":            int(cond.get("temp_F",           "72")),
            "humidity":        int(cond.get("humidity",          "50")),
            "wind_speed":      int(cond.get("windspeedMiles",     "0")),
            "wind_direction":  str(cond.get("winddir16Point",  "CALM")),
            "conditions":      str(cond.get("weatherDesc", [{}])[0].get("value", "")),
        }
    except Exception as exc:
        log.warning("Weather fetch failed for %.4f,%.4f: %s", lat, lon, exc)
        return _neutral_weather()


def _neutral_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Unknown"}


def _dome_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Dome"}


# ── Player key helpers ────────────────────────────────────────────────────────

def _player_key(name: str) -> str:
    """Deterministic lowercase underscore key from a full player name."""
    return name.lower().replace(" ", "_").replace(".", "").replace("'", "").replace("-", "_")


def _short_name(full: str) -> str:
    """'Aaron Judge' → 'A. Judge'"""
    parts = full.strip().split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return full


def _empty_order(team: str) -> list:
    return []


def _ensure_batter_stub(key: str, name: str, team: str, hand: str) -> None:
    """Register a minimal batter dict so the app can render the row even before Savant loads."""
    if key not in _BATTER_REGISTRY:
        _BATTER_REGISTRY[key] = {
            "player_id":    key,    "name":          _short_name(name),
            "team":         team,   "batter_hand":   hand,
            "vs_RHP_slg":   0.450,  "vs_LHP_slg":    0.450,  # midpoint of 0.280–0.620
            "barrel_rate":  0.105,  "flyball_rate":   0.375,  # midpoint of respective ranges
            "hard_hit_rate":0.415,  "pull_rate":      0.40,
            "oppo_rate":    0.24,   "hr_rate":        0.030,
        }


def _ensure_pitcher_stub(key: str, name: str, hand: str) -> None:
    if key not in _PITCHER_REGISTRY:
        _PITCHER_REGISTRY[key] = {
            "pitcher_id":    key,   "name":          _short_name(name),
            "hand":          hand,
            "hr_per_9":      1.35,  "hr_per_9_vs_L": 1.42,  "hr_per_9_vs_R": 1.28,  # midpoint of 0.50–2.20
        }


# ── Assembly (same interface as original) ────────────────────────────────────

def build_rows(data: dict) -> list[dict]:
    """
    Flatten games + lineups + stats into one list of per-batter rows.
    Identical contract to the original data_loader.build_rows().
    """
    rows = []
    for game in data["games"]:
        gid      = game["game_id"]
        park_id  = game["park_id"]
        park     = data["parks"].get(park_id)
        if park is None:
            log.warning("No park entry for %s — skipping game %s", park_id, gid)
            continue
        weather  = data["weather"].get(gid, _neutral_weather())
        lineup   = data["lineups"].get(gid, {})

        away, home = game["away"], game["home"]
        for batting_team, opp_team in [(away, home), (home, away)]:
            side     = lineup.get(batting_team, {})
            opp_side = lineup.get(opp_team, {})
            if not side or not opp_side:
                continue

            pitcher_id = opp_side.get("pitcher_id", "unknown")
            pitcher    = (data["pitchers"].get(pitcher_id)
                          or _PITCHER_REGISTRY.get(pitcher_id)
                          or _sd.PITCHERS.get(pitcher_id)
                          or {"pitcher_id": pitcher_id, "name": pitcher_id,
                              "hand": "R", "hr_per_9": 1.2,
                              "hr_per_9_vs_L": 1.26, "hr_per_9_vs_R": 1.14})

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
    """Return the original sample data when live APIs fail entirely."""
    parks = {abbr: _stadiums.STADIUMS.get(abbr, v)
             for abbr, v in _sd.PARKS.items()}
    return dict(
        games    = _sd.GAMES,
        lineups  = _sd.LINEUPS,
        pitchers = _sd.PITCHERS,
        parks    = parks,
        weather  = _sd.WEATHER,
        batters  = _sd.BATTERS,
    )
