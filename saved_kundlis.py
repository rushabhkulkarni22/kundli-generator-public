"""Local storage and import helpers for saved Kundli birth details."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any


STORE_PATH = Path(__file__).with_name("saved_kundlis.json")


def load_profiles() -> list[dict[str, Any]]:
    if not STORE_PATH.exists():
        return []
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_profiles(profiles: list[dict[str, Any]]) -> None:
    temporary = STORE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(STORE_PATH)


def _integer(record: dict, *names: str, default: int = 0) -> int:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return int(float(value))
    return default


def normalize_profile(record: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an Astrotalk JSON/CSV record to the app's local format."""

    name = str(record.get("name") or record.get("fullName") or "").strip()
    place = str(record.get("place") or record.get("birthPlace") or "").strip()
    try:
        day = _integer(record, "day", "birthDay")
        month = _integer(record, "month", "birthMonth")
        year = _integer(record, "year", "birthYear")
        hour = _integer(record, "hour", "birthHour")
        minute = _integer(record, "min", "minute", "birthMinute")
    except (TypeError, ValueError):
        return None
    if not name or not place or not (1 <= day <= 31 and 1 <= month <= 12 and year >= 1900):
        return None
    identifier = str(record.get("id") or record.get("encid") or "").strip()
    if not identifier:
        identifier = f"{name}|{year:04d}-{month:02d}-{day:02d}|{hour:02d}:{minute:02d}|{place}"
    return {
        "id": identifier,
        "name": name,
        "gender": record.get("gender", ""),
        "day": day,
        "month": month,
        "year": year,
        "hour": hour,
        "minute": minute,
        "place": place,
        "latitude": record.get("lat", record.get("latitude")),
        "longitude": record.get("lon", record.get("longitude")),
        "timezone_offset": record.get("tzone", record.get("timezoneOffset")),
        "source": record.get("source", "Astrotalk"),
    }


def _find_records(value: Any) -> list[dict[str, Any]]:
    # HAR exports keep each API response as a JSON string in response.content.text.
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return _find_records(json.loads(value))
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, dict)]
        if records and any("name" in item and "year" in item for item in records):
            return records
        found: list[dict[str, Any]] = []
        for item in value:
            found.extend(_find_records(item))
        return found
    if isinstance(value, dict):
        if "name" in value and "year" in value and ("place" in value or "birthPlace" in value):
            return [value]
        found = []
        for child in value.values():
            found.extend(_find_records(child))
        return found
    return []


def import_profiles(content: bytes, filename: str) -> tuple[list[dict[str, Any]], int]:
    text = content.decode("utf-8-sig")
    if filename.lower().endswith(".csv"):
        raw_records = list(csv.DictReader(io.StringIO(text)))
    else:
        raw_records = _find_records(json.loads(text))
    normalized = [profile for row in raw_records if (profile := normalize_profile(row))]
    existing = {profile["id"]: profile for profile in load_profiles()}
    before = len(existing)
    existing.update({profile["id"]: profile for profile in normalized})
    profiles = sorted(existing.values(), key=lambda item: item["name"].casefold())
    save_profiles(profiles)
    return profiles, len(existing) - before


def upsert_profile(profile: dict[str, Any]) -> None:
    normalized = normalize_profile(profile)
    if not normalized:
        return
    profiles = {item["id"]: item for item in load_profiles()}
    profiles[normalized["id"]] = normalized
    save_profiles(sorted(profiles.values(), key=lambda item: item["name"].casefold()))


def delete_profile(profile_id: str) -> None:
    save_profiles([profile for profile in load_profiles() if profile["id"] != profile_id])


def import_pasted_text(text: str) -> tuple[list[dict[str, Any]], int]:
    """Import the plain-text Saved Kundli listing copied from Astrotalk."""

    records = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = [line.strip().rstrip("\\") for line in block.splitlines() if line.strip()]
        if len(lines) == 4 and len(lines[0]) == 1:
            lines = lines[1:]
        if len(lines) != 3:
            continue
        name_gender, date_time, place = lines
        if "," not in name_gender:
            continue
        name, gender = (part.strip() for part in name_gender.rsplit(",", 1))
        try:
            birth = datetime.strptime(date_time, "%d %b, %Y %I:%M %p")
        except ValueError:
            continue
        records.append({
            "name": name,
            "gender": gender,
            "day": birth.day,
            "month": birth.month,
            "year": birth.year,
            "hour": birth.hour,
            "min": birth.minute,
            "place": place,
            "source": "Astrotalk",
        })

    existing = {profile["id"]: profile for profile in load_profiles()}
    before = len(existing)
    for record in records:
        profile = normalize_profile(record)
        if profile:
            existing[profile["id"]] = profile
    profiles = sorted(existing.values(), key=lambda item: item["name"].casefold())
    save_profiles(profiles)
    return profiles, len(existing) - before
