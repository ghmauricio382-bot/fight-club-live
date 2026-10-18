import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from supabase import create_client

# FightClub Live — shared, Supabase-backed event dashboard.
# This version uses NON-MONEY points only. It does not process wagers or payouts.

st.set_page_config(page_title="FightClub Live", page_icon="🥊", layout="wide")

DEFAULT_STATE = {
    "fighter_a": "Marcus",
    "fighter_b": "Leo",
    "match_status": "UPCOMING",
    "fight_start_time": None,
    "fighter_roster": [],
    "points_entries": [],
    "points_ledger": {},
}


@st.cache_resource
def get_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])


def load_state():
    result = (
        get_supabase()
        .table("match_state")
        .select("*")
        .eq("id", 1)
        .single()
        .execute()
    )
    row = result.data or {}
    state = DEFAULT_STATE.copy()
    state.update({key: row.get(key) for key in DEFAULT_STATE if key in row})
    # Keep JSONB columns robust if they are null.
    state["fighter_roster"] = state.get("fighter_roster") or []
    state["points_entries"] = state.get("points_entries") or []
    state["points_ledger"] = state.get("points_ledger") or {}
    return state


def save_state(state):
    payload = {
        "fighter_a": state["fighter_a"],
        "fighter_b": state["fighter_b"],
        "match_status": state["match_status"],
        "fight_start_time": state["fight_start_time"],
        "fighter_roster": state["fighter_roster"],
        "points_entries": state["points_entries"],
        "points_ledger": state["points_ledger"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_supabase().table("match_state").update(payload).eq("id", 1).execute()


def admin_is_configured():
    return bool(st.secrets.get("ADMIN_PASSWORD", ""))


def elapsed_seconds(start_time):
    if not start_time:
        return 0.0
    try:
        parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
    except (ValueError, TypeError, AttributeError):
        return 0.0


def format_clock(seconds):
    minutes = int(seconds // 60)
    whole_seconds = int(seconds % 60)
    tenths = int((seconds * 10) % 10)
    return f"{minutes:02d}:{whole_seconds:02d}.{tenths}"


def render_roster(roster):
    if not roster:
        st.info("No fighters have been added yet.")
        return
    df = pd.DataFrame(roster)
    if "Points" in df.columns:
        df = df.sort_values("Points", ascending=False)
    columns = [c for c in ["Name", "Points", "Grade"] if c in df.columns]
    st.dataframe(df[columns] if columns else df, use_container_width=True, hide_index=True)


st.sidebar.title("🥊 FightClub Live")
view = st.sidebar.radio(
    "Navigate",
    [
        "⚡ Live Public Dashboard",
        "🏆 Leaderboards",
        "🔒 Admin Control",
        "🗂️ Fighter Profiles",
    ],
)

try:
    state = load_state()
except Exception as exc:
    st.error("Could not load the shared Supabase match data.")
    st.caption(
        "Check SUPABASE_URL, SUPABASE_SECRET_KEY, and that the match_state table has "
        "the extra JSONB columns listed in the setup instructions."
    )
    st.stop()


if view == "⚡ Live Public Dashboard":
    st.title("🥊 FightClub Live")
    st.caption("Live event dashboard · updates every 2 seconds")

    @st.fragment(run_every=2)
    def live_dashboard():
        current = load_state()
        st.write(f"**Current status:** {current['match_status']}")
        clock_value = (
            format_clock(elapsed_seconds(current["fight_start_time"]))
            if current["match_status"] == "FIGHTING"
            else (
                format_clock(elapsed_seconds(current["fight_start_time"]))
                if current["fight_start_time"]
                else "00:00.0"
            )
        )
        left, right = st.columns(2)
        left.metric("⏱️ Official fight clock", clock_value)
        right.metric("🏆 Total event points", sum(
            int(item.get("points", 0)) for item in current["points_entries"]
        ))

        st.divider()
        red, blue = st.columns(2)
        entries = current["points_entries"]
        for col, key, color in [
            (red, "fighter_a", "🔴"),
            (blue, "fighter_b", "🔵"),
        ]:
            fighter_name = current[key]
            fighter_points = sum(
                int(item.get("points", 0))
                for item in entries
                if item.get("target") == fighter_name
            )
            total_points = sum(int(item.get("points", 0)) for item in entries)
            pct = fighter_points / total_points if total_points else 0
            with col:
                st.subheader(f"{color} {fighter_name}")
                st.metric("Points assigned", fighter_points)
                st.progress(pct)
                st.markdown("**Recent points activity**")
                matched = [item for item in entries if item.get("target") == fighter_name]
                if not matched:
                    st.caption("No points activity yet.")
                for item in reversed(matched[-10:]):
                    st.write(
                        f"• **{item.get('name', 'Participant')}** — "
                        f"{int(item.get('points', 0))} points"
                    )

    live_dashboard()


elif view == "🏆 Leaderboards":
    st.title("🏆 Leaderboards")
    tab_fighters, tab_points = st.tabs(["Fighter Rankings", "Points Activity"])

    with tab_fighters:
        render_roster(state["fighter_roster"])

    with tab_points:
        ledger = state["points_ledger"]
        if ledger:
            rows = [{"Participant": name, "Total points": points} for name, points in ledger.items()]
            df = pd.DataFrame(rows).sort_values("Total points", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No participant points have been recorded yet.")


elif view == "🔒 Admin Control":
    st.title("⚙️ Admin Control")
    if not admin_is_configured():
        st.error("Admin password is not configured.")
        st.info("Add ADMIN_PASSWORD to your Streamlit Secrets before using admin controls.")
        st.stop()

    password = st.text_input("Admin password", type="password")
    if password != st.secrets["ADMIN_PASSWORD"]:
        st.info("Enter the admin password to unlock controls.")
        st.stop()

    st.success("Admin controls unlocked for this session.")

    with st.expander("✏️ Match setup", expanded=True):
        with st.form("match_setup"):
            fighter_a = st.text_input("Red fighter", value=state["fighter_a"])
            fighter_b = st.text_input("Blue fighter", value=state["fighter_b"])
            save_names = st.form_submit_button("Save fighter names")
        if save_names:
            if not fighter_a.strip() or not fighter_b.strip():
                st.warning("Enter both fighter names.")
            elif fighter_a.strip() == fighter_b.strip():
                st.warning("Choose two different fighter names.")
            else:
                state["fighter_a"] = fighter_a.strip()
                state["fighter_b"] = fighter_b.strip()
                save_state(state)
                st.success("Fighter names saved for every viewer.")
                st.rerun()

    st.subheader("⏱️ Match controls")
    c1, c2, c3 = st.columns(3)
    if c1.button("▶️ Start / Resume", use_container_width=True):
        if state["match_status"] != "FIGHTING":
            if not state["fight_start_time"] or state["match_status"] == "UPCOMING":
                state["fight_start_time"] = datetime.now(timezone.utc).isoformat()
            state["match_status"] = "FIGHTING"
            save_state(state)
            st.rerun()
    if c2.button("⏹️ End match", use_container_width=True):
        state["match_status"] = "MATCH ENDED"
        save_state(state)
        st.rerun()
    if c3.button("↩️ Reset match clock/status", use_container_width=True):
        state["match_status"] = "UPCOMING"
        state["fight_start_time"] = None
        save_state(state)
        st.rerun()

    st.subheader("👊 Fighter roster")
    with st.expander("Add fighter"):
        with st.form("add_fighter", clear_on_submit=True):
            name = st.text_input("Name")
            grade = st.selectbox("Grade (optional)", ["", "9", "10", "11", "12"])
            points = st.number_input("Starting ranking points", min_value=0, value=100, step=1)
            add_fighter = st.form_submit_button("Add fighter")
        if add_fighter:
            if not name.strip():
                st.warning("Enter a name.")
            elif any(f.get("Name", "").casefold() == name.strip().casefold() for f in state["fighter_roster"]):
                st.warning("That fighter is already on the roster.")
            else:
                fighter = {"Name": name.strip(), "Points": int(points)}
                if grade:
                    fighter["Grade"] = grade
                state["fighter_roster"].append(fighter)
                save_state(state)
                st.success("Fighter added.")
                st.rerun()

    if state["fighter_roster"]:
        names = [f.get("Name", "") for f in state["fighter_roster"]]
        with st.expander("Remove fighter"):
            remove_name = st.selectbox("Choose fighter", names)
            if st.button("Remove selected fighter"):
                state["fighter_roster"] = [
                    f for f in state["fighter_roster"] if f.get("Name") != remove_name
                ]
                save_state(state)
                st.rerun()

    st.subheader("🎯 Record non-money event points")
    st.caption("These are scoreboard points only, not cash bets or redeemable balances.")
    with st.form("points_entry", clear_on_submit=True):
        participant = st.text_input("Participant name")
        target = st.radio("Choose fighter", [state["fighter_a"], state["fighter_b"]], horizontal=True)
        points_value = st.number_input("Points", min_value=1, max_value=1000, value=10, step=1)
        record_points = st.form_submit_button("Record points")
    if record_points:
        if not participant.strip():
            st.warning("Enter a participant name.")
        else:
            entry = {
                "name": participant.strip(),
                "target": target,
                "points": int(points_value),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            state["points_entries"].append(entry)
            state["points_ledger"][participant.strip()] = int(
                state["points_ledger"].get(participant.strip(), 0)
            ) + int(points_value)
            save_state(state)
            st.success("Points recorded and synced.")
            st.rerun()

    if st.button("Clear points activity and ledger", type="secondary"):
        state["points_entries"] = []
        state["points_ledger"] = {}
        save_state(state)
        st.rerun()


elif view == "🗂️ Fighter Profiles":
    st.title("🗂️ Fighter Profiles")
    st.caption("Only add information you have permission to publish.")
    roster = state["fighter_roster"]
    if not roster:
        st.info("No profiles are available yet.")
    else:
        grade_options = sorted({str(f.get("Grade", "")) for f in roster if f.get("Grade")})
        selected_grades = st.multiselect("Filter by grade", grade_options, default=grade_options)
        for fighter in roster:
            grade = str(fighter.get("Grade", ""))
            if grade_options and grade not in selected_grades:
                continue
            with st.container(border=True):
                st.subheader(f"🏅 {fighter.get('Name', 'Unnamed fighter')}")
                c1, c2 = st.columns(2)
                c1.write(f"**Grade:** {grade or 'Not provided'}")
                c2.write(f"**Ranking points:** {fighter.get('Points', 0)}")
                # Avoid collecting or publicly displaying age, height, or weight by default.
