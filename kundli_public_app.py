"""Privacy-safe public Kundli generator without saved profiles or RAG."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st
from streamlit_searchbox import st_searchbox

from kundli_complete_app import generate_chart, show_chart, show_upcoming_transits
from kundli_streamlit import search_places, selected_datetime


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
    main()
