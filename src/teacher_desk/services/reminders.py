"""Determine when a weekly timetable reminder is due."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from teacher_desk.db import TimetableEntry


def due_occurrence(entry: TimetableEntry, now: datetime, grace_seconds: int = 90) -> str | None:
    """Return the lesson date when its reminder is due in the current poll window."""
    if not entry.enabled or entry.id is None:
        return None
    start_time = time.fromisoformat(entry.start_time)
    for day_offset in (-1, 0, 1):
        lesson_date = now.date() + timedelta(days=day_offset)
        if lesson_date.weekday() != entry.weekday:
            continue
        lesson_start = datetime.combine(lesson_date, start_time)
        reminder_at = lesson_start - timedelta(minutes=entry.remind_before)
        if reminder_at <= now < reminder_at + timedelta(seconds=grace_seconds):
            return lesson_date.isoformat()
    return None
