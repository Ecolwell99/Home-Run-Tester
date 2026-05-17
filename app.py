"""
MLB Home Run Probability Screener
Streamlit dashboard — dark mode, trading-desk style.
"""

import datetime as _dt
import streamlit as st
import pandas as pd
import data_loader
import scoring

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MLB HR Screener",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS: dark, dense, minimal ─────────────────────────────────────────
st.markdown("""
<style>
  /* Base dark background */
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
    background-color: #0d0d0d;
    color: #d0d0d0;
  }
  /* Remove default padding */
  .block-container { padding-top: 1rem; padding-bottom: 0; }
  /* Header strip */
  .hdr { font-size: 11px; color: #555; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 2px; }
  .title { font-size: 18px; font-weight: 700; color: #e8e8e8; margin-bottom: 0; }
  .subtitle { font-size: 11px; color: #666; margin-bottom: 12px; }
  /* Tier badges */
  .tier-elite   { background:#1a3a1a; color:#4dff4d; padding:1px 7px; border-radius:3px;
                  font-size:11px; font-weight:700; letter-spacing:.04em; }
  .tier-strong  { background:#1a2e3a; color:#4db8ff; padding:1px 7px; border-radius:3px;
                  font-size:11px; font-weight:700; letter-spacing:.04em; }
  .tier-neutral { background:#2a2a1a; color:#cccc44; padding:1px 7px; border-radius:3px;
                  font-size:11px; font-weight:700; letter-spacing:.04em; }
  .tier-fade    { background:#2a1a1a; color:#cc4444; padding:1px 7px; border-radius:3px;
                  font-size:11px; font-weight:700; letter-spacing:.04em; }
  /* Score bar */
  .score-bar-wrap { background:#1e1e1e; border-radius:3px; height:6px; width:100%; }
  .score-bar      { background:#4db8ff; border-radius:3px; height:6px; }
  /* Expander rows */
  [data-testid="stExpander"] {
    border: 1px solid #1f1f1f !important;
    border-radius: 4px !important;
    background: #111 !important;
    margin-bottom: 3px !important;
  }
  details summary { font-size: 12px !important; color: #bbb !important; }
  /* Metric widget */
  [data-testid="stMetric"] { background: #111; border-radius: 4px; padding: 6px 10px; }
  [data-testid="stMetricValue"] { font-size: 15px !important; color: #e8e8e8 !important; }
  [data-testid="stMetricLabel"] { font-size: 10px !important; color: #777 !important; text-transform: uppercase; }
  /* Sidebar */
  [data-testid="stSidebar"] .stSelectbox label,
  [data-testid="stSidebar"] .stMultiSelect label,
  [data-testid="stSidebar"] .stSlider label { font-size: 11px; color: #888; text-transform: uppercase; }
  /* DataFrame tweaks */
  [data-testid="stDataFrame"] { font-size: 12px; }
  /* Dividers */
  hr { border-color: #1f1f1f; }
</style>
""", unsafe_allow_html=True)


# ── Load + score data ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def get_scored_df(date: str | None = None) -> tuple[pd.DataFrame, dict]:
    data = data_loader.load_all(date=date)
    rows = data_loader.build_rows(data)
    meta = {
        "game_count":   len(data.get("games", [])),
        "batter_count": sum(
            len(side.get("batting_order", []))
            for gid, lu in data.get("lineups", {}).items()
            for side in lu.values()
        ),
        "is_live": True,
    }
    records = []
    for row in rows:
        sc = scoring.compute_hr_score(
            row["batter"], row["pitcher"],
            row["park"],   row["weather"],
            row["pitcher_hand"],
        )
        explanation = scoring.generate_explanation(
            row["batter"], row["pitcher"],
            row["park"],   row["weather"],
            sc,
        )
        b = row["batter"]
        p = row["pitcher"]
        pk = row["park"]
        wx = row["weather"]
        records.append({
            "Player":              b["name"],
            "Team":                row["batting_team"],
            "Opp":                 row["opp_team"],
            "Order":               row["batting_order"],
            "Side":                b.get("batter_hand", "R"),   # original hand (S preserved)
            "Bats":                sc["effective_hand"],         # resolved hand (S→L or R)
            "Pitcher":             p["name"],
            "P Hand":              p["hand"],
            "Park":                pk["name"],
            "Wind":                f"{wx['wind_speed']} mph {wx['wind_direction']}",
            "Temp":                f"{wx['temp']}°F",
            "HR Score":            sc["hr_score"],
            "Split Power":         round(sc["batter_power_vs_hand"] * 100, 1),
            "Barrel/FB":           round(sc["barrel_flyball_profile"] * 100, 1),
            "Wind Fit":            round(sc["directional_wind_fit"] * 100, 1),
            "Park Boost":          round(sc["park_factor"] * 100, 1),
            "Pitcher Vuln":        round(sc["pitcher_hr_vulnerability"] * 100, 1),
            "Carry":               round(sc["weather_carry_score"] * 100, 1),
            "Tier":                sc["tier"],
            "Explanation":         explanation,
            "_game":               row["game_label"],
            "_game_id":            row["game_id"],
        })
    df = pd.DataFrame(records) if records else pd.DataFrame()
    if not df.empty:
        df = df.sort_values("HR Score", ascending=False).reset_index(drop=True)
    return df, meta


