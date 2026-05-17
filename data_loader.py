"""
Data loader — live API implementation.

Sources (all free, no auth):
  Schedule + lineups  : MLB Stats API  (statsapi.mlb.com)
  Batter SLG          : pybaseball batting_stats() → FanGraphs season totals
  Batter profile      : Baseball Savant batted-ball leaderboard CSV
                        (barrel%, FB%, pull%, oppo%)
  Pitcher HR/9        : pybaseball pitching_stats() → FanGraphs season totals
  Weather             : wttr.in JSON API (lat/lon per stadium)
  Park factors        : stadiums.py static registry

Hand-split approximation:
  True vs-LHP/vs-RHP splits require per-player API calls (too slow for a full slate).
  Instead we use season-total SLG/HR9 and apply empirical MLB platoon multipliers:
    LHH  vs RHP: ×1.08  vs LHP: ×0.87
    RHH  vs LHP: ×1.06  vs RHP: ×0.96
    SHH  both  : ×1.00
  This preserves real player differentiation (Judge .600 vs bench bat .320)
  while correctly ranking LHH vs RHP higher than LHH vs LHP.
"""

from __future__ import annotations

import datetime
import logging
import time
from io import StringIO
from typing import Any

import requests
import pandas as pd

import sample_data as _sd
import stadiums as _stadiums

log = logging.getLogger(__name__)

MLB_SCHEDULE_URL   = "https://statsapi.mlb.com/api/v1/schedule"
MLB_GAME_URL       = "https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
WTTR_URL           = "https://wttr.in/{lat},{lon}?format=j1"
SAVANT_BATBALL_URL = "https://baseballsavant.mlb.com/leaderboard/batted-ball"

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mlb-hr-screener/1.0)"}

# Platoon SLG multipliers — empirical MLB averages
_PLATOON_SLG = {
    "L": {"R": 1.08, "L": 0.87},   # LHH vs RHP gets a boost, vs LHP a penalty
    "R": {"R": 0.96, "L": 1.06},   # RHH vs LHP gets a boost, vs RHP a slight penalty
    "S": {"R": 1.00, "L": 1.00},
}

