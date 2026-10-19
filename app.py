from datetime import datetime, timezone
import pandas as pd
import streamlit as st
from supabase import create_client

# FightClub Live — hypothetical simulation only. No real money or payments.
st.set_page_config(page_title="FightClub Live", page_icon="🥊", layout="wide")
ALI_BACKGROUND = "https://img.gallerix.com/product/4280_29567.jpg?width=1080&height=1080&mode=fit&enlarge=true"
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600;700&family=Oswald:wght@400;500;600&display=swap');

    .stApp {{
        background: #171310;
        color: #E8DCC4;
    }}

    .stApp::before {{
        content: "";
        position: fixed;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background:
            linear-gradient(rgba(18,14,11,.70), rgba(18,14,11,.86)),
            url("{ALI_BACKGROUND}") center center / cover no-repeat;
    }}

    [data-testid="stAppViewContainer"],
    [data-testid="stHeader"],
    [data-testid="stSidebar"] {{
        background: transparent;
    }}

    [data-testid="stMain"] {{
        position: relative;
        z-index: 1;
    }}

    h1, h2, h3 {{
        font-family: 'Cormorant Garamond', serif !important;
        color: #E8DCC4 !important;
    }}

    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: rgba(30,23,17,.82);
        border: 1px solid rgba(184,151,103,.68);
        border-radius: 8px;
    }}

    [data-testid="stMetric"] {{
        background: rgba(35,27,20,.78);
        border: 1px solid #69533E;
        border-radius: 8px;
        padding: 14px;
    }}

    [data-testid="stSidebar"] {{
        border-right: 1px solid #493526;
    }}

    .stButton > button {{
        border: 1px solid #A98A5D;
        background: rgba(50,37,26,.9);
        color: #F0E4CD;
        border-radius: 5px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

HOUSE_SHARE_RATE = 0.07  # Fixed simulation parameter; not editable in the UI.
FIGHTER_SHARE_RATE = 0.10 # New parameter: 10% of total pool goes to the winning fighter.

DEFAULT_STATE = {
    "fighter_a": "Marcus",
    "fighter_b": "Leo",
    "match_status": "UPCOMING",
    "winner": None,
    "fight_start_time": None,
    "fight_elapsed_seconds": 0.0,
    "fighter_roster": [],
    "points_entries": [],
    "points_ledger": {},
}

@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])

def load_state():
    result = get_supabase().table("match_state").select("*").eq("id", 1).single().execute()
    row = result.data or {}
    state = DEFAULT_STATE.copy()
    state.update({k: row.get(k) for k in DEFAULT_STATE if k in row})
    state["fighter_roster"] = state.get("fighter_roster") or []
    state["points_entries"] = state.get("points_entries") or []
    state["points_ledger"] = state.get("points_ledger") or {}
    state["fight_elapsed_seconds"] = float(state.get("fight_elapsed_seconds") or 0)
    return state

