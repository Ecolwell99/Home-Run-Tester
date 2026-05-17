"""
Data loader — single interface between the app and data sources.

Currently uses sample_data.py (mock).
To swap in real APIs, replace the _load_* functions below while keeping
the return shapes identical.  The scoring engine and app depend only on
the structures returned here, not on any specific data source.

API integration touch-points:
  _load_games()    → MLB Stats API  (schedule endpoint)
  _load_lineups()  → MLB Stats API  (lineups endpoint)
  _load_pitchers() → Baseball Savant / FanGraphs API
  _load_parks()    → Baseball Savant park factors  (static + seasonal)
  _load_weather()  → OpenWeatherMap API (lat/lon of each stadium)
"""

from __future__ import annotations
from typing import Any
import sample_data as _sd


# ---------------------------------------------------------------------------
# Public API — these are the only functions the app calls
# ---------------------------------------------------------------------------

def load_all() -> dict[str, Any]:
    """Return a fully assembled data bundle for today's slate."""
    games    = _load_games()
    lineups  = _load_lineups()
    pitchers = _load_pitchers()
    parks    = _load_parks()
    weather  = _load_weather()
    batters  = _load_batters()
    return dict(games=games, lineups=lineups, pitchers=pitchers,
                parks=parks, weather=weather, batters=batters)


# ---------------------------------------------------------------------------
# Internal loaders — swap each one for a real API call independently
# ---------------------------------------------------------------------------

def _load_games() -> list[dict]:
    """
    TODO: replace with MLB Stats API
      GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD
    Expected shape: list of dicts matching sample_data.GAMES
    """
    return _sd.GAMES


def _load_lineups() -> dict:
    """
    TODO: replace with MLB Stats API
      GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live
      Pull lineups once they are posted (usually ~60 min before first pitch).
    Expected shape: dict matching sample_data.LINEUPS
    """
    return _sd.LINEUPS


def _load_pitchers() -> dict:
    """
    TODO: replace with Baseball Savant or FanGraphs pitcher splits.
    Key stat needed: hr_per_9_vs_L and hr_per_9_vs_R (current season + prev).
    Expected shape: dict matching sample_data.PITCHERS
    """
    return _sd.PITCHERS


def _load_parks() -> dict:
    """
    TODO: replace with park factor data.
    Sources:
      - Baseball Savant park factors (HR-specific, by batter hand, 5-yr rolling)
      - Compass bearings of fields can be fetched from stadium coordinate data
        or maintained as a static lookup table (changes rarely).
    Expected shape: dict matching sample_data.PARKS
    """
    return _sd.PARKS


def _load_weather() -> dict:
    """
    TODO: replace with OpenWeatherMap or WeatherAPI.
      Use the lat/lon of each stadium to pull current + forecast conditions.
      Wind direction should be the compass bearing the wind is blowing FROM.
    Expected shape: dict matching sample_data.WEATHER
    """
    return _sd.WEATHER


def _load_batters() -> dict:
    """
    TODO: replace with Baseball Savant Statcast / FanGraphs batter splits.
    Key stats per batter:
      vs_RHP_slg, vs_LHP_slg   — SLG by pitcher hand (rolling season)
      barrel_rate               — Statcast barrels / PA
      flyball_rate              — batted ball type
      hard_hit_rate             — exit velo >= 95 mph
      pull_rate, oppo_rate      — spray direction tendencies
    Expected shape: dict matching sample_data.BATTERS
    """
    return _sd.BATTERS


# ---------------------------------------------------------------------------
# Assembly helpers used by app.py
# ---------------------------------------------------------------------------

def build_rows(data: dict) -> list[dict]:
    """
    Flatten games + lineups + stats into one list of per-batter rows.
    Each row has everything scoring.compute_hr_score() needs.
    """
    rows = []
    for game in data["games"]:
        gid      = game["game_id"]
        park     = data["parks"][game["park_id"]]
        weather  = data["weather"][gid]
        lineup   = data["lineups"][gid]

        for batting_team, opp_team in [
            (game["away"], game["home"]),
            (game["home"], game["away"]),
        ]:
            side       = lineup[batting_team]
            opp_side   = lineup[opp_team]
            pitcher_id = opp_side["pitcher_id"]
            pitcher    = data["pitchers"][pitcher_id]

            for player_id, order in side["batting_order"]:
                batter = data["batters"].get(player_id)
                if batter is None:
                    continue
                rows.append({
                    "batter":       batter,
                    "pitcher":      pitcher,
                    "park":         park,
                    "weather":      weather,
                    "pitcher_hand": pitcher["hand"],
                    "game_id":      gid,
                    "game_label":   game["label"],
                    "batting_team": batting_team,
                    "opp_team":     opp_team,
                    "batting_order":order,
                })
    return rows

