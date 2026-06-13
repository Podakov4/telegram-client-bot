from __future__ import annotations

from typing import Optional


def parse_notes(notes: Optional[str]) -> dict[str, str]:
    data: dict[str, str] = {}
    if not notes:
        return data
    for line in notes.splitlines():
        raw = line.strip()
        if not raw or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def dump_notes(data: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in data.items())


def get_note_int(notes: Optional[str], key: str, default: int) -> int:
    value = parse_notes(notes).get(key)
    if not value:
        return default
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def upsert_note(notes: Optional[str], key: str, value: str) -> str:
    data = parse_notes(notes)
    data[key] = value
    return dump_notes(data)
