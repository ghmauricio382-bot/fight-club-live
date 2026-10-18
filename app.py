import streamlit as st
from supabase import create_client

st.set_page_config(page_title="FightClub Live", page_icon="🥊", layout="wide")

@st.cache_resource
def connect_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

st.title("🥊 FightClub Live")

try:
    supabase = connect_supabase()

    @st.fragment(run_every=2)
    def live_dashboard():
        result = (
            supabase.table("match_state")
            .select("fighter_a, fighter_b, match_status")
            .eq("id", 1)
            .single()
            .execute()
        )
        match = result.data

        st.subheader("LIVE MATCH")
        left, right = st.columns(2)
        left.metric("🔴 Fighter 1", match["fighter_a"])
        right.metric("🔵 Fighter 2", match["fighter_b"])
        st.info(f"Match status: {match['match_status']}")

    live_dashboard()

except Exception as e:
    st.error("Connection setup needed. Check your Supabase secrets.")
    st.caption(str(e))
