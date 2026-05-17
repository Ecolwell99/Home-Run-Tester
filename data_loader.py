"""
Data loader — requests only, no pybaseball dependency.

All four stat sources are free public endpoints:

  Batter SLG         : Savant expected_statistics CSV
                       columns: "last_name, first_name", slg
                       name format: "Judge, Aaron"

  Batter profile     : Savant statcast_leaderboard CSV
                       columns: "last_name first_name", brl_pa, ev95percent
                       name format: "Judge Aaron"

  Batter spray       : Savant batted-ball leaderboard CSV
                       columns: name, fb_rate, pull_rate, oppo_rate
                       name format: "Judge Aaron"

  Pitcher HR/9       : MLB Stats API /stats?group=pitching&hydrate=person
                       returns homeRuns, inningsPitched, pitchHand per pitcher

  Batter hand        : MLB Stats API /sports/1/players (all rostered players)
                       returns batSide per player — merged by player_id

  Schedule/lineups   : MLB Stats API (unchanged)
  Weather            : wttr.in (unchanged)
  Park factors       : stadiums.py (unchanged)

Platoon multipliers applied to overall SLG/HR9 to estimate hand splits:
  LHH vs RHP: ×1.08  LHH vs LHP: ×0.87
  RHH vs LHP: ×1.06  RHH vs RHP: ×0.96
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

MLB_SCHEDULE_URL  = "https://statsapi.mlb.com/api/v1/schedule"
MLB_GAME_URL      = "https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
MLB_PLAYERS_URL   = "https://statsapi.mlb.com/api/v1/sports/1/players"
MLB_PITCH_STATS   = "https://statsapi.mlb.com/api/v1/stats"
WTTR_URL          = "https://wttr.in/{lat},{lon}?format=j1"

SAVANT_EXPECTED   = "https://baseballsavant.mlb.com/expected_statistics"
SAVANT_EV         = "https://baseballsavant.mlb.com/statcast_leaderboard"
SAVANT_BATBALL    = "https://baseballsavant.mlb.com/leaderboard/batted-ball"

_HDR = {"User-Agent": "Mozilla/5.0 (compatible; mlb-hr-screener/1.0)"}

_PLATOON_SLG = {
    "L": {"R": 1.08, "L": 0.87},
    "R": {"R": 0.96, "L": 1.06},
    "S": {"R": 1.00, "L": 1.00},
}
_PLATOON_HR9 = {
    "L": {"R": 1.12, "L": 0.82},
    "R": {"R": 0.92, "L": 1.10},
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

    year = datetime.date.today().year

    # Fetch all stat sources in sequence
    slg_map      = _fetch_savant_expected_slg(year)      # key → slg float
    ev_map       = _fetch_savant_ev_barrels(year)         # key → {barrel, hard_hit}
    spray_map    = _fetch_savant_batted_ball(year)        # key → {fb, pull, oppo}
    hand_map     = _fetch_player_hands(year)              # key → "L"/"R"/"S"
    pitcher_map  = _fetch_pitcher_stats(year)             # key → pitcher dict

    batters  = _build_batters(slg_map, ev_map, spray_map, hand_map)
    pitchers = pitcher_map

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
        r = requests.get(MLB_SCHEDULE_URL, params=params, timeout=10, headers=_HDR)
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
        r = requests.get(MLB_GAME_URL.format(gamePk=game_pk), timeout=10, headers=_HDR)
        r.raise_for_status()
        feed = r.json()
    except Exception as exc:
        log.warning("Live feed failed %s: %s", game_pk, exc)
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

        prob = feed.get("gameData", {}).get("probablePitchers", {}).get(side, {})
        pid_mlb = pitchers_ids[0] if pitchers_ids else prob.get("id")
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
        pkey  = _player_key(prob.get("fullName", "TBD"))
        result[abbr] = {"pitcher_id": pkey, "batting_order": []}
    return result


# ── Savant: SLG ──────────────────────────────────────────────────────────────

def _fetch_savant_expected_slg(year: int) -> dict[str, float]:
    """
    Returns {player_key: slg} for all qualified batters.
    Name format in CSV: "Judge, Aaron" → key: "aaron_judge"
    """
    params = {"type": "batter", "year": year, "position": "", "team": "", "min": 25, "csv": "true"}
    try:
        r = requests.get(SAVANT_EXPECTED, params=params, headers=_HDR, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant expected stats: %d rows, cols: %s", len(df), list(df.columns))
    except Exception as exc:
        log.warning("Savant expected stats failed: %s", exc)
        return {}

    out = {}
    name_col = _find_col(df, ["last_name, first_name", "player_name", "name"])
    slg_col  = _find_col(df, ["slg", "SLG", "slg_percent"])
    if not name_col or not slg_col:
        log.warning("Savant expected stats: missing name or SLG column. Cols: %s", list(df.columns))
        return {}

    for _, row in df.iterrows():
        try:
            name = str(row[name_col]).strip()
            slg  = float(row[slg_col])
            key  = _player_key(_last_first_to_first_last(name))
            out[key] = slg
        except Exception:
            continue
    log.info("SLG map: %d players", len(out))
    return out


# ── Savant: barrel rate + hard-hit rate ──────────────────────────────────────

def _fetch_savant_ev_barrels(year: int) -> dict[str, dict]:
    """
    Returns {player_key: {barrel_rate, hard_hit_rate}}.
    Name format: "Judge Aaron" (last first, space separated, single column)
    """
    params = {"csv": "true", "type": "batter", "year": year, "min_pa": 25}
    try:
        r = requests.get(SAVANT_EV, params=params, headers=_HDR, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant EV/barrels: %d rows", len(df))
    except Exception as exc:
        log.warning("Savant EV fetch failed: %s", exc)
        return {}

    out = {}
    # Name column may be "last_name first_name" (combined) or separate columns
    name_col    = _find_col(df, ["last_name first_name", "player_name", "name"])
    barrel_col  = _find_col(df, ["brl_pa", "brl_percent", "barrel_batted_rate"])
    hh_col      = _find_col(df, ["ev95percent", "hard_hit_percent", "ev95plus"])

    if not name_col:
        # Try constructing from separate last/first columns
        if "last_name" in df.columns and "first_name" in df.columns:
            df["_name"] = df["first_name"].astype(str) + " " + df["last_name"].astype(str)
            name_col = "_name"
        else:
            log.warning("Savant EV: no name column found. Cols: %s", list(df.columns))
            return {}

    for _, row in df.iterrows():
        try:
            raw_name = str(row[name_col]).strip()
            # Format is "Last First" → need "First Last" for key
            key = _player_key(_last_first_to_first_last(raw_name))

            barrel   = float(row[barrel_col]) / 100 if barrel_col else 0.105
            hard_hit = float(row[hh_col])     / 100 if hh_col     else 0.415

            out[key] = {"barrel_rate": barrel, "hard_hit_rate": hard_hit}
        except Exception:
            continue
    log.info("EV map: %d players", len(out))
    return out


# ── Savant: batted-ball spray ─────────────────────────────────────────────────

def _fetch_savant_batted_ball(year: int) -> dict[str, dict]:
    """
    Returns {player_key: {flyball_rate, pull_rate, oppo_rate}}.
    Confirmed working endpoint. Columns: id, name, fb_rate, pull_rate, oppo_rate.
    Name format: "Judge Aaron" (last first)
    """
    params = {"csv": "true", "year": year, "min_bbe": 20}
    try:
        r = requests.get(SAVANT_BATBALL, params=params, headers=_HDR, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        log.info("Savant batted-ball: %d rows", len(df))
    except Exception as exc:
        log.warning("Savant batted-ball failed: %s", exc)
        return {}

    out = {}
    for _, row in df.iterrows():
        try:
            raw_name = str(row.get("name", "")).strip()
            if not raw_name:
                continue
            key = _player_key(_last_first_to_first_last(raw_name))
            out[key] = {
                "flyball_rate": float(row.get("fb_rate",    0.375)),
                "pull_rate":    float(row.get("pull_rate",  0.400)),
                "oppo_rate":    float(row.get("oppo_rate",  0.240)),
            }
        except Exception:
            continue
    log.info("Spray map: %d players", len(out))
    return out


# ── MLB Stats API: batter handedness ─────────────────────────────────────────

def _fetch_player_hands(year: int) -> dict[str, str]:
    """
    Returns {player_key: "L"/"R"/"S"} for all rostered players.
    Uses MLB /sports/1/players which returns batSide for everyone.
    """
    try:
        r = requests.get(
            MLB_PLAYERS_URL,
            params={"season": year, "gameType": "R"},
            headers=_HDR, timeout=15,
        )
        r.raise_for_status()
        players = r.json().get("people", [])
        log.info("MLB players: %d", len(players))
    except Exception as exc:
        log.warning("MLB players fetch failed: %s", exc)
        return {}

    out = {}
    for p in players:
        name = p.get("fullName", "")
        hand = p.get("batSide", {}).get("code", "R")
        if name:
            out[_player_key(name)] = hand
    return out


# ── MLB Stats API: pitcher season stats ──────────────────────────────────────

def _fetch_pitcher_stats(year: int) -> dict[str, dict]:
    """
    Returns pitcher dicts with HR/9 and split estimates.
    Uses MLB Stats API /stats with hydrate=person to get pitchHand.
    Paginates to get all pitchers (limit 500 per call).
    """
    out: dict[str, dict] = {}
    offset = 0
    limit  = 500

    while True:
        params = {
            "stats":      "season",
            "group":      "pitching",
            "season":     year,
            "playerPool": "ALL",
            "limit":      limit,
            "offset":     offset,
            "hydrate":    "person",
        }
        try:
            r = requests.get(MLB_PITCH_STATS, params=params, headers=_HDR, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            log.warning("MLB pitcher stats fetch failed: %s", exc)
            break

        splits = data.get("stats", [{}])[0].get("splits", [])
        if not splits:
            break

        for s in splits:
            try:
                person = s.get("person", {})
                name   = person.get("fullName", "")
                if not name:
                    continue
                key   = _player_key(name)
                stat  = s.get("stat", {})
                hr    = int(stat.get("homeRuns", 0) or 0)
                ip    = _ip_to_float(stat.get("inningsPitched", "1"))
                hr9   = round((hr / max(ip, 0.33)) * 9, 3)
                hand  = person.get("pitchHand", {}).get("code", "R")
                plat  = _PLATOON_HR9.get(hand, _PLATOON_HR9["R"])

                # Only update if this entry has more innings (keep the most pitched)
                if key not in out or ip > out[key].get("_ip", 0):
                    out[key] = {
                        "pitcher_id":    key,
                        "name":          _short_name(name),
                        "hand":          hand,
                        "hr_per_9":      hr9,
                        "hr_per_9_vs_R": round(hr9 * plat["R"], 3),
                        "hr_per_9_vs_L": round(hr9 * plat["L"], 3),
                        "_ip":           ip,
                    }
            except Exception:
                continue

        if len(splits) < limit:
            break
        offset += limit
        time.sleep(0.3)

    log.info("Pitcher map: %d pitchers", len(out))
    return out


# ── Merge batter stats ────────────────────────────────────────────────────────

def _build_batters(
    slg_map:   dict[str, float],
    ev_map:    dict[str, dict],
    spray_map: dict[str, dict],
    hand_map:  dict[str, str],
) -> dict[str, dict]:
    """
    Union all keys across all four maps.
    Any missing value falls back to the range midpoint.
    """
    all_keys = set(slg_map) | set(ev_map) | set(spray_map)
    out: dict[str, dict] = {}

    for key in all_keys:
        slg    = slg_map.get(key, 0.450)
        ev     = ev_map.get(key, {})
        spray  = spray_map.get(key, {})
        hand   = hand_map.get(key, "R")
        plat   = _PLATOON_SLG.get(hand, _PLATOON_SLG["R"])

        # Short display name: best effort from key
        parts = key.split("_")
        name  = _short_name(" ".join(p.capitalize() for p in parts))

        out[key] = {
            "player_id":     key,
            "name":          name,
            "team":          "MLB",
            "batter_hand":   hand,
            "vs_RHP_slg":    round(slg * plat["R"], 3),
            "vs_LHP_slg":    round(slg * plat["L"], 3),
            "barrel_rate":   ev.get("barrel_rate",   0.105),
            "hard_hit_rate": ev.get("hard_hit_rate",  0.415),
            "flyball_rate":  spray.get("flyball_rate", 0.375),
            "pull_rate":     spray.get("pull_rate",    0.400),
            "oppo_rate":     spray.get("oppo_rate",    0.240),
            "hr_rate":       0.035,
        }

    # Patch hands and names into stubs already registered from lineup fetch
    for key, hand in hand_map.items():
        if key in _BATTER_REGISTRY:
            _BATTER_REGISTRY[key]["batter_hand"] = hand

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
        r = requests.get(WTTR_URL.format(lat=lat, lon=lon), timeout=8, headers=_HDR)
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
        log.warning("Weather fetch %.4f,%.4f: %s", lat, lon, exc)
        return _neutral_weather()


def _neutral_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Unknown"}


def _dome_weather() -> dict:
    return {"temp": 72, "humidity": 50, "wind_speed": 0,
            "wind_direction": "CALM", "conditions": "Dome"}


# ── Name format helpers ───────────────────────────────────────────────────────

def _last_first_to_first_last(name: str) -> str:
    """
    Handles two formats:
      "Judge, Aaron"  → "Aaron Judge"   (comma-separated)
      "Judge Aaron"   → "Aaron Judge"   (space-separated, last name first)
    """
    name = name.strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        return f"{parts[1]} {parts[0]}"
    # Space-separated "Last First" — assume last name is one word
    parts = name.split()
    if len(parts) >= 2:
        return " ".join(parts[1:]) + " " + parts[0]
    return name


def _player_key(name: str) -> str:
    return (name.lower()
            .replace(" ", "_").replace(".", "").replace("'", "")
            .replace("-", "_").replace(",", "").strip("_"))


def _short_name(full: str) -> str:
    parts = full.strip().split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else full


def _ip_to_float(ip) -> float:
    try:
        s = str(ip).strip()
        if "." in s:
            whole, frac = s.split(".", 1)
            return float(whole) + float(frac) / 3
        return float(s)
    except Exception:
        return 1.0


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


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


# ── Debug helpers (used by app.py Debug view) ─────────────────────────────────

def _fetch_fg_batting() -> pd.DataFrame:
    """Stub kept for debug view compatibility — replaced by Savant expected stats."""
    return _fetch_savant_expected_slg_df(datetime.date.today().year)


def _fetch_savant_expected_slg_df(year: int) -> pd.DataFrame:
    params = {"type": "batter", "year": year, "position": "", "team": "", "min": 25, "csv": "true"}
    try:
        r = requests.get(SAVANT_EXPECTED, params=params, headers=_HDR, timeout=20)
        r.raise_for_status()
        return pd.read_csv(StringIO(r.text))
    except Exception as exc:
        log.warning("Savant expected stats df failed: %s", exc)
        return pd.DataFrame()


def _fetch_savant_batted_ball_df() -> pd.DataFrame:
    return _fetch_savant_batted_ball_raw(datetime.date.today().year)


def _fetch_savant_batted_ball_raw(year: int) -> pd.DataFrame:
    params = {"csv": "true", "year": year, "min_bbe": 20}
    try:
        r = requests.get(SAVANT_BATBALL, params=params, headers=_HDR, timeout=20)
        r.raise_for_status()
        return pd.read_csv(StringIO(r.text))
    except Exception as exc:
        log.warning("Savant batted-ball raw failed: %s", exc)
        return pd.DataFrame()


# ── Sample data fallback ──────────────────────────────────────────────────────

def _sample_bundle() -> dict[str, Any]:
    parks = {abbr: _stadiums.STADIUMS.get(abbr, v) for abbr, v in _sd.PARKS.items()}
    return dict(games=_sd.GAMES, lineups=_sd.LINEUPS, pitchers=_sd.PITCHERS,
                parks=parks, weather=_sd.WEATHER, batters=_sd.BATTERS)
