"""
Sample data representing a slate of MLB games.
Replace this module with real API calls in data_loader.py.

Structure mirrors what data_loader.py will return:
  games       : list[dict]  — game metadata
  lineups     : dict        — keyed by game_id, each side has 'batting_order' list
  pitchers    : dict        — keyed by pitcher_id
  parks       : dict        — keyed by park_id
  weather     : dict        — keyed by game_id
"""

PARKS = {
    "coors":    {
        "park_id": "coors",    "name": "Coors Field",
        "hr_factor": 1.38,     "hr_factor_L": 1.40, "hr_factor_R": 1.36,
        "lf_bearing": 255,     "cf_bearing": 225,   "rf_bearing": 195,
        # Bearings measured from home plate looking toward outfield (degrees from North)
    },
    "fenway":   {
        "park_id": "fenway",   "name": "Fenway Park",
        "hr_factor": 0.92,     "hr_factor_L": 0.80, "hr_factor_R": 1.05,
        "lf_bearing": 270,     "cf_bearing": 315,   "rf_bearing": 30,
    },
    "gabp":     {
        "park_id": "gabp",     "name": "Great American Ball Park",
        "hr_factor": 1.20,     "hr_factor_L": 1.22, "hr_factor_R": 1.18,
        "lf_bearing": 260,     "cf_bearing": 310,   "rf_bearing": 40,
    },
    "yankee":   {
        "park_id": "yankee",   "name": "Yankee Stadium",
        "hr_factor": 1.15,     "hr_factor_L": 1.28, "hr_factor_R": 1.05,
        "lf_bearing": 250,     "cf_bearing": 305,   "rf_bearing": 45,
    },
    "oracle":   {
        "park_id": "oracle",   "name": "Oracle Park",
        "hr_factor": 0.82,     "hr_factor_L": 0.80, "hr_factor_R": 0.84,
        "lf_bearing": 240,     "cf_bearing": 295,   "rf_bearing": 350,
    },
    "petco":    {
        "park_id": "petco",    "name": "Petco Park",
        "hr_factor": 0.88,     "hr_factor_L": 0.90, "hr_factor_R": 0.86,
        "lf_bearing": 245,     "cf_bearing": 300,   "rf_bearing": 355,
    },
    "minaj":    {
        "park_id": "minaj",    "name": "Minute Maid Park",
        "hr_factor": 1.12,     "hr_factor_L": 1.18, "hr_factor_R": 1.08,
        "lf_bearing": 255,     "cf_bearing": 315,   "rf_bearing": 50,
    },
}

PITCHERS = {
    "p_burnes":   {"pitcher_id": "p_burnes",   "name": "C. Burnes",    "hand": "R",
                   "hr_per_9": 0.72, "hr_per_9_vs_L": 0.65, "hr_per_9_vs_R": 0.78},
    "p_verlander":{"pitcher_id": "p_verlander","name": "J. Verlander", "hand": "R",
                   "hr_per_9": 1.05, "hr_per_9_vs_L": 1.18, "hr_per_9_vs_R": 0.95},
    "p_snell":    {"pitcher_id": "p_snell",    "name": "B. Snell",     "hand": "L",
                   "hr_per_9": 1.35, "hr_per_9_vs_L": 0.85, "hr_per_9_vs_R": 1.72},
    "p_alcantara":{"pitcher_id": "p_alcantara","name": "S. Alcantara", "hand": "R",
                   "hr_per_9": 0.65, "hr_per_9_vs_L": 0.60, "hr_per_9_vs_R": 0.70},
    "p_gray":     {"pitcher_id": "p_gray",     "name": "J. Gray",      "hand": "R",
                   "hr_per_9": 1.48, "hr_per_9_vs_L": 1.62, "hr_per_9_vs_R": 1.38},
    "p_freeland": {"pitcher_id": "p_freeland", "name": "K. Freeland",  "hand": "L",
                   "hr_per_9": 1.62, "hr_per_9_vs_L": 0.98, "hr_per_9_vs_R": 2.05},
    "p_wheeler":  {"pitcher_id": "p_wheeler",  "name": "Z. Wheeler",   "hand": "R",
                   "hr_per_9": 0.90, "hr_per_9_vs_L": 0.95, "hr_per_9_vs_R": 0.85},
    "p_kopech":   {"pitcher_id": "p_kopech",   "name": "M. Kopech",    "hand": "R",
                   "hr_per_9": 1.40, "hr_per_9_vs_L": 1.55, "hr_per_9_vs_R": 1.28},
}