# ── Helpers ───────────────────────────────────────────────────────────────────

def tier_badge(tier: str) -> str:
    cls = f"tier-{tier.lower()}"
    return f'<span class="{cls}">{tier}</span>'


def score_bar(score: float) -> str:
    pct = min(100, max(0, score))
    color = "#4dff4d" if pct >= 75 else "#4db8ff" if pct >= 55 else "#cccc44" if pct >= 35 else "#cc4444"
    return (
        f'<div class="score-bar-wrap">'
        f'<div class="score-bar" style="width:{pct}%; background:{color};"></div>'
        f'</div>'
    )


def sub_gauge(val: float) -> str:
    """Small colored score dot for sub-scores (0-100)."""
    if val >= 65:
        c = "#4dff4d"
    elif val >= 40:
        c = "#cccc44"
    else:
        c = "#cc4444"
    return f'<span style="color:{c}; font-weight:700;">{val:.0f}</span>'


# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<div class="hdr">MLB HR Screener</div>', unsafe_allow_html=True)
    st.markdown('<div class="title">Filters</div>', unsafe_allow_html=True)
    st.markdown("---")

    sel_date = st.date_input("Date", value=_dt.date.today(), label_visibility="visible")
    sel_date_str = sel_date.isoformat()

    if st.button("Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

df_all, _meta = get_scored_df(date=sel_date_str)

with st.sidebar:
    games_available = df_all["_game"].unique().tolist() if not df_all.empty else []
    sel_games = st.multiselect("Game", games_available, default=games_available)

    teams_available = sorted(df_all["Team"].unique().tolist()) if not df_all.empty else []
    sel_teams = st.multiselect("Team", teams_available, default=teams_available)

    tiers_available = ["Elite", "Strong", "Neutral", "Fade"]
    sel_tiers = st.multiselect("Tier", tiers_available, default=tiers_available)

    sides_available = ["L", "R", "S"]
    sel_sides = st.multiselect("Batter Side", sides_available, default=["L", "R", "S"])

    parks_available = sorted(df_all["Park"].unique().tolist()) if not df_all.empty else []
    sel_parks = st.multiselect("Park", parks_available, default=parks_available)

    min_score, max_score = st.slider("HR Score Range", 0, 100, (0, 100))

    st.markdown("---")
    st.markdown('<div class="hdr">Score Formula</div>', unsafe_allow_html=True)
    st.markdown("""
<div style="font-size:10px; color:#666; line-height:1.8;">
0.25 × Split Power<br>
0.20 × Barrel/FB Profile<br>
0.20 × <b style="color:#aaa;">Directional Wind Fit ★</b><br>
0.15 × Pitcher Vuln<br>
0.10 × Park Factor<br>
0.10 × Carry (Temp/Humidity)
</div>
""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:10px; color:#555;">Live data · {_meta["game_count"]} games · '
        f'{_meta["batter_count"]} lineup slots</div>',
        unsafe_allow_html=True,
    )


# ── Apply filters ─────────────────────────────────────────────────────────────

if df_all.empty:
    df = df_all
else:
    df = df_all[
        df_all["_game"].isin(sel_games) &
        df_all["Team"].isin(sel_teams) &
        df_all["Tier"].isin(sel_tiers) &
        df_all["Side"].isin(sel_sides) &
        df_all["Park"].isin(sel_parks) &
        df_all["HR Score"].between(min_score, max_score)
    ].reset_index(drop=True)


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown('<div class="hdr">MLB</div>', unsafe_allow_html=True)
st.markdown('<div class="title">Home Run Probability Screener</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Directional wind fit · Split power · Park factors · Pitcher vulnerability</div>', unsafe_allow_html=True)

# Lineup availability notice
if _meta["game_count"] > 0 and _meta["batter_count"] == 0:
    st.warning(
        "Lineups not yet posted for today's games. "
        "Batting order rows will populate ~60–90 min before first pitch. "
        "Pitcher matchups are shown where probable starters are available.",
        icon="⏳",
    )
elif df_all.empty:
    st.info(f"No games found for {sel_date_str}. Try a different date.", icon="📅")

# Summary metrics row
c1, c2, c3, c4, c5 = st.columns(5)
elite_n   = len(df[df["Tier"] == "Elite"])   if not df.empty else 0
strong_n  = len(df[df["Tier"] == "Strong"])  if not df.empty else 0
avg_score = df["HR Score"].mean()             if not df.empty else 0.0
with c1: st.metric("Total Batters", len(df))
with c2: st.metric("Elite",  elite_n)
with c3: st.metric("Strong", strong_n)
with c4: st.metric("Avg HR Score", f"{avg_score:.1f}")
with c5: st.metric("Games", _meta["game_count"])

st.markdown("---")


# ── View toggle ───────────────────────────────────────────────────────────────

view = st.radio("View", ["Ranked Cards", "Raw Table", "Debug"], horizontal=True, label_visibility="collapsed")
st.markdown("")


# ── Ranked Cards view ─────────────────────────────────────────────────────────

if view == "Ranked Cards":
    if df.empty:
        st.warning("No batters match the current filters.")
    else:
        for _, row in df.iterrows():
            tier     = row["Tier"]
            score    = row["HR Score"]
            name_tag = f"#{row['Order']} {row['Player']} · {row['Team']}"

            with st.expander(
                f"{name_tag}  —  {score:.1f}  {tier}",
                expanded=(tier == "Elite"),
            ):
                col_a, col_b, col_c = st.columns([2, 2, 3])

                with col_a:
                    st.markdown(f"**HR Score** {score:.1f} / 100")
                    st.markdown(score_bar(score), unsafe_allow_html=True)
                    st.markdown(tier_badge(tier), unsafe_allow_html=True)
                    st.markdown("")
                    side_label = row['Side'] + ("→" + row['Bats'] if row['Side'] == 'S' else "")
                    st.markdown(f"**Batter:** {row['Player']} ({side_label}HB)")
                    st.markdown(f"**vs:** {row['Pitcher']} ({row['P Hand']}HP)")
                    st.markdown(f"**Park:** {row['Park']}")
                    st.markdown(f"**Weather:** {row['Wind']}, {row['Temp']}")

                with col_b:
                    st.markdown("**Sub-scores (0–100)**")
                    sub_rows = [
                        ("Split Power",    row["Split Power"],   "SLG vs pitcher hand"),
                        ("Barrel/FB",      row["Barrel/FB"],     "Barrel + fly-ball + hard-hit"),
                        ("Wind Fit",       row["Wind Fit"],      "Directional alignment"),
                        ("Pitcher Vuln",   row["Pitcher Vuln"],  "HR/9 allowed vs this side"),
                        ("Park Boost",     row["Park Boost"],    "HR park factor"),
                        ("Carry",          row["Carry"],         "Temp + humidity carry"),
                    ]
                    for label, val, desc in sub_rows:
                        st.markdown(
                            f'<div style="display:flex; justify-content:space-between; '
                            f'font-size:11px; margin-bottom:3px;">'
                            f'<span style="color:#888;">{label}</span>'
                            f'{sub_gauge(val)}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                with col_c:
                    st.markdown("**Analysis**")
                    explanation = row["Explanation"]
                    parts = explanation.split(" | ")
                    for part in parts:
                        st.markdown(f"- {part}")


# ── Raw Table view ────────────────────────────────────────────────────────────

elif view == "Raw Table":
    if df.empty:
        st.warning("No batters match the current filters.")
    else:
        display_cols = [
            "Player", "Team", "Opp", "Order", "Side", "Bats",
            "Pitcher", "P Hand", "Park", "Wind", "Temp",
            "HR Score", "Split Power", "Barrel/FB", "Wind Fit",
            "Park Boost", "Pitcher Vuln", "Carry", "Tier",
        ]
        st.dataframe(
            df[display_cols].style
                .background_gradient(subset=["HR Score"], cmap="RdYlGn", vmin=0, vmax=100)
                .background_gradient(subset=["Wind Fit"], cmap="RdYlGn", vmin=0, vmax=100)
                .format({
                    "HR Score":    "{:.1f}",
                    "Split Power": "{:.1f}",
                    "Barrel/FB":   "{:.1f}",
                    "Wind Fit":    "{:.1f}",
                    "Park Boost":  "{:.1f}",
                    "Pitcher Vuln":"{:.1f}",
                    "Carry":       "{:.1f}",
                }),
            use_container_width=True,
            height=620,
        )
        st.markdown("---")
        st.markdown("**Explanation**")
        sel_name = st.selectbox("Select player", df["Player"].tolist(), label_visibility="collapsed")
        if sel_name:
            row_exp = df[df["Player"] == sel_name].iloc[0]
            parts = row_exp["Explanation"].split(" | ")
            for p in parts:
                st.markdown(f"- {p}")


# ── Debug view ────────────────────────────────────────────────────────────────

elif view == "Debug":
    import datetime as _dt2
    st.markdown("### Data Pipeline Diagnostics")

    # ── FanGraphs batting ──
    st.markdown("#### 1. FanGraphs Batting Stats")
    fg = data_loader._fetch_fg_batting()
    if fg.empty:
        st.error("FAILED — empty DataFrame. pybaseball may not be installed or FanGraphs is unreachable.")
    else:
        st.success(f"OK — {len(fg)} rows")
        st.write("Columns:", list(fg.columns))
        sample_cols = [c for c in ["Name", "Team", "SLG", "Bat", "bat", "HR", "PA"] if c in fg.columns]
        st.dataframe(fg[sample_cols].head(15))

    # ── Savant batted-ball ──
    st.markdown("#### 2. Savant Batted-Ball CSV")
    sv = data_loader._fetch_savant_batted_ball()
    if sv.empty:
        st.error("FAILED — empty DataFrame.")
    else:
        st.success(f"OK — {len(sv)} rows")
        st.write("Columns:", list(sv.columns))
        st.dataframe(sv.head(5))

    # ── FanGraphs pitching ──
    st.markdown("#### 3. FanGraphs Pitching Stats")
    try:
        from pybaseball import pitching_stats
        pf = pitching_stats(_dt2.date.today().year, qual=10)
        if pf is None or pf.empty:
            st.error("FAILED — empty")
        else:
            st.success(f"OK — {len(pf)} rows")
            sample_cols = [c for c in ["Name", "Team", "HR/9", "throws", "Throws"] if c in pf.columns]
            st.dataframe(pf[sample_cols].head(15))
    except Exception as e:
        st.error(f"FAILED — {e}")

    # ── Name key match rate ──
    st.markdown("#### 4. Name Key Match Rate (FanGraphs ↔ MLB Lineup API)")
    if not fg.empty:
        fg_keys = set(data_loader._player_key(str(r.get("Name", ""))) for _, r in fg.iterrows())
        lineup_keys = set()
        for lu in data_loader.load_all(date=sel_date_str)["lineups"].values():
            for side in lu.values():
                for k, _ in side.get("batting_order", []):
                    lineup_keys.add(k)

        matched   = lineup_keys & fg_keys
        unmatched = lineup_keys - fg_keys

        c1, c2, c3 = st.columns(3)
        c1.metric("Lineup keys", len(lineup_keys))
        c2.metric("Matched to FG", len(matched))
        c3.metric("Unmatched (stubs)", len(unmatched))

        if unmatched:
            st.markdown("**Unmatched lineup keys** (these players are using stub data):")
            st.write(sorted(unmatched))
            st.markdown("**Sample FanGraphs keys** (for comparison):")
            st.write(sorted(fg_keys)[:20])
    else:
        st.warning("Skipped — FanGraphs data unavailable.")

    # ── Score breakdown for first real batter ──
    st.markdown("#### 5. Score Breakdown — First Batter in Results")
    if not df_all.empty:
        r = df_all.iloc[0]
        st.write({
            "Player":       r["Player"],
            "vs_RHP_slg":   data_loader._BATTER_REGISTRY.get(
                                data_loader._player_key(r["Player"]), {}
                            ).get("vs_RHP_slg", "not in registry — check batters dict"),
            "Split Power":  r["Split Power"],
            "Barrel/FB":    r["Barrel/FB"],
            "Wind Fit":     r["Wind Fit"],
            "Park Boost":   r["Park Boost"],
            "Pitcher Vuln": r["Pitcher Vuln"],
            "Carry":        r["Carry"],
            "HR Score":     r["HR Score"],
        })