def save_state(state):
    payload = {
        "fighter_a": state["fighter_a"],
        "fighter_b": state["fighter_b"],
        "match_status": state["match_status"],
        "winner": state.get("winner"),
        "fight_start_time": state["fight_start_time"],
        "fight_elapsed_seconds": float(state["fight_elapsed_seconds"]),
        "fighter_roster": state["fighter_roster"],
        "points_entries": state["points_entries"],
        "points_ledger": state["points_ledger"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_supabase().table("match_state").update(payload).eq("id", 1).execute()

def admin_is_configured():
    return bool(st.secrets.get("ADMIN_PASSWORD", ""))

def active_elapsed(state):
    elapsed = float(state.get("fight_elapsed_seconds") or 0)
    start = state.get("fight_start_time")
    if state.get("match_status") == "FIGHTING" and start:
        try:
            parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            elapsed += max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
        except (ValueError, TypeError, AttributeError):
            pass
    return elapsed

def format_clock(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    tenths = int((seconds * 10) % 10)
    return f"{minutes:02d}:{secs:02d}.{tenths}"

def amount(entry):
    try:
        return max(0.0, float(entry.get("stake", entry.get("points", 0))))
    except (TypeError, ValueError):
        return 0.0

def pool_summary(entries):
    total_pool = sum(amount(e) for e in entries)
    house_take = total_pool * HOUSE_SHARE_RATE
    fighter_take = total_pool * FIGHTER_SHARE_RATE
    distributable = total_pool - house_take - fighter_take
    winning_entries = [e for e in entries if str(e.get("result", "PENDING")).upper() == "WIN"]
    winning_stakes = sum(amount(e) for e in winning_entries)
    payouts = {}
    for e in entries:
        result = str(e.get("result", "PENDING")).upper()
        stake = amount(e)
        if result == "WIN" and winning_stakes > 0:
            payout = distributable * stake / winning_stakes
            profit = payout - stake
        else:
            payout = 0.0
            profit = 0.0
        payouts[id(e)] = (payout, profit)
    return total_pool, house_take, fighter_take, distributable, payouts

def render_activity(entries, target):
    matched = [e for e in entries if e.get("target") == target]
    if not matched:
        st.caption("No simulated activity yet.")
        return
    _, _, _, _, payouts = pool_summary(entries)
    for entry in reversed(matched[-20:]):
        result = str(entry.get("result", "PENDING")).upper()
        stake = amount(entry)
        payout, profit = payouts[id(entry)]
        if result == "PENDING":
            line = f"**{entry.get('name', 'Participant')}** — ${stake:,.2f} simulated stake · PENDING"
            st.write(line)
        else:
            line = (
                f"**{entry.get('name', 'Participant')}** — ${stake:,.2f} simulated stake "
                f"(${payout:,.2f}) / (+${profit:,.2f}) {result}"
            )
            if result == "WIN":
                st.markdown(f":green[{line}]")
            else:
                st.markdown(f":red[{line}]")

def render_roster(roster):
    if not roster:
        st.info("No fighters have been added yet.")
        return
    df = pd.DataFrame(roster)
    if "Points" in df.columns:
        df = df.sort_values("Points", ascending=False)
    cols = [c for c in ["Name", "Height", "Weight", "Grade", "Points"] if c in df.columns]
    st.dataframe(df[cols] if cols else df, use_container_width=True, hide_index=True)

st.sidebar.title("🥊 FightClub Live")
view = st.sidebar.radio("Navigate", [
    "⚡ Live Public Dashboard", "🏆 Leaderboards", "🔒 Admin Control", "🗂️ Fighter Profiles"
])

try:
    state = load_state()
except Exception as exc:
    st.error("Could not load the shared Supabase match data.")
    st.caption("Check Streamlit Secrets and confirm the match_state columns, including fight_elapsed_seconds, are set up.")
    st.stop()

if view == "⚡ Live Public Dashboard":
    st.title("🥊 FightClub Live")
    st.caption("Hypothetical simulation only · live updates every 0.4 seconds")

    @st.fragment(run_every=0.4)
    def live_dashboard():
        current = load_state()
        entries = current["points_entries"]
        total_pool, _, _, _, _ = pool_summary(entries)
        st.write(f"**Current status:** {current['match_status']}")
        if current.get("winner"):
            st.success(f"Simulation result: {current['winner']} wins")
        left, right = st.columns(2)
        left.metric("⏱️ Official fight clock", format_clock(active_elapsed(current)))
        right.metric("🎯 Total simulated pool", f"${total_pool:,.2f}")
        st.divider()
        red, blue = st.columns(2)
        for col, key, color in [(red, "fighter_a", "🔴"), (blue, "fighter_b", "🔵")]:
            fighter_name = current[key]
            matched = [e for e in entries if e.get("target") == fighter_name]
            total = sum(amount(e) for e in matched)
            total_all = sum(amount(e) for e in entries)
            with col:
                st.subheader(f"{color} {fighter_name}")
                st.metric("Simulated entries", f"${total:,.2f}")
                st.progress(total / total_all if total_all else 0)
                st.markdown("**Recent points activity**")
                render_activity(entries, fighter_name)
    live_dashboard()

elif view == "🏆 Leaderboards":
    st.title("🏆 Leaderboards")
    tab_fighters, tab_activity = st.tabs(["Fighter Rankings", "Simulation Activity"])
    with tab_fighters:
        render_roster(state["fighter_roster"])
    with tab_activity:
        ledger = state["points_ledger"]
        if ledger:
            rows = [{"Participant": name, "Total points": points} for name, points in ledger.items()]
            st.dataframe(pd.DataFrame(rows).sort_values("Total points", ascending=False),
                         use_container_width=True, hide_index=True)
        else:
            st.info("No participant points have been recorded yet.")

elif view == "🔒 Admin Control":
    st.title("⚙️ Admin Control")
    st.caption("Private controls for a hypothetical, non-cash simulation.")
    if not admin_is_configured():
        st.error("Admin password is not configured. Add ADMIN_PASSWORD to Streamlit Secrets.")
        st.stop()
    password = st.text_input("Admin password", type="password")
    if password != st.secrets["ADMIN_PASSWORD"]:
        st.info("Enter the admin password to unlock controls.")
        st.stop()
    st.success("Admin controls unlocked for this session.")

    current = load_state()
    entries = current["points_entries"]
    total_pool, house_take, fighter_take, distributable, _ = pool_summary(entries)
    with st.container(border=True):
        st.subheader("Private simulation summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Simulated pool", f"${total_pool:,.2f}")
        c2.metric("Simulated 7% share", f"${house_take:,.2f}")
        c3.metric("Secret 10% Fighter Cut", f"${fighter_take:,.2f}")
        c4.metric("Pool after simulated share", f"${distributable:,.2f}")
        st.caption("Illustrative figures only; no real money, wagers, or payments.")

    with st.expander("✏️ Match setup", expanded=True):
        roster_names = [f.get("Name") for f in current["fighter_roster"]]
        if not roster_names:
            st.warning("Please add fighters to the roster first before setting up a match.")
        else:
            default_a = current["fighter_a"] if current["fighter_a"] in roster_names else roster_names[0]
            default_b = current["fighter_b"] if current["fighter_b"] in roster_names and current["fighter_b"] != default_a else (roster_names[1] if len(roster_names) > 1 else roster_names[0])
            
            with st.form("match_setup"):
                fighter_a = st.selectbox("Red fighter", roster_names, index=roster_names.index(default_a) if default_a in roster_names else 0)
                fighter_b = st.selectbox("Blue fighter", roster_names, index=roster_names.index(default_b) if default_b in roster_names else (1 if len(roster_names) > 1 else 0))
                save_names = st.form_submit_button("Save fighter names")
            if save_names:
                if fighter_a == fighter_b:
                    st.warning("Red and Blue fighters must be different people.")
                else:
                    current["fighter_a"], current["fighter_b"] = fighter_a, fighter_b
                    save_state(current)
                    st.success("Fighter names saved.")
                    st.rerun()

    st.subheader("⏱️ Match clock controls")
    c1, c2, c3 = st.columns(3)
    if c1.button("▶️ Start / Resume", use_container_width=True):
        if current["match_status"] != "FIGHTING":
            current["fight_start_time"] = datetime.now(timezone.utc).isoformat()
            current["match_status"] = "FIGHTING"
            save_state(current)
            st.rerun()
    if c2.button("⏸️ Pause clock", use_container_width=True):
        if current["match_status"] == "FIGHTING":
            current["fight_elapsed_seconds"] = active_elapsed(current)
            current["fight_start_time"] = None
            current["match_status"] = "PAUSED"
            save_state(current)
            st.rerun()
    if c3.button("⏹️ End Match / Calculate Payouts", use_container_width=True):
        st.session_state["show_winner_dialog"] = True
        st.rerun()

    @st.dialog("End match and calculate simulation results")
    def choose_winner_dialog():
        st.write("Select the winner. All pending fictional entries and fighter ranking points will be updated automatically.")
        winner_choice = st.radio(
            "Who won?",
            [current["fighter_a"], current["fighter_b"]],
            key="simulation_winner_choice",
        )
        st.caption("Simulation only — no real money or payments.")
        confirm_col, cancel_col = st.columns(2)
        if confirm_col.button("Confirm winner & calculate", type="primary", use_container_width=True):
            if current["match_status"] == "FIGHTING":
                current["fight_elapsed_seconds"] = active_elapsed(current)
            current["fight_start_time"] = None
            current["match_status"] = "MATCH ENDED"
            current["winner"] = winner_choice
            
            # Update points entries
            for entry in current["points_entries"]:
                entry["result"] = "WIN" if entry.get("target") == winner_choice else "LOSE"
            
            # Update fighter roster points (+25 for winner, -15 for loser)
            loser_choice = current["fighter_b"] if winner_choice == current["fighter_a"] else current["fighter_a"]
            for fighter in current["fighter_roster"]:
                name = fighter.get("Name")
                if name == winner_choice:
                    fighter["Points"] = int(fighter.get("Points", 100)) + 25
                elif name == loser_choice:
                    fighter["Points"] = max(0, int(fighter.get("Points", 100)) - 15)

            save_state(current)
            st.session_state["show_winner_dialog"] = False
            st.rerun()
        if cancel_col.button("Cancel", use_container_width=True):
            st.session_state["show_winner_dialog"] = False
            st.rerun()

    if st.session_state.get("show_winner_dialog", False):
        choose_winner_dialog()
    if st.button("↩️ Reset clock/status"):
        current["match_status"] = "UPCOMING"
        current["winner"] = None
        current["fight_start_time"] = None
        current["fight_elapsed_seconds"] = 0.0
        save_state(current)
        st.rerun()

    st.subheader("👊 Fighter roster")
    with st.expander("Add fighter"):
        with st.form("add_fighter", clear_on_submit=True):
            name = st.text_input("Name")
            grade = st.selectbox("Grade (optional)", ["", "9", "10", "11", "12"])
            height = st.text_input("Height (e.g. 5 ft 10 in)")
            weight = st.text_input("Weight (e.g. 155 lb)")
            points = st.number_input("Starting ranking points", min_value=0, value=100, step=1)
            add_fighter = st.form_submit_button("Add fighter")
        if add_fighter:
            if not name.strip():
                st.warning("Enter a name.")
            elif any(f.get("Name", "").casefold() == name.strip().casefold() for f in current["fighter_roster"]):
                st.warning("That fighter is already on the roster.")
            else:
                current["fighter_roster"].append({
                    "Name": name.strip(), "Points": int(points), "Grade": grade,
                    "Height": height.strip(), "Weight": weight.strip()
                })
                save_state(current)
                st.success("Fighter added.")
                st.rerun()

    if current["fighter_roster"]:
        names = [f.get("Name", "") for f in current["fighter_roster"]]
        with st.expander("Remove fighter"):
            remove_name = st.selectbox("Choose fighter", names)
            if st.button("Remove selected fighter"):
                current["fighter_roster"] = [f for f in current["fighter_roster"] if f.get("Name") != remove_name]
                save_state(current)
                st.rerun()

    st.subheader("🎯 Add simulated entry")
    st.caption("Fictional amounts only. The 7% simulation parameter is fixed in code.")
    with st.form("sim_entry", clear_on_submit=True):
        participant = st.text_input("Participant name")
        target = st.radio("Choose fighter", [current["fighter_a"], current["fighter_b"]], horizontal=True)
        stake = st.number_input("Simulated amount ($)", min_value=0.01, max_value=100000.0, value=10.0, step=1.0)
        result_value = st.selectbox("Simulated result", ["PENDING", "WIN", "LOSE"])
        add_entry = st.form_submit_button("Add simulated entry")
    if add_entry:
        if not participant.strip():
            st.warning("Enter a participant name.")
        else:
            entry = {
                "name": participant.strip(), "target": target, "stake": round(float(stake), 2),
                "result": result_value, "created_at": datetime.now(timezone.utc).isoformat()
            }
            current["points_entries"].append(entry)
            current["points_ledger"][participant.strip()] = int(current["points_ledger"].get(participant.strip(), 0)) + int(stake)
            save_state(current)
            st.success("Simulated entry saved and synced.")
            st.rerun()

    if current["points_entries"]:
        if st.button("Clear simulation activity and ledger", type="secondary"):
            current["points_entries"] = []
            current["points_ledger"] = {}
            save_state(current)
            st.rerun()

elif view == "🗂️ Fighter Profiles":
    st.title("🗂️ Fighter Profiles")
    st.caption("Only publish details you have permission to share.")
    roster = state["fighter_roster"]
    if not roster:
        st.info("No profiles are available yet.")
    else:
        grades = sorted({str(f.get("Grade", "")) for f in roster if f.get("Grade")})
        selected = st.multiselect("Filter by grade", grades, default=grades)
        for fighter in roster:
            grade = str(fighter.get("Grade", ""))
            if grades and grade not in selected:
                continue
            with st.container(border=True):
                st.subheader(f"🏅 {fighter.get('Name', 'Unnamed fighter')}")
                a, b = st.columns(2)
                a.write(f"**Grade:** {grade or 'Not provided'}")
                b.write(f"**Ranking points:** {fighter.get('Points', 0)}")
                c, d = st.columns(2)
                c.write(f"**Height:** {fighter.get('Height') or 'Not provided'}")
                d.write(f"**Weight:** {fighter.get('Weight') or 'Not provided'}")