# Each batter dict: stats that feed the scoring engine
BATTERS = {
    # NYY batters
    "judge": {
        "player_id": "judge",     "name": "A. Judge",   "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.620,      "vs_LHP_slg": 0.580,
        "barrel_rate": 0.185,     "flyball_rate": 0.42,  "hard_hit_rate": 0.55,
        "pull_rate": 0.46,        "oppo_rate": 0.17,
        "hr_rate": 0.072,
    },
    "stanton": {
        "player_id": "stanton",   "name": "G. Stanton", "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.558,      "vs_LHP_slg": 0.610,
        "barrel_rate": 0.172,     "flyball_rate": 0.39,  "hard_hit_rate": 0.58,
        "pull_rate": 0.44,        "oppo_rate": 0.18,
        "hr_rate": 0.065,
    },
    "rizzo": {
        "player_id": "rizzo",     "name": "A. Rizzo",   "team": "NYY", "batter_hand": "L",
        "vs_RHP_slg": 0.475,      "vs_LHP_slg": 0.380,
        "barrel_rate": 0.095,     "flyball_rate": 0.38,  "hard_hit_rate": 0.44,
        "pull_rate": 0.43,        "oppo_rate": 0.22,
        "hr_rate": 0.042,
    },
    "torres": {
        "player_id": "torres",    "name": "G. Torres",  "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.430,      "vs_LHP_slg": 0.470,
        "barrel_rate": 0.088,     "flyball_rate": 0.35,  "hard_hit_rate": 0.40,
        "pull_rate": 0.41,        "oppo_rate": 0.23,
        "hr_rate": 0.038,
    },
    "bregman": {
        "player_id": "bregman",   "name": "A. Bregman", "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.448,      "vs_LHP_slg": 0.490,
        "barrel_rate": 0.092,     "flyball_rate": 0.37,  "hard_hit_rate": 0.45,
        "pull_rate": 0.38,        "oppo_rate": 0.26,
        "hr_rate": 0.040,
    },
    "trevino": {
        "player_id": "trevino",   "name": "J. Trevino", "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.360,      "vs_LHP_slg": 0.395,
        "barrel_rate": 0.055,     "flyball_rate": 0.30,  "hard_hit_rate": 0.35,
        "pull_rate": 0.37,        "oppo_rate": 0.27,
        "hr_rate": 0.022,
    },
    "volpe": {
        "player_id": "volpe",     "name": "A. Volpe",   "team": "NYY", "batter_hand": "R",
        "vs_RHP_slg": 0.398,      "vs_LHP_slg": 0.420,
        "barrel_rate": 0.072,     "flyball_rate": 0.33,  "hard_hit_rate": 0.38,
        "pull_rate": 0.40,        "oppo_rate": 0.24,
        "hr_rate": 0.028,
    },
    "cabrera_o": {
        "player_id": "cabrera_o", "name": "O. Cabrera", "team": "NYY", "batter_hand": "S",
        "vs_RHP_slg": 0.380,      "vs_LHP_slg": 0.340,
        "barrel_rate": 0.060,     "flyball_rate": 0.31,  "hard_hit_rate": 0.36,
        "pull_rate": 0.39,        "oppo_rate": 0.25,
        "hr_rate": 0.025,
    },
    "soto": {
        "player_id": "soto",      "name": "J. Soto",    "team": "NYY", "batter_hand": "L",
        "vs_RHP_slg": 0.545,      "vs_LHP_slg": 0.470,
        "barrel_rate": 0.142,     "flyball_rate": 0.44,  "hard_hit_rate": 0.50,
        "pull_rate": 0.42,        "oppo_rate": 0.22,
        "hr_rate": 0.055,
    },
    # BOS batters
    "devers": {
        "player_id": "devers",    "name": "R. Devers",  "team": "BOS", "batter_hand": "L",
        "vs_RHP_slg": 0.565,      "vs_LHP_slg": 0.440,
        "barrel_rate": 0.155,     "flyball_rate": 0.41,  "hard_hit_rate": 0.52,
        "pull_rate": 0.48,        "oppo_rate": 0.18,
        "hr_rate": 0.060,
    },
    "casas": {
        "player_id": "casas",     "name": "T. Casas",   "team": "BOS", "batter_hand": "L",
        "vs_RHP_slg": 0.490,      "vs_LHP_slg": 0.370,
        "barrel_rate": 0.115,     "flyball_rate": 0.40,  "hard_hit_rate": 0.47,
        "pull_rate": 0.45,        "oppo_rate": 0.20,
        "hr_rate": 0.048,
    },
    "yoshida": {
        "player_id": "yoshida",   "name": "M. Yoshida", "team": "BOS", "batter_hand": "L",
        "vs_RHP_slg": 0.460,      "vs_LHP_slg": 0.390,
        "barrel_rate": 0.085,     "flyball_rate": 0.36,  "hard_hit_rate": 0.43,
        "pull_rate": 0.36,        "oppo_rate": 0.28,
        "hr_rate": 0.038,
    },
    "turner_j": {
        "player_id": "turner_j",  "name": "J. Turner",  "team": "BOS", "batter_hand": "R",
        "vs_RHP_slg": 0.435,      "vs_LHP_slg": 0.475,
        "barrel_rate": 0.090,     "flyball_rate": 0.37,  "hard_hit_rate": 0.42,
        "pull_rate": 0.40,        "oppo_rate": 0.24,
        "hr_rate": 0.035,
    },
    "mccloskey": {
        "player_id": "mccloskey", "name": "C. McCall",  "team": "BOS", "batter_hand": "R",
        "vs_RHP_slg": 0.355,      "vs_LHP_slg": 0.385,
        "barrel_rate": 0.052,     "flyball_rate": 0.29,  "hard_hit_rate": 0.34,
        "pull_rate": 0.38,        "oppo_rate": 0.26,
        "hr_rate": 0.019,
    },
    "rafaela": {
        "player_id": "rafaela",   "name": "C. Rafaela", "team": "BOS", "batter_hand": "R",
        "vs_RHP_slg": 0.415,      "vs_LHP_slg": 0.440,
        "barrel_rate": 0.078,     "flyball_rate": 0.34,  "hard_hit_rate": 0.40,
        "pull_rate": 0.39,        "oppo_rate": 0.25,
        "hr_rate": 0.032,
    },
    "wong_c": {
        "player_id": "wong_c",    "name": "C. Wong",    "team": "BOS", "batter_hand": "R",
        "vs_RHP_slg": 0.345,      "vs_LHP_slg": 0.375,
        "barrel_rate": 0.048,     "flyball_rate": 0.28,  "hard_hit_rate": 0.33,
        "pull_rate": 0.37,        "oppo_rate": 0.27,
        "hr_rate": 0.018,
    },
    "duran_j": {
        "player_id": "duran_j",   "name": "J. Duran",   "team": "BOS", "batter_hand": "L",
        "vs_RHP_slg": 0.500,      "vs_LHP_slg": 0.410,
        "barrel_rate": 0.120,     "flyball_rate": 0.38,  "hard_hit_rate": 0.48,
        "pull_rate": 0.44,        "oppo_rate": 0.21,
        "hr_rate": 0.048,
    },
    "abreu_w": {
        "player_id": "abreu_w",   "name": "W. Abreu",   "team": "BOS", "batter_hand": "R",
        "vs_RHP_slg": 0.418,      "vs_LHP_slg": 0.450,
        "barrel_rate": 0.080,     "flyball_rate": 0.35,  "hard_hit_rate": 0.41,
        "pull_rate": 0.41,        "oppo_rate": 0.24,
        "hr_rate": 0.033,
    },
    # COL batters (Coors)
    "mcmahon": {
        "player_id": "mcmahon",   "name": "R. McMahon", "team": "COL", "batter_hand": "L",
        "vs_RHP_slg": 0.455,      "vs_LHP_slg": 0.375,
        "barrel_rate": 0.098,     "flyball_rate": 0.39,  "hard_hit_rate": 0.44,
        "pull_rate": 0.43,        "oppo_rate": 0.21,
        "hr_rate": 0.042,
    },
    "tovar": {
        "player_id": "tovar",     "name": "E. Tovar",   "team": "COL", "batter_hand": "R",
        "vs_RHP_slg": 0.420,      "vs_LHP_slg": 0.460,
        "barrel_rate": 0.082,     "flyball_rate": 0.34,  "hard_hit_rate": 0.39,
        "pull_rate": 0.40,        "oppo_rate": 0.24,
        "hr_rate": 0.030,
    },
    "doyle": {
        "player_id": "doyle",     "name": "B. Doyle",   "team": "COL", "batter_hand": "L",
        "vs_RHP_slg": 0.480,      "vs_LHP_slg": 0.390,
        "barrel_rate": 0.105,     "flyball_rate": 0.40,  "hard_hit_rate": 0.46,
        "pull_rate": 0.45,        "oppo_rate": 0.20,
        "hr_rate": 0.045,
    },
    "rodgers": {
        "player_id": "rodgers",   "name": "B. Rodgers", "team": "COL", "batter_hand": "R",
        "vs_RHP_slg": 0.465,      "vs_LHP_slg": 0.490,
        "barrel_rate": 0.100,     "flyball_rate": 0.38,  "hard_hit_rate": 0.45,
        "pull_rate": 0.42,        "oppo_rate": 0.22,
        "hr_rate": 0.040,
    },
    "blackmon": {
        "player_id": "blackmon",  "name": "C. Blackmon","team": "COL", "batter_hand": "L",
        "vs_RHP_slg": 0.445,      "vs_LHP_slg": 0.360,
        "barrel_rate": 0.090,     "flyball_rate": 0.37,  "hard_hit_rate": 0.43,
        "pull_rate": 0.41,        "oppo_rate": 0.23,
        "hr_rate": 0.038,
    },
    "stallings": {
        "player_id": "stallings", "name": "J. Stallings","team": "COL", "batter_hand": "R",
        "vs_RHP_slg": 0.330,      "vs_LHP_slg": 0.360,
        "barrel_rate": 0.045,     "flyball_rate": 0.27,  "hard_hit_rate": 0.32,
        "pull_rate": 0.36,        "oppo_rate": 0.28,
        "hr_rate": 0.015,
    },
    "bouchard": {
        "player_id": "bouchard",  "name": "S. Bouchard","team": "COL", "batter_hand": "L",
        "vs_RHP_slg": 0.460,      "vs_LHP_slg": 0.370,
        "barrel_rate": 0.100,     "flyball_rate": 0.39,  "hard_hit_rate": 0.45,
        "pull_rate": 0.43,        "oppo_rate": 0.21,
        "hr_rate": 0.042,
    },
    "trejo": {
        "player_id": "trejo",     "name": "A. Trejo",   "team": "COL", "batter_hand": "R",
        "vs_RHP_slg": 0.340,      "vs_LHP_slg": 0.365,
        "barrel_rate": 0.048,     "flyball_rate": 0.29,  "hard_hit_rate": 0.34,
        "pull_rate": 0.38,        "oppo_rate": 0.26,
        "hr_rate": 0.018,
    },
    "hilliard": {
        "player_id": "hilliard",  "name": "S. Hilliard","team": "COL", "batter_hand": "R",
        "vs_RHP_slg": 0.395,      "vs_LHP_slg": 0.430,
        "barrel_rate": 0.075,     "flyball_rate": 0.36,  "hard_hit_rate": 0.39,
        "pull_rate": 0.40,        "oppo_rate": 0.24,
        "hr_rate": 0.030,
    },
    # ARI batters (at COL - visiting)
    "walker_ch": {
        "player_id": "walker_ch", "name": "C. Walker",  "team": "ARI", "batter_hand": "R",
        "vs_RHP_slg": 0.505,      "vs_LHP_slg": 0.545,
        "barrel_rate": 0.130,     "flyball_rate": 0.42,  "hard_hit_rate": 0.50,
        "pull_rate": 0.44,        "oppo_rate": 0.19,
        "hr_rate": 0.052,
    },
    "carroll": {
        "player_id": "carroll",   "name": "C. Carroll", "team": "ARI", "batter_hand": "L",
        "vs_RHP_slg": 0.470,      "vs_LHP_slg": 0.385,
        "barrel_rate": 0.108,     "flyball_rate": 0.39,  "hard_hit_rate": 0.46,
        "pull_rate": 0.44,        "oppo_rate": 0.21,
        "hr_rate": 0.043,
    },
    "thomas_k": {
        "player_id": "thomas_k",  "name": "K. Thomas",  "team": "ARI", "batter_hand": "L",
        "vs_RHP_slg": 0.520,      "vs_LHP_slg": 0.430,
        "barrel_rate": 0.135,     "flyball_rate": 0.43,  "hard_hit_rate": 0.52,
        "pull_rate": 0.46,        "oppo_rate": 0.19,
        "hr_rate": 0.055,
    },
    "gurriel": {
        "player_id": "gurriel",   "name": "L. Gurriel", "team": "ARI", "batter_hand": "R",
        "vs_RHP_slg": 0.405,      "vs_LHP_slg": 0.440,
        "barrel_rate": 0.078,     "flyball_rate": 0.33,  "hard_hit_rate": 0.39,
        "pull_rate": 0.39,        "oppo_rate": 0.25,
        "hr_rate": 0.030,
    },
    "marte_k": {
        "player_id": "marte_k",   "name": "K. Marte",   "team": "ARI", "batter_hand": "R",
        "vs_RHP_slg": 0.435,      "vs_LHP_slg": 0.465,
        "barrel_rate": 0.088,     "flyball_rate": 0.35,  "hard_hit_rate": 0.42,
        "pull_rate": 0.40,        "oppo_rate": 0.24,
        "hr_rate": 0.035,
    },
    "beer": {
        "player_id": "beer",      "name": "S. Beer",    "team": "ARI", "batter_hand": "L",
        "vs_RHP_slg": 0.480,      "vs_LHP_slg": 0.370,
        "barrel_rate": 0.108,     "flyball_rate": 0.40,  "hard_hit_rate": 0.46,
        "pull_rate": 0.44,        "oppo_rate": 0.21,
        "hr_rate": 0.044,
    },
    "perdomo": {
        "player_id": "perdomo",   "name": "G. Perdomo", "team": "ARI", "batter_hand": "S",
        "vs_RHP_slg": 0.395,      "vs_LHP_slg": 0.360,
        "barrel_rate": 0.070,     "flyball_rate": 0.31,  "hard_hit_rate": 0.37,
        "pull_rate": 0.38,        "oppo_rate": 0.26,
        "hr_rate": 0.026,
    },
    "longoria": {
        "player_id": "longoria",  "name": "E. Longoria","team": "ARI", "batter_hand": "R",
        "vs_RHP_slg": 0.415,      "vs_LHP_slg": 0.455,
        "barrel_rate": 0.085,     "flyball_rate": 0.36,  "hard_hit_rate": 0.41,
        "pull_rate": 0.41,        "oppo_rate": 0.23,
        "hr_rate": 0.033,
    },
    "hazen": {
        "player_id": "hazen",     "name": "M. Moreno",  "team": "ARI", "batter_hand": "R",
        "vs_RHP_slg": 0.450,      "vs_LHP_slg": 0.485,
        "barrel_rate": 0.095,     "flyball_rate": 0.37,  "hard_hit_rate": 0.44,
        "pull_rate": 0.41,        "oppo_rate": 0.23,
        "hr_rate": 0.038,
    },
}