# Platoon HR/9 multipliers for pitchers
_PLATOON_HR9 = {
    "L": {"R": 1.12, "L": 0.82},   # LHP allows more HRs to RHH, fewer to LHH
    "R": {"R": 0.92, "L": 1.10},   # RHP allows more HRs to LHH, fewer to RHH
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

    batters  = _fetch_all_batter_stats()
    pitchers = _fetch_all_pitcher_stats()

    # Sample data fills named players not yet qualified in Savant/FG (callups, etc.)
    for k, v in _sd.BATTERS.items():
        batters.setdefault(k, v)
    for k, v in _sd.PITCHERS.items():
        pitchers.setdefault(k, v)

    weather = _fetch_all_weather(games)
    parks   = {abbr: _stadiums.STADIUMS[abbr]
               for abbr in park_map.values() if abbr in _stadiums.STADIUMS}

    return dict(games=games, lineups=lineups, pitchers=pitchers,
                parks=parks, weather=weather, batters=batters)


# ── Schedule + lineups ────────────────────────────────────────────────────────

def _fetch_schedule(date: str) -> list[dict]:
    params = {"sportId": 1, "date": date, "hydrate": "team,venue,probablePitcher(note)"}
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
        if g.get("status", {}).get("detailedState") in ("Postponed", "Cancelled", "Suspended"):
            continue
        gid       = str(g["gamePk"])
        away_abbr = g["teams"]["away"]["team"].get("abbreviation", "UNK")
        home_abbr = g["teams"]["home"]["team"].get("abbreviation", "UNK")
        venue     = g.get("venue", {}).get("name", "Unknown Park")
        games.append({
            "game_id":  gid,
            "away":     away_abbr,
            "home":     home_abbr,
            "park_id":  home_abbr,
            "time":     g.get("gameDate", "TBD"),
            "label":    f"{away_abbr} @ {home_abbr} — {venue}",
        })
        park_map[gid] = home_abbr
        lineups[gid]  = _fetch_lineup(gid, g, away_abbr, home_abbr)
    return games, lineups, park_map


def _fetch_lineup(game_pk: str, game_meta: dict, away_abbr: str, home_abbr: str) -> dict:
    try:
        r = requests.get(MLB_GAME_URL.format(gamePk=game_pk), timeout=10)
        r.raise_for_status()
        feed = r.json()
    except Exception as exc:
        log.warning("Live feed failed for %s: %s", game_pk, exc)
        return _probable_only_lineup(game_meta, away_abbr, home_abbr)

    players   = feed.get("gameData", {}).get("players", {})
    teams_box = feed.get("liveData", {}).get("boxscore", {}).get("teams", {})

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

        prob_side = feed.get("gameData", {}).get("probablePitchers", {}).get(side, {})
        pid_mlb   = pitchers_ids[0] if pitchers_ids else prob_side.get("id")
        pitcher_key = "unknown"
        if pid_mlb:
            pdata       = players.get(f"ID{pid_mlb}", {})
            pname       = pdata.get("fullName", str(pid_mlb))
            phand       = pdata.get("pitchHand", {}).get("code", "R")
            pitcher_key = _player_key(pname)
            _ensure_pitcher_stub(pitcher_key, pname, phand)

        result[abbr] = {"pitcher_id": pitcher_key, "batting_order": batting_order}
    return result


def _probable_only_lineup(game_meta: dict, away_abbr: str, home_abbr: str) -> dict:
    result = {}
    for side, abbr in [("away", away_abbr), ("home", home_abbr)]:
        prob  = game_meta.get("teams", {}).get(side, {}).get("probablePitcher", {})
        pname = prob.get("fullName", "TBD")
        pkey  = _player_key(pname)
        result[abbr] = {"pitcher_id": pkey, "batting_order": []}
    return result


# ── Batter stats ──────────────────────────────────────────────────────────────

def _fetch_all_batter_stats() -> dict:
    """
    Two sources merged per batter:
      1. pybaseball batting_stats() → FanGraphs: SLG, batter hand
      2. Savant batted-ball CSV → barrel%, FB%, pull%, oppo%
    """
    fg_df     = _fetch_fg_batting()
    savant_df = _fetch_savant_batted_ball()
    return _merge_batter_stats(fg_df, savant_df)


def _fetch_fg_batting() -> pd.DataFrame:
    try:
        from pybaseball import batting_stats
        df = batting_stats(datetime.date.today().year, qual=50)
        log.info("FanGraphs batting: %d rows", len(df))
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        log.warning("FanGraphs batting fetch failed: %s", exc)
        return pd.DataFrame()


def _fetch_savant_batted_ball() -> pd.DataFrame:
    """
    Savant batted-ball leaderboard — all batters, season totals (no hand filter).
    Confirmed columns: id, name, fb_rate, pull_rate, straight_rate, oppo_rate,
                       air_rate, gb_rate, ld_rate, pu_rate
    """
    params = {"csv": "true", "year": datetime.date.today().year, "min_bbe": 20}
    try:
        r = requests.get(SAVANT_BATBALL_URL, params=params, headers=_HEADERS, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant batted-ball: %d rows, cols: %s", len(df), list(df.columns)[:8])
        return df if df is not None else pd.DataFrame()
    except Exception as exc:
        log.warning("Savant batted-ball fetch failed: %s", exc)
        return pd.DataFrame()


def _merge_batter_stats(fg: pd.DataFrame, savant: pd.DataFrame) -> dict:
    """
    Build per-batter dicts. FanGraphs is the primary source for SLG and hand.
    Savant provides the batted-ball profile. Merged on normalized player name key.
    """
    # Build Savant lookup: name_key → row
    sav_lookup: dict[str, Any] = {}
    if not savant.empty:
        for _, row in savant.iterrows():
            name = str(row.get("name", "")).strip()
            if name:
                sav_lookup[_player_key(name)] = row

    out: dict[str, dict] = {}

    if not fg.empty:
        for _, row in fg.iterrows():
            try:
                name = str(row.get("Name", "")).strip()
                if not name:
                    continue
                key  = _player_key(name)
                hand = str(row.get("Bat", row.get("bat", "R"))).strip().upper()
                if hand not in ("L", "R", "S"):
                    hand = "R"

                slg  = float(row.get("SLG", 0.450) or 0.450)

                # Apply platoon multipliers to get split SLG
                plat = _PLATOON_SLG.get(hand, _PLATOON_SLG["R"])
                vs_rhp_slg = round(slg * plat["R"], 3)
                vs_lhp_slg = round(slg * plat["L"], 3)

                # Pull batted-ball profile from Savant if available
                srow = sav_lookup.get(key, {})
                barrel   = _safe_float(srow, ["brl_pa", "brl_percent", "barrel_batted_rate"], 10.5) / 100
                flyball  = _safe_float(srow, ["fb_rate"], 37.5)
                hard_hit = _safe_float(srow, ["ev95percent", "hard_hit_percent"], 41.5)
                pull     = _safe_float(srow, ["pull_rate"], 40.0)
                oppo     = _safe_float(srow, ["oppo_rate"], 24.0)

                # Savant fb_rate, pull_rate, oppo_rate are already 0–1
                # ev95percent is 0–100; normalise
                hard_hit = hard_hit / 100 if hard_hit > 1 else hard_hit
                flyball  = flyball  / 100 if flyball  > 1 else flyball
                pull     = pull     / 100 if pull     > 1 else pull
                oppo     = oppo     / 100 if oppo     > 1 else oppo

                out[key] = {
                    "player_id":     key,
                    "name":          _short_name(name),
                    "team":          str(row.get("Team", "MLB")),
                    "batter_hand":   hand,
                    "vs_RHP_slg":    vs_rhp_slg,
                    "vs_LHP_slg":    vs_lhp_slg,
                    "barrel_rate":   barrel,
                    "flyball_rate":  flyball,
                    "hard_hit_rate": hard_hit,
                    "pull_rate":     pull,
                    "oppo_rate":     oppo,
                    "hr_rate":       float(row.get("HR", 0) or 0) / max(float(row.get("PA", 1) or 1), 1),
                }
            except Exception as e:
                log.debug("Batter row error: %s", e)
                continue

    return out


# ── Pitcher stats ─────────────────────────────────────────────────────────────

def _fetch_all_pitcher_stats() -> dict:
    try:
        from pybaseball import pitching_stats
        df = pitching_stats(datetime.date.today().year, qual=10)
        log.info("FanGraphs pitching: %d rows", len(df))
        return _build_pitcher_dict(df) if df is not None else {}
    except Exception as exc:
        log.warning("FanGraphs pitching fetch failed: %s", exc)
        return {}


def _build_pitcher_dict(df: pd.DataFrame) -> dict:
    out: dict[str, dict] = {}
    if df.empty:
        return out
    for _, row in df.iterrows():
        try:
            name = str(row.get("Name", "")).strip()
            if not name:
                continue
            key  = _player_key(name)

            # FanGraphs HR9 column is "HR/9"
            hr9  = float(row.get("HR/9", 1.35) or 1.35)
            hand = str(row.get("throws", row.get("Throws", "R"))).strip().upper()
            if hand not in ("L", "R"):
                hand = "R"

            # Apply platoon multipliers: pitcher hand × batter hand
            plat = _PLATOON_HR9.get(hand, _PLATOON_HR9["R"])
            out[key] = {
                "pitcher_id":    key,
                "name":          _short_name(name),
                "hand":          hand,
                "hr_per_9":      hr9,
                "hr_per_9_vs_R": round(hr9 * plat["R"], 3),
                "hr_per_9_vs_L": round(hr9 * plat["L"], 3),
            }
        except Exception as e:
            log.debug("Pitcher row error: %s", e)
            continue
    return out


# ── Weather ───────────────────────────────────────────────────────────────────

def _fetch_all_weather(games: list[dict]) -> dict:
    weather = {}
    for game in games:
        gid       = game["game_id"]
        home_abbr = game["home"]
        park      = _stadiums.STADIUMS.get(home_abbr, {})
        lat, lon  = park.get("lat"), park.get("lon")

        if home_abbr in _stadiums.DOME_PARKS:
            weather[gid] = _dome_weather()
        elif lat is None:
            weather[gid] = _neutral_weather()
        else:
            weather[gid] = _fetch_wttr(lat, lon)
            time.sleep(0.3)
    return weather


def _fetch_wttr(lat: float, lon: float) -> dict:
    try:
        r = requests.get(WTTR_URL.format(lat=lat, lon=lon), timeout=8, headers=_HEADERS)
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(row, cols: list[str], default: float) -> float:
    if not hasattr(row, "get") and not hasattr(row, "__getitem__"):
        return default
    for c in cols:
        try:
            v = row[c] if hasattr(row, "__getitem__") else getattr(row, c, None)
            if v is not None and pd.notna(v):
                return float(v)
        except Exception:
            continue
    return default


def _player_key(name: str) -> str:
    return (name.lower()
            .replace(" ", "_").replace(".", "").replace("'", "")
            .replace("-", "_").replace(",", "").replace("  ", "_"))


def _short_name(full: str) -> str:
    parts = full.strip().split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else full


# ── Stub registries ───────────────────────────────────────────────────────────

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
        gid    = game["game_id"]
        park   = data["parks"].get(game["park_id"])
        if park is None:
            log.warning("No park for %s, skipping %s", game["park_id"], gid)
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
