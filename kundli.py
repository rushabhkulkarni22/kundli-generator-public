"""Create a North-Indian-style Vedic birth chart (Kundli).

The program asks for name, birth date, birth time, and birthplace, then:
1. finds the place's latitude/longitude and IANA time zone,
2. converts the local birth time to UTC,
3. calculates Lahiri sidereal positions with Swiss Ephemeris, and
4. saves a North Indian chart as a PNG image.

This is an educational calculator, not professional or scientific advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Iterable
from zoneinfo import ZoneInfo

import swisseph as swe
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim
from functools import lru_cache


SIGN_NAMES = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)

# Classical Vedic rulers for Aries through Pisces.
SIGN_LORDS = (
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
)

PLANETS = (
    ("Su", "Sun", swe.SUN),
    ("Mo", "Moon", swe.MOON),
    ("Ma", "Mars", swe.MARS),
    ("Me", "Mercury", swe.MERCURY),
    ("Ju", "Jupiter", swe.JUPITER),
    ("Ve", "Venus", swe.VENUS),
    ("Sa", "Saturn", swe.SATURN),
    ("Ur", "Uranus", swe.URANUS),
    ("Ne", "Neptune", swe.NEPTUNE),
    ("Pl", "Pluto", swe.PLUTO),
    ("Ra", "Rahu", swe.MEAN_NODE),
)

# Text centres for houses 1..12 in a fixed North Indian chart.
HOUSE_CENTRES = {
    1: (0.50, 0.28), 2: (0.27, 0.13), 3: (0.13, 0.27),
    4: (0.28, 0.50), 5: (0.13, 0.73), 6: (0.27, 0.87),
    7: (0.50, 0.72), 8: (0.73, 0.87), 9: (0.87, 0.73),
    10: (0.72, 0.50), 11: (0.87, 0.27), 12: (0.73, 0.13),
}

# Zodiac sign labels sit beside the internal junctions in a North Indian chart.
# They must not be centred in the same area used for planet text.
SIGN_POSITIONS = {
    1: (0.50, 0.445), 2: (0.265, 0.205), 3: (0.10, 0.18),
    4: (0.445, 0.50), 5: (0.13, 0.73), 6: (0.265, 0.795),
    7: (0.50, 0.555), 8: (0.735, 0.795), 9: (0.90, 0.81),
    10: (0.555, 0.50), 11: (0.91, 0.22), 12: (0.735, 0.205),
}

COLOURS = {
    "Su": "#e67e22", "Mo": "#555555", "Ma": "#d62728",
    "Me": "#2ca02c", "Ju": "#c49a00", "Ve": "#d84fa3",
    "Sa": "#4f8080", "Ur": "#e0a800", "Ne": "#1683d8",
    "Pl": "#34495e", "Ra": "#444444", "Ke": "#8b4513",
    "Asc": "#4f8080",
}


@dataclass(frozen=True)
class BodyPosition:
    short_name: str
    full_name: str
    longitude: float
    sign: int
    degree: float
    house: int
    retrograde: bool = False


CLASSICAL_GRAHAS = {
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"
}


def natal_house_lord(ascendant_sign: str, house: int) -> str:
    """Return the classical lord of a whole-sign natal house."""

    ascendant_index = SIGN_NAMES.index(ascendant_sign)
    house_sign_index = (ascendant_index + house - 1) % 12
    return SIGN_LORDS[house_sign_index]


def find_shadashtak_pairs(planets) -> list[dict]:
    """Return classical-graha pairs having an inclusive 6–8 house relationship."""

    eligible = [planet for planet in planets if planet["name"] in CLASSICAL_GRAHAS]
    pairs = []
    for index, first in enumerate(eligible):
        for second in eligible[index + 1:]:
            first_to_second = ((second["house"] - first["house"]) % 12) + 1
            second_to_first = ((first["house"] - second["house"]) % 12) + 1
            if {first_to_second, second_to_first} == {6, 8}:
                pairs.append({
                    "first": first["name"],
                    "second": second["name"],
                    "first_house": first["house"],
                    "second_house": second["house"],
                    "relationship": f"{first_to_second}-{second_to_first}",
                })
    return pairs


def ask_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Please enter a value.")


def parse_birth_datetime(date_text: str, time_text: str) -> datetime:
    formats = ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M")
    combined = f"{date_text} {time_text}"
    for date_format in formats:
        try:
            return datetime.strptime(combined, date_format)
        except ValueError:
            pass
    raise ValueError("Use DD-MM-YYYY for the date and HH:MM (24-hour) for the time.")


@lru_cache(maxsize=128)
def resolve_place(place: str) -> tuple[str, float, float, str]:
    from timezonefinder import TimezoneFinder
    geocoder = Nominatim(user_agent="educational-kundli-python-app", timeout=15)
    try:
        location = geocoder.geocode(place, exactly_one=True, addressdetails=True)
    except GeocoderServiceError as error:
        raise RuntimeError(f"The location service could not be reached: {error}") from error

    if location is None:
        raise ValueError(f"Place not found: {place!r}. Try adding state and country.")

    latitude, longitude = float(location.latitude), float(location.longitude)
    with TimezoneFinder() as finder:
        timezone_name = finder.timezone_at(lng=longitude, lat=latitude)
    if timezone_name is None:
        raise ValueError("Could not determine the time zone for that location.")

    return location.address, latitude, longitude, timezone_name


def to_julian_day(local_birth: datetime, timezone_name: str) -> tuple[datetime, float]:
    local_aware = local_birth.replace(tzinfo=ZoneInfo(timezone_name))
    utc_birth = local_aware.astimezone(timezone.utc)
    decimal_hour = (
        utc_birth.hour
        + utc_birth.minute / 60
        + utc_birth.second / 3600
        + utc_birth.microsecond / 3_600_000_000
    )
    jd = swe.julday(
        utc_birth.year, utc_birth.month, utc_birth.day, decimal_hour, swe.GREG_CAL
    )
    return utc_birth, jd


def calculate_chart(jd: float, latitude: float, longitude: float) -> tuple[float, list[BodyPosition]]:
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED | swe.FLG_SWIEPH

    # Whole-sign houses are conventional for this simple Vedic chart.
    _cusps, important_points = swe.houses_ex(
        jd, latitude, longitude, b"W", swe.FLG_SIDEREAL
    )
    ascendant = important_points[0] % 360
    asc_sign = int(ascendant // 30)

    positions: list[BodyPosition] = []
    for short_name, full_name, planet_id in PLANETS:
        values, _return_flags = swe.calc_ut(jd, planet_id, flags)
        planet_longitude = values[0] % 360
        sign = int(planet_longitude // 30)
        house = ((sign - asc_sign) % 12) + 1
        positions.append(
            BodyPosition(
                short_name=short_name,
                full_name=full_name,
                longitude=planet_longitude,
                sign=sign,
                degree=planet_longitude % 30,
                house=house,
                retrograde=values[3] < 0,
            )
        )

    # Ketu is always exactly opposite Rahu.
    rahu = positions[-1]
    ketu_longitude = (rahu.longitude + 180) % 360
    ketu_sign = int(ketu_longitude // 30)
    positions.append(
        BodyPosition(
            "Ke", "Ketu", ketu_longitude, ketu_sign, ketu_longitude % 30,
            ((ketu_sign - asc_sign) % 12) + 1, rahu.retrograde,
        )
    )
    return ascendant, positions


def draw_base_chart(axis: plt.Axes) -> None:
    lines: Iterable[tuple[tuple[float, float], tuple[float, float]]] = (
        ((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0)),
        ((0.5, 0), (1, 0.5)), ((1, 0.5), (0.5, 1)),
        ((0.5, 1), (0, 0.5)), ((0, 0.5), (0.5, 0)),
        ((0, 0), (1, 1)), ((0, 1), (1, 0)),
    )
    for start, end in lines:
        axis.plot((start[0], end[0]), (start[1], end[1]), color="#333333", linewidth=1.15)
    axis.set_xlim(-0.01, 1.01)
    axis.set_ylim(1.01, -0.01)
    axis.set_aspect("equal")
    axis.axis("off")


def draw_kundli(
    name: str,
    birth_text: str,
    place: str,
    ascendant: float,
    positions: list[BodyPosition],
    output_path: Path,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axis = plt.subplots(figsize=(10, 10), facecolor="white")
    draw_base_chart(axis)
    asc_sign = int(ascendant // 30)

    grouped: dict[int, list[BodyPosition]] = {house: [] for house in range(1, 13)}
    for planet in positions:
        grouped[planet.house].append(planet)

    for house in range(1, 13):
        x, y = HOUSE_CENTRES[house]
        sign_number = ((asc_sign + house - 1) % 12) + 1
        sign_x, sign_y = SIGN_POSITIONS[house]
        axis.text(
            sign_x, sign_y, str(sign_number),
            ha="center", va="center", fontsize=11, color="#b58900",
        )

        entries: list[tuple[str, str]] = []
        if house == 1:
            entries.append(("Asc", f"Asc {ascendant % 30:.2f}°"))
        for planet in grouped[house]:
            retrograde = " R" if planet.retrograde else ""
            entries.append(
                (planet.short_name, f"{planet.short_name} {planet.degree:.2f}°{retrograde}")
            )

        # Keep text inside each triangular house and avoid excessive overlap.
        start_y = y - (len(entries) - 1) * 0.018
        for index, (key, label) in enumerate(entries):
            axis.text(
                x, start_y + index * 0.037, label,
                ha="center", va="center", fontsize=10.5,
                color=COLOURS.get(key, "#333333"),
            )

    fig.suptitle(f"Kundli — {name}\n{birth_text}\n{place}", fontsize=13, y=0.985)
    fig.subplots_adjust(top=0.88, bottom=0.03, left=0.03, right=0.97)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def safe_filename(name: str) -> str:
    cleaned = "".join(character if character.isalnum() else "_" for character in name)
    return cleaned.strip("_") or "birth"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Vedic Kundli Generator (Lahiri sidereal, whole-sign houses)\n")
    name = ask_nonempty("Name: ")
    date_text = ask_nonempty("Date of birth (DD-MM-YYYY): ")
    time_text = ask_nonempty("Time of birth (HH:MM, 24-hour): ")
    place_text = ask_nonempty("Birthplace (city, state, country): ")

    try:
        local_birth = parse_birth_datetime(date_text, time_text)
        address, latitude, longitude, timezone_name = resolve_place(place_text)
        utc_birth, jd = to_julian_day(local_birth, timezone_name)
        ascendant, positions = calculate_chart(jd, latitude, longitude)
    except (ValueError, RuntimeError) as error:
        print(f"\nError: {error}")
        return

    output_path = Path(__file__).with_name(f"kundli_{safe_filename(name)}.png")
    local_offset = local_birth.replace(tzinfo=ZoneInfo(timezone_name)).strftime("UTC%z")
    birth_caption = f"{date_text} {time_text} ({timezone_name}, {local_offset})"
    draw_kundli(name, birth_caption, address, ascendant, positions, output_path)

    asc_sign = int(ascendant // 30)
    print(f"\nResolved place: {address}")
    print(f"Coordinates: {latitude:.5f}, {longitude:.5f}")
    print(f"Time zone: {timezone_name} | UTC: {utc_birth:%Y-%m-%d %H:%M}")
    print(f"Ascendant: {SIGN_NAMES[asc_sign]} {ascendant % 30:.2f}°")
    print("\nPlanet      Sign          Degree   House   Motion")
    print("-" * 54)
    for planet in positions:
        motion = "Retrograde" if planet.retrograde else "Direct"
        print(
            f"{planet.full_name:<11} {SIGN_NAMES[planet.sign]:<13} "
            f"{planet.degree:>6.2f}°   {planet.house:>2}     {motion}"
        )
    print(f"\nKundli image saved to: {output_path}")


if __name__ == "__main__":
    main()