GAMES = [
    {
        "game_id":  "nyy_bos",
        "away":     "NYY",
        "home":     "BOS",
        "park_id":  "fenway",
        "time":     "7:10 PM ET",
        "label":    "NYY @ BOS — Fenway",
    },
    {
        "game_id":  "ari_col",
        "away":     "ARI",
        "home":     "COL",
        "park_id":  "coors",
        "time":     "6:40 PM MT",
        "label":    "ARI @ COL — Coors",
    },
]

LINEUPS = {
    "nyy_bos": {
        "NYY": {
            "pitcher_id":    "p_kopech",
            "batting_order": [
                ("soto",     1),
                ("judge",    2),
                ("stanton",  3),
                ("rizzo",    4),
                ("bregman",  5),
                ("torres",   6),
                ("volpe",    7),
                ("trevino",  8),
                ("cabrera_o",9),
            ],
        },
        "BOS": {
            "pitcher_id":    "p_snell",
            "batting_order": [
                ("rafaela",  1),
                ("turner_j", 2),
                ("devers",   3),
                ("casas",    4),
                ("duran_j",  5),
                ("yoshida",  6),
                ("abreu_w",  7),
                ("mccloskey",8),
                ("wong_c",   9),
            ],
        },
    },
    "ari_col": {
        "ARI": {
            "pitcher_id":    "p_gray",
            "batting_order": [
                ("carroll",   1),
                ("thomas_k",  2),
                ("walker_ch", 3),
                ("gurriel",   4),
                ("marte_k",   5),
                ("beer",      6),
                ("longoria",  7),
                ("perdomo",   8),
                ("hazen",     9),
            ],
        },
        "COL": {
            "pitcher_id":    "p_freeland",
            "batting_order": [
                ("tovar",     1),
                ("rodgers",   2),
                ("mcmahon",   3),
                ("doyle",     4),
                ("blackmon",  5),
                ("bouchard",  6),
                ("hilliard",  7),
                ("stallings", 8),
                ("trejo",     9),
            ],
        },
    },
}

# Weather keyed by game_id
WEATHER = {
    "nyy_bos": {
        "temp":           58,
        "humidity":       62,
        "wind_speed":     12,
        "wind_direction": "SW",    # blowing toward NE — toward RF at Fenway
        "conditions":     "Partly Cloudy",
    },
    "ari_col": {
        "temp":           80,
        "humidity":       35,
        "wind_speed":     14,
        "wind_direction": "SE",    # blowing toward NW — helps LHB pull at Coors
        "conditions":     "Clear",
    },
}

