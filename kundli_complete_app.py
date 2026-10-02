"""Lightweight Streamlit Kundli generator for local use and public hosting.

Run:
    streamlit run kundli_complete_app.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from streamlit_searchbox import st_searchbox

from kundli import (
    SIGN_NAMES, BodyPosition, calculate_chart, draw_kundli, find_shadashtak_pairs,
    natal_house_lord, resolve_place, safe_filename, to_julian_day,
)
from kundli_streamlit import search_places, selected_datetime
from saved_kundlis import delete_profile, load_profiles, upsert_profile


ROOT = Path(__file__).resolve().parent


def make_chart_data(
    name: str,
    local_birth,
    utc_birth,
    address: str,
    latitude: float,
    longitude: float,
    timezone_name: str,
    ascendant: float,
    positions,
    image_path: Path,
) -> dict:
    """Create a JSON-safe representation of the calculated chart."""

    planet_data = [
        {
            "name": planet.full_name,
            "sign": SIGN_NAMES[planet.sign],
            "degree": round(planet.degree, 4),
            "house": planet.house,
            "retrograde": planet.retrograde,
        }
        for planet in positions
    ]
    return {
        "name": name,
        "birth_local": local_birth.isoformat(),
        "birth_utc": utc_birth.isoformat(),
        "place": address,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone_name,
        "ayanamsa": "Lahiri",
        "house_system": "Whole sign",
        "ascendant": {
            "sign": SIGN_NAMES[int(ascendant // 30)],
            "degree": round(ascendant % 30, 4),
        },
        "planets": planet_data,
        "shadashtak_pairs": find_shadashtak_pairs(planet_data),
        "chart_image": str(image_path),
    }


def generate_chart(
    name: str,
    local_birth,
    selected_place: str,
    *,
    file_token: str | None = None,
    save_latest: bool = True,
) -> dict:
    """Calculate and render a Kundli, returning its structured data."""

    address, latitude, longitude, timezone_name = resolve_place(selected_place)
    utc_birth, julian_day = to_julian_day(local_birth, timezone_name)
    ascendant, positions = calculate_chart(julian_day, latitude, longitude)

    file_stem = safe_filename(file_token or name)
    image_path = ROOT / f"kundli_{file_stem}.png"
    local_offset = local_birth.replace(tzinfo=ZoneInfo(timezone_name)).strftime("UTC%z")
    caption = f"{local_birth:%d-%m-%Y %I:%M %p} ({timezone_name}, {local_offset})"
    draw_kundli(name, caption, address, ascendant, positions, image_path)

    chart = make_chart_data(
        name,
        local_birth,
        utc_birth,
        address,
        latitude,
        longitude,
        timezone_name,
        ascendant,
        positions,
        image_path,
    )

    # Calculate today's sidereal planet positions, but place them in houses
    # counted from the user's natal ascendant (not the current ascendant).
    current_local = datetime.now(ZoneInfo(timezone_name)).replace(second=0, microsecond=0)
    current_naive = current_local.replace(tzinfo=None)
    current_utc, current_julian_day = to_julian_day(current_naive, timezone_name)
    _current_ascendant, current_positions = calculate_chart(
        current_julian_day, latitude, longitude
    )
    natal_ascendant_sign = int(ascendant // 30)
    anchored_positions = [
        BodyPosition(
            short_name=planet.short_name,
            full_name=planet.full_name,
            longitude=planet.longitude,
            sign=planet.sign,
            degree=planet.degree,
            house=((planet.sign - natal_ascendant_sign) % 12) + 1,
            retrograde=planet.retrograde,
        )
        for planet in current_positions
    ]
    transit_image_path = ROOT / f"kundli_{file_stem}_current.png"
    transit_caption = f"Current positions: {current_local:%d-%m-%Y %I:%M %p} ({timezone_name})"
    draw_kundli(
        f"{name} — Current Transits",
        transit_caption,
        f"Houses anchored to natal ascendant: {SIGN_NAMES[natal_ascendant_sign]}",
        ascendant,
        anchored_positions,
        transit_image_path,
    )
    chart["current_transits"] = make_chart_data(
        name,
        current_naive,
        current_utc,
        address,
        latitude,
        longitude,
        timezone_name,
        ascendant,
        anchored_positions,
        transit_image_path,
    )
    chart["current_transits"]["calculated_at"] = current_local.isoformat()
    chart["current_transits"]["houses_anchored_to_natal_ascendant"] = True
    if save_latest:
        (ROOT / "latest_kundli.json").write_text(
            json.dumps(chart, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return chart


def show_chart(chart: dict) -> None:
    image_path = Path(chart["chart_image"])
    transit = chart.get("current_transits")
    transit_image_path = Path(transit["chart_image"]) if transit else None

    natal_column, transit_column = st.columns(2)
    with natal_column:
        st.subheader("Birth Kundli")
        st.image(str(image_path), caption=f"Kundli for {chart['name']}", use_container_width=True)
        with image_path.open("rb") as image_file:
            st.download_button(
                "Download birth Kundli",
                image_file.read(),
                file_name=image_path.name,
                mime="image/png",
                use_container_width=True,
            )
    with transit_column:
        st.subheader("Current Planet Positions")
        if transit_image_path:
            st.image(
                str(transit_image_path),
                caption="Current planets in houses from your birth ascendant",
                use_container_width=True,
            )
            st.caption(
                f"Calculated at {transit['calculated_at']} · Ascendant kept as "
                f"{chart['ascendant']['sign']} {chart['ascendant']['degree']:.2f}°"
            )
            with transit_image_path.open("rb") as image_file:
                st.download_button(
                    "Download current-position Kundli",
                    image_file.read(),
                    file_name=transit_image_path.name,
                    mime="image/png",
                    use_container_width=True,
                )

    ascendant = chart["ascendant"]
    col1, col2 = st.columns(2)
    col1.metric("Ascendant", f"{ascendant['sign']} {ascendant['degree']:.2f}°")
    col2.metric("Time zone", chart["timezone"])
    st.write(f"**Resolved birthplace:** {chart['place']}")

    rows = [
        {
            "Planet": planet["name"],
            "Sign": planet["sign"],
            "Degree": f"{planet['degree']:.2f}°",
            "House": planet["house"],
            "Motion": "Retrograde" if planet["retrograde"] else "Direct",
        }
        for planet in chart["planets"]
    ]
    with st.expander("Planetary positions"):
        st.dataframe(rows, hide_index=True, use_container_width=True)

    if transit:
        transit_rows = [
            {
                "Planet": planet["name"],
                "Sign": planet["sign"],
                "Degree": f"{planet['degree']:.2f}°",
                "Natal House": planet["house"],
                "Motion": "Retrograde" if planet["retrograde"] else "Direct",
            }
            for planet in transit["planets"]
        ]
        with st.expander("Current planetary positions"):
            st.dataframe(transit_rows, hide_index=True, use_container_width=True)

    st.subheader("Shadashtak relationships (6–8)")
    pairs = chart.get("shadashtak_pairs", [])
    if pairs:
        for pair in pairs:
            st.markdown(
                f"- **{pair['first']} and {pair['second']}** — houses "
                f"{pair['first_house']} and {pair['second_house']} "
                f"({pair['relationship']} relationship)"
            )
    else:
        st.write("No Shadashtak relationship is present among the nine classical grahas.")


def show_upcoming_transits(chart: dict) -> None:
    """Show current 6–12 and 8–12 lord transit combinations."""

    transit = chart.get("current_transits")
    if not transit:
        st.info("Generate the Kundli again to calculate current transits.")
        return

    ascendant_sign = chart["ascendant"]["sign"]
    lords = {
        6: natal_house_lord(ascendant_sign, 6),
        8: natal_house_lord(ascendant_sign, 8),
        12: natal_house_lord(ascendant_sign, 12),
    }
    current_houses = {
        planet["name"]: planet["house"] for planet in transit["planets"]
    }

    st.header("Upcoming Transits")
    st.caption(
        "Checked from the current sidereal planet positions against the houses of "
        "the original birth ascendant."
    )
    lord_columns = st.columns(3)
    for column, house in zip(lord_columns, (6, 8, 12)):
        column.metric(f"{house}th house lord", lords[house])

    sixth_twelfth = (
        current_houses.get(lords[6]) == 12
        or current_houses.get(lords[12]) == 6
    )
    eighth_twelfth = (
        current_houses.get(lords[8]) == 12
        or current_houses.get(lords[12]) == 8
    )

    if sixth_twelfth:
        st.warning(
            f"The 6th house lord ({lords[6]}) is transiting the 12th house, or the "
            f"12th house lord ({lords[12]}) is transiting the 6th house. "
            "There are possibilities of illness and hospitalization."
        )
    if eighth_twelfth:
        st.warning(
            f"The 8th house lord ({lords[8]}) is transiting the 12th house, or the "
            f"12th house lord ({lords[12]}) is transiting the 8th house. "
            "There are possibilities of illness and expenditure due to hospitalization."
        )
    if not sixth_twelfth and not eighth_twelfth:
        st.success(
            "Neither the specified 6–12 nor 8–12 house-lord transit is active "
            "at the current calculation time."
        )

    st.subheader("Current lord positions")
    for house in (6, 8, 12):
        lord = lords[house]
        st.write(f"- **{house}th house lord {lord}:** currently in house {current_houses[lord]}")
    st.caption(
        "This is a traditional astrological interpretation, not a medical prediction. "
        "Seek a qualified medical professional for health concerns."
    )


def main() -> None:
    st.set_page_config(page_title="Celestial Kundli", page_icon="✦", layout="wide")
    if st.session_state.get("authenticated"):
        with st.sidebar:
            st.success("Signed in")
            if st.button("Sign out", use_container_width=True):
                st.session_state.clear()
                st.rerun()
    st.markdown('<div class="app-kicker">PRIVATE VEDIC OBSERVATORY</div>', unsafe_allow_html=True)
    st.title("✦ Celestial Kundli")
    st.caption("Create a North Indian Vedic birth chart and explore current planetary movements")
    st.info("Enter the birth time accurately; a small difference can change the ascendant.")

    profiles = load_profiles()
    profile_by_id = {profile["id"]: profile for profile in profiles}
    for key, value in {"birth_day": 22, "birth_month": 6, "birth_year": 1998,
                       "birth_hour": 2, "birth_minute": 30, "birth_period": "AM",
                       "profile_name": "Rushabh", "profile_gender": "M",
                       "selected_saved_kundli": "__new__"}.items():
        st.session_state.setdefault(key, value)

    def apply_profile(profile_id: str) -> None:
        profile = profile_by_id.get(profile_id)
        if not profile:
            return
        hour_24 = profile["hour"]
        st.session_state["selected_saved_kundli"] = profile_id
        st.session_state["profile_name"] = profile["name"]
        st.session_state["profile_gender"] = profile.get("gender") or "M"
        st.session_state["birth_day"] = profile["day"]
        st.session_state["birth_month"] = profile["month"]
        st.session_state["birth_year"] = profile["year"]
        st.session_state["birth_hour"] = hour_24 % 12 or 12
        st.session_state["birth_minute"] = profile["minute"]
        st.session_state["birth_period"] = "PM" if hour_24 >= 12 else "AM"

    def start_new_profile() -> None:
        st.session_state["selected_saved_kundli"] = "__new__"
        st.session_state["profile_name"] = ""
        st.session_state["profile_gender"] = "M"

    def remove_profile(profile_id: str) -> None:
        delete_profile(profile_id)
        if st.session_state.get("selected_saved_kundli") == profile_id:
            start_new_profile()

    st.markdown("""
        <style>
        :root {color-scheme:dark}
        html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"],.stApp {
            background:
              radial-gradient(circle at 8% 12%, rgba(255,255,255,.65) 0 1px, transparent 2px),
              radial-gradient(circle at 91% 22%, rgba(98,210,255,.6) 0 1px, transparent 2px),
              radial-gradient(circle at 74% 82%, rgba(255,255,255,.55) 0 1px, transparent 2px),
              radial-gradient(ellipse at 50% 0%, #17285f 0%, #090e29 48%, #040716 100%) !important;
            color:#eaf6ff;
        }
        [data-testid="stMainBlockContainer"] {padding-top:4.25rem}
        [data-testid="stHeader"] {background:rgba(3,6,21,.72) !important;backdrop-filter:blur(10px)}
        section[data-testid="stSidebar"] {background:#070b1d !important;border-right:1px solid rgba(83,175,255,.22)}
        section[data-testid="stSidebar"] > div {background:linear-gradient(180deg,#0a1230 0%,#050817 100%) !important}
        section[data-testid="stSidebar"] [data-testid="stAlert"] {background:rgba(14,75,92,.52) !important}
        h1 {color:#9ee9ff !important;text-shadow:0 0 24px rgba(55,172,255,.45)}
        h2,h3 {color:#7fdcff !important}
        p,label,[data-testid="stCaptionContainer"],.stMarkdown {color:#c5dcf0 !important}
        .app-kicker {letter-spacing:.32em;color:#6fd9ff;font-size:.72rem;font-weight:800;margin-bottom:-.5rem}
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius:24px;background:linear-gradient(145deg,rgba(15,29,72,.94),rgba(5,12,37,.94)) !important;
            border:1px solid rgba(91,195,255,.42) !important;
            box-shadow:0 16px 55px rgba(0,0,0,.42),inset 0 0 35px rgba(39,112,255,.08);
        }
        div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
            background:#0b173b !important;border-color:#356ab3 !important;color:#bcecff !important;
        }
        input {color:#bcecff !important;-webkit-text-fill-color:#bcecff !important;caret-color:#79dcff !important}
        input::placeholder {color:#7398bb !important;-webkit-text-fill-color:#7398bb !important}
        div[data-baseweb="select"] span,div[data-baseweb="select"] input {color:#bcecff !important}
        div[data-baseweb="popover"],ul[role="listbox"] {background:#0a1637 !important;color:#d7f3ff !important}
        li[role="option"] {color:#c4eaff !important}
        li[role="option"]:hover {background:#17356c !important}
        div[data-testid="stSegmentedControl"] {background:#091534;border-radius:12px;padding:3px}
        div[data-testid="stSegmentedControl"] label {color:#aee8ff !important}
        button[kind="primary"] {background:linear-gradient(90deg,#265bc7,#159ed3) !important;
            color:white !important;border:1px solid #66d8ff !important;box-shadow:0 0 22px rgba(48,154,255,.28)}
        button[kind="secondary"] {background:rgba(12,29,69,.82) !important;color:#dff5ff !important;
            border-color:rgba(99,184,255,.35) !important}
        button[kind="secondary"] p,button[kind="primary"] p {color:inherit !important}
        [data-testid="stAlert"] {background:rgba(18,46,93,.78) !important;color:#eaf6ff !important;border-color:#2d72bd !important}
        [data-testid="stTabs"] button {color:#9edfff !important}
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {background:#60d7ff !important}
        hr {border-color:rgba(91,174,226,.20) !important}
        [data-testid="stDataFrame"] {border:1px solid rgba(80,177,239,.3);border-radius:14px;overflow:hidden}
        .saved-avatar {width:42px;height:42px;border-radius:50%;background:linear-gradient(145deg,#315fc5,#19a6cf);color:white;
            display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;margin-top:7px}
        .saved-count {color:#8fb0cd;font-size:14px;margin-top:-8px;margin-bottom:8px}
        </style>
    """, unsafe_allow_html=True)

    editor_column, saved_column = st.columns(2, gap="large")
    with editor_column:
        with st.container(border=True):
            heading_column, new_column = st.columns([3, 1])
            heading_column.subheader("New Kundli")
            new_column.button("＋ New", on_click=start_new_profile, use_container_width=True)

            name_column, gender_column = st.columns([3, 2])
            with name_column:
                name = st.text_input("NAME *", placeholder="Enter full name", key="profile_name")
            with gender_column:
                gender = st.segmented_control(
                    "GENDER *", options=("M", "F"),
                    format_func=lambda value: "Male" if value == "M" else "Female",
                    key="profile_gender", selection_mode="single",
                )

            local_birth = selected_datetime()
            st.caption(f"Selected: {local_birth:%d %B %Y, %I:%M %p}")
            selected_profile_id = st.session_state["selected_saved_kundli"]
            selected_profile = profile_by_id.get(selected_profile_id)
            if selected_profile:
                selected_place = selected_profile["place"]
                st.text_input("BIRTH PLACE *", value=selected_place, disabled=True)
            else:
                selected_place = st_searchbox(
                    search_places,
                    key="complete_app_birthplace",
                    placeholder="Type a city, state, and country",
                    label="BIRTH PLACE *",
                    help="Type at least three characters and select the correct suggested address.",
                    debounce=500,
                    clear_on_submit=False,
                )

            create_kundli = st.button(
                "Generate Kundli  →", type="primary", use_container_width=True
            )

    with saved_column:
        with st.container(border=True):
            st.subheader("Saved Kundli")
            search_name = st.text_input(
                "Search kundli by name", placeholder="🔍  Search kundli by name",
                label_visibility="collapsed", key="saved_kundli_search",
            )
            filtered_profiles = [
                profile for profile in profiles
                if search_name.strip().casefold() in profile["name"].casefold()
            ]
            st.markdown(
                f'<div class="saved-count">Recently Opened · {len(filtered_profiles)} saved</div>',
                unsafe_allow_html=True,
            )
            with st.container(height=475, border=False):
                if not filtered_profiles:
                    st.info("No saved Kundli matches this name.")
                for profile in filtered_profiles:
                    avatar_column, detail_column, delete_column = st.columns([1, 7, 1])
                    avatar_column.markdown(
                        f'<div class="saved-avatar">{profile["name"][0].upper()}</div>',
                        unsafe_allow_html=True,
                    )
                    hour = profile["hour"] % 12 or 12
                    period = "PM" if profile["hour"] >= 12 else "AM"
                    saved_birth_date = datetime(
                        profile["year"], profile["month"], profile["day"]
                    ).strftime("%d %b, %Y")
                    detail_column.button(
                        f"{profile['name']}, {profile.get('gender', '')}\n\n"
                        f"{saved_birth_date} "
                        f"{hour:02d}:{profile['minute']:02d} {period}\n\n{profile['place']}",
                        key=f"open_{profile['id']}", on_click=apply_profile,
                        args=(profile["id"],), use_container_width=True,
                    )
                    delete_column.button(
                        "🗑", key=f"delete_{profile['id']}", help="Delete saved Kundli",
                        on_click=remove_profile, args=(profile["id"],),
                    )
                    st.divider()

    if create_kundli:
            if not name.strip():
                st.error("Please enter your name.")
            elif not selected_place:
                st.error("Please select a birthplace from the suggestions.")
            else:
                try:
                    with st.spinner("Calculating your Kundli..."):
                        chart = generate_chart(name.strip(), local_birth, selected_place)
                    st.session_state["complete_chart"] = chart
                    chart["input_place"] = selected_place
                    upsert_profile({
                        "id": selected_profile_id if selected_profile else "",
                        "name": name.strip(),
                        "day": local_birth.day,
                        "month": local_birth.month,
                        "year": local_birth.year,
                        "hour": local_birth.hour,
                        "min": local_birth.minute,
                        "gender": gender or "",
                        "place": selected_place,
                        "source": "Astrotalk" if selected_profile else "Local",
                    })
                    st.success("Your Kundli was created successfully and saved locally.")
                except Exception as error:
                    st.error(f"Could not create the Kundli: {error}")

    chart = st.session_state.get("complete_chart")
    if chart and (chart["name"] != name.strip() or chart["birth_local"] != local_birth.isoformat()
                  or chart.get("input_place") != selected_place):
        st.info("Birth details changed. Click Create my Kundli to update the chart and interpretation.")
        chart = None
    if chart:
        chart_tab, transit_tab = st.tabs(("Kundli chart", "Upcoming transits"))
        with chart_tab:
            show_chart(chart)
        with transit_tab:
            show_upcoming_transits(chart)
    st.caption(
        "Educational use only. Astrology is not scientifically validated and should "
        "not replace medical, legal, or financial advice."
    )


if __name__ == "__main__":
    main()
