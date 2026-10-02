"""Animated celestial entrance and authentication for the Kundli application."""

from __future__ import annotations

import hashlib
import hmac
import base64
from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit_searchbox import st_searchbox

from kundli_complete_app import (
    generate_chart,
    main as saved_kundli_main,
    show_chart,
    show_upcoming_transits,
)
from kundli_streamlit import search_places, selected_datetime


AUTH_USERNAME = "Rutika"
AUTH_SALT = bytes.fromhex("06240b31a34494ce55d48d8a7313fd11")
AUTH_PASSWORD_HASH = bytes.fromhex(
    "33b66c5c355738054d5eddbbd5ab35f4c87030914476a9c7ab94ed8c66b38d4c"
)


def password_matches(candidate: str) -> bool:
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256", candidate.encode("utf-8"), AUTH_SALT, 600_000
    )
    return hmac.compare_digest(candidate_hash, AUTH_PASSWORD_HASH)


def portal_theme(*, wheel: bool = False) -> None:
    wheel_image = ""
    if wheel:
        wheel_path = Path(__file__).with_name("zodiac_wheel.svg")
        wheel_image = base64.b64encode(wheel_path.read_bytes()).decode("ascii")
    wheel_css = """
    div[data-testid="stButton"] {display:flex; justify-content:center; margin:1.4rem 0 1rem}
    div[data-testid="stButton"] > button {
        width:min(68vw,430px) !important; height:min(68vw,430px) !important;
        min-height:280px;border-radius:50% !important;color:transparent !important;font-size:0 !important;
        border:0 !important;background-color:transparent !important;
        background-image:url("data:image/svg+xml;base64,__WHEEL_IMAGE__") !important;
        background-repeat:no-repeat !important;background-position:center !important;background-size:contain !important;
        box-shadow:0 0 38px rgba(42,149,255,.48),0 0 100px rgba(38,72,214,.34) !important;
        animation:celestial-spin 30s linear infinite;
        transition:filter .25s ease, box-shadow .25s ease;
    }
    div[data-testid="stButton"] > button:hover {
        filter:brightness(1.2); box-shadow:0 0 35px #65d8ff,0 0 90px #315cff,inset 0 0 42px #73e4ff !important;
    }
    div[data-testid="stButton"] > button:focus:not(:active) {color:transparent !important}
    @keyframes celestial-spin {to {transform:rotate(360deg)}}
    @media (max-width:640px) {div[data-testid="stButton"] > button {min-height:260px}}
    """.replace("__WHEEL_IMAGE__", wheel_image) if wheel else ""
    st.markdown(f"""
    <style>
    html,body,[data-testid="stAppViewContainer"],.stApp {{
      background:
        radial-gradient(circle at 12% 18%, rgba(255,255,255,.8) 0 1px, transparent 2px),
        radial-gradient(circle at 84% 25%, rgba(111,217,255,.75) 0 1px, transparent 2px),
        radial-gradient(circle at 72% 78%, rgba(255,255,255,.7) 0 1px, transparent 2px),
        radial-gradient(circle at 22% 82%, rgba(96,137,255,.8) 0 1px, transparent 2px),
        radial-gradient(ellipse at 50% 35%, #172762 0%, #090e2a 53%, #030615 100%);
      color:#edf7ff;
    }}
    [data-testid="stHeader"] {{background:transparent}}
    [data-testid="stToolbar"] {{right:1rem}}
    h1,h2,h3,p,label,[data-testid="stCaptionContainer"] {{color:#edf7ff !important}}
    .celestial-kicker {{text-align:center;letter-spacing:.38em;color:#7edcff;font-size:.78rem;font-weight:700}}
    .celestial-title {{text-align:center;font-size:clamp(2rem,5vw,4rem);margin:.2rem 0;color:#f6fbff;
      text-shadow:0 0 18px rgba(93,190,255,.8)}}
    .celestial-copy {{text-align:center;color:#9eb9d8;max-width:620px;margin:0 auto 1rem}}
    div[data-testid="stForm"] {{background:rgba(11,20,57,.78);border:1px solid rgba(104,190,255,.35);
      border-radius:24px;padding:1.25rem;box-shadow:0 20px 70px rgba(0,0,0,.35),inset 0 0 28px rgba(57,127,255,.08)}}
    div[data-baseweb="input"] > div {{background:#f7f9fd !important;border-color:#78b8e9 !important}}
    input {{color:#111827 !important;-webkit-text-fill-color:#111827 !important;caret-color:#111827 !important}}
    input::placeholder {{color:#697386 !important;-webkit-text-fill-color:#697386 !important}}
    button[kind="primaryFormSubmit"] {{background:linear-gradient(90deg,#235bc7,#19a4d9) !important;border:0 !important}}
    {wheel_css}
    </style>
    """, unsafe_allow_html=True)


