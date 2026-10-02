"""Streamlit user interface for the Kundli calculator.

Run:
    streamlit run kundli_streamlit.py
"""

from __future__ import annotations

import calendar
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim
from streamlit_searchbox import st_searchbox

from kundli import (
    SIGN_NAMES,
    calculate_chart,
    draw_kundli,
    resolve_place,
    safe_filename,
    to_julian_day,
)


@st.cache_data(ttl=86_400, show_spinner=False)
def search_places(search_term: str) -> list[tuple[str, str]]:
    """Return matching addresses as (visible label, selected value) tuples."""

    if len(search_term.strip()) < 3:
        return []

    geocoder = Nominatim(user_agent="educational-kundli-streamlit-app", timeout=10)
    try:
        results = geocoder.geocode(
            search_term,
            exactly_one=False,
            limit=7,
            addressdetails=True,
        )
    except GeocoderServiceError:
        return []

    if not results:
        return []
    return [(location.address, location.address) for location in results]


def selected_datetime() -> datetime:
    """Build a valid local datetime from the date and 12-hour controls."""

    date_col, month_col, year_col = st.columns(3)
    with month_col:
        month = st.selectbox(
            "Month",
            range(1, 13),
            index=0,
            format_func=lambda value: calendar.month_name[value],
            key="birth_month",
        )
    with year_col:
        current_year = datetime.now().year
        years = list(range(current_year, 1899, -1))
        year = st.selectbox("Year", years, index=years.index(2000), key="birth_year")
    with date_col:
        maximum_day = calendar.monthrange(year, month)[1]
        if st.session_state.get("birth_day", 1) > maximum_day:
            st.session_state["birth_day"] = maximum_day
        day = st.selectbox("Day", range(1, maximum_day + 1), index=0, key="birth_day")

    st.markdown("**Time of birth**")
    hour_col, minute_col, period_col = st.columns(3)
    with hour_col:
        hour_12 = st.selectbox("Hour", range(1, 13), index=11, key="birth_hour")
    with minute_col:
        minute = st.selectbox("Minute", range(0, 60), index=0, format_func=lambda value: f"{value:02d}", key="birth_minute")
    with period_col:
        period = st.selectbox("AM / PM", ("AM", "PM"), index=0, key="birth_period")

    hour_24 = hour_12 % 12 + (12 if period == "PM" else 0)
    return datetime(year, month, day, hour_24, minute)


def main() -> None:
    st.set_page_config(page_title="Vedic Kundli Generator", page_icon="✨", layout="centered")
    st.title("✨ Vedic Kundli Generator")
    st.caption("Lahiri sidereal zodiac · Whole-sign houses · North Indian chart")
    st.info("Enter the birth details accurately. Even a small time difference can change the ascendant.")

    name = st.text_input("Name", value="Rushabh", placeholder="Enter your name")
    local_birth = selected_datetime()

    st.markdown("**Birthplace (city, state, country)**")
    selected_place = st_searchbox(
        search_places,
        key="birthplace_search",
        placeholder="Start typing, for example: Mumbai, Maharashtra, India",
        label="Search birthplace",
        help="Type at least three characters, then choose one of the suggested places.",
        debounce=500,
        clear_on_submit=False,
    )

    generate = st.button("Create my Kundli", type="primary", use_container_width=True)
    if not generate:
        return
    if not name.strip():
        st.error("Please enter your name.")
        return
    if not selected_place:
        st.error("Please search for and select a birthplace from the suggestions.")
        return

    try:
        with st.spinner("Calculating planetary positions and drawing the chart..."):
            address, latitude, longitude, timezone_name = resolve_place(selected_place)
            utc_birth, julian_day = to_julian_day(local_birth, timezone_name)
            ascendant, positions = calculate_chart(julian_day, latitude, longitude)

            output_path = Path(__file__).with_name(f"kundli_{safe_filename(name)}.png")
            local_offset = local_birth.replace(tzinfo=ZoneInfo(timezone_name)).strftime("UTC%z")
            birth_caption = (
                f"{local_birth:%d-%m-%Y %I:%M %p} "
                f"({timezone_name}, {local_offset})"
            )
            draw_kundli(
                name.strip(), birth_caption, address, ascendant, positions, output_path
            )
            chart_data = {
                "name": name.strip(),
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
                "planets": [
                    {
                        "name": planet.full_name,
                        "sign": SIGN_NAMES[planet.sign],
                        "degree": round(planet.degree, 4),
                        "house": planet.house,
                        "retrograde": planet.retrograde,
                    }
                    for planet in positions
                ],
                "chart_image": str(output_path),
            }
            Path(__file__).with_name("latest_kundli.json").write_text(
                json.dumps(chart_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))
        return

    st.success("Your Kundli was created successfully.")
    st.image(str(output_path), caption=f"Kundli for {name.strip()}", use_container_width=True)

    with output_path.open("rb") as image_file:
        st.download_button(
            "Download Kundli as PNG",
            data=image_file.read(),
            file_name=output_path.name,
            mime="image/png",
            use_container_width=True,
        )

    asc_sign = int(ascendant // 30)
    first_col, second_col = st.columns(2)
    first_col.metric("Ascendant", f"{SIGN_NAMES[asc_sign]} {ascendant % 30:.2f}°")
    second_col.metric("Time zone", timezone_name)
    st.write(f"**Resolved place:** {address}")
    st.write(f"**Coordinates:** {latitude:.5f}, {longitude:.5f}")
    st.write(f"**UTC birth time:** {utc_birth:%d-%m-%Y %H:%M}")

    rows = [
        {
            "Planet": planet.full_name,
            "Sign": SIGN_NAMES[planet.sign],
            "Degree": f"{planet.degree:.2f}°",
            "House": planet.house,
            "Motion": "Retrograde" if planet.retrograde else "Direct",
        }
        for planet in positions
    ]
    st.subheader("Planetary positions")
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.caption("For educational use. Astrology is not scientifically validated.")


if __name__ == "__main__":
    main()