def authenticate() -> bool:
    """Show a login gate and return True only for an authenticated session."""

    if st.session_state.get("authenticated"):
        return True

    if not st.session_state.get("show_login"):
        st.set_page_config(page_title="Celestial Kundli", page_icon="✦", layout="centered")
        portal_theme(wheel=True)
        st.markdown('<div class="celestial-kicker">VEDIC ASTROLOGY</div>', unsafe_allow_html=True)
        st.markdown('<div class="celestial-title">Your Celestial Portal</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="celestial-copy">Click the rotating zodiac wheel to enter your private Kundli workspace.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Open zodiac portal", key="open_celestial_portal", type="primary"):
            st.session_state["show_login"] = True
            st.rerun()
        st.markdown('<div class="celestial-copy">✦ Aligning planets · Mapping possibilities · Preserving tradition ✦</div>', unsafe_allow_html=True)
        return False

    st.set_page_config(page_title="Kundli Login", page_icon="🔐", layout="centered")
    portal_theme()
    st.markdown('<div class="celestial-kicker">PRIVATE OBSERVATORY</div>', unsafe_allow_html=True)
    st.markdown('<div class="celestial-title">Welcome Back</div>', unsafe_allow_html=True)
    st.markdown('<div class="celestial-copy">Sign in to access saved Kundlis and create a new chart.</div>', unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button(
            "Sign in", type="primary", use_container_width=True
        )
    if submitted:
        valid_user = hmac.compare_digest(username.strip(), AUTH_USERNAME)
        if valid_user and password_matches(password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect username or password.")
    return False


def main() -> None:
    st.set_page_config(page_title="Kundli Generator", page_icon="✨", layout="wide")
    st.title("✨ Kundli Generator")
    st.caption("Create a North Indian Vedic Kundli from your birth details")
    st.info("Enter the birth time accurately; a small difference can change the ascendant.")

    with st.container(border=True):
        name_column, gender_column = st.columns([3, 2])
        with name_column:
            name = st.text_input("NAME *", placeholder="Enter full name")
        with gender_column:
            st.segmented_control(
                "GENDER", options=("Male", "Female"), default="Male",
                selection_mode="single",
            )

        local_birth = selected_datetime()
        st.caption(f"Selected: {local_birth:%d %B %Y, %I:%M %p}")
        selected_place = st_searchbox(
            search_places,
            key="public_app_birthplace",
            placeholder="Type a city, state, and country",
            label="BIRTH PLACE *",
            help="Type at least three characters and select the correct suggested address.",
            debounce=500,
            clear_on_submit=False,
        )
        create_kundli = st.button(
            "Generate Kundli →", type="primary", use_container_width=True
        )

    if create_kundli:
        if not name.strip():
            st.error("Please enter your name.")
        elif not selected_place:
            st.error("Please select a birthplace from the suggestions.")
        else:
            try:
                with st.spinner("Calculating your Kundli..."):
                    session_token = st.session_state.setdefault(
                        "chart_file_token", uuid4().hex
                    )
                    chart = generate_chart(
                        name.strip(), local_birth, selected_place,
                        file_token=session_token, save_latest=False,
                    )
                chart["input_place"] = selected_place
                st.session_state["public_chart"] = chart
                st.success("Your Kundli was created successfully.")
            except Exception as error:
                st.error(f"Could not create the Kundli: {error}")

    chart = st.session_state.get("public_chart")
    if chart:
        chart_tab, transit_tab = st.tabs(("Kundli chart", "Upcoming transits"))
        with chart_tab:
            show_chart(chart)
        with transit_tab:
            show_upcoming_transits(chart)

    st.caption(
        "Birth details are not added to the saved-profile list. Educational use only; "
        "astrology is not scientifically validated."
    )


if __name__ == "__main__":
    # The authenticated deployment uses the complete non-RAG interface,
    # including the saved Kundli list stored in saved_kundlis.json.
    if authenticate():
        saved_kundli_main()
