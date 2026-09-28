from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from teacher_desk.db import Student

SEAT_WIDTH = 110
SEAT_HEIGHT = 72
SEAT_GAP_X = 12
SEAT_GAP_Y = 12
PODIUM_HEIGHT = 44
ROOM_MARGIN = 16
SNAP_THRESHOLD = 16


@dataclass
class Seat:
    row: int
    col: int
    student_id: int | None = None


@dataclass
class SeatItem:
    id: str
    x: int
    y: int
    w: int = SEAT_WIDTH
    h: int = SEAT_HEIGHT
    student_id: int | None = None
    locked: bool = False


@dataclass
class PodiumItem:
    x: int
    y: int
    w: int
    h: int = PODIUM_HEIGHT


@dataclass
class RoomLayout:
    podium: PodiumItem
    seats: list[SeatItem] = field(default_factory=list)


def empty_grid(rows: int, cols: int) -> list[list[int | None]]:
    return [[None for _ in range(cols)] for _ in range(rows)]


def grid_to_json(grid: list[list[int | None]]) -> str:
    return json.dumps(grid)


def json_to_grid(raw: str, rows: int, cols: int) -> list[list[int | None]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return empty_grid(rows, cols)
    if isinstance(data, dict):
        layout = parse_layout(raw, rows, cols)
        grid = empty_grid(rows, cols)
        for index, seat in enumerate(layout.seats):
            row, col = divmod(index, max(cols, 1))
            if row < rows and col < cols:
                grid[row][col] = seat.student_id
        return grid
    grid = empty_grid(rows, cols)
    if not isinstance(data, list):
        return grid
    for r, row in enumerate(data[:rows]):
        if not isinstance(row, list):
            continue
        for c, value in enumerate(row[:cols]):
            grid[r][c] = int(value) if value is not None else None
    return grid


def default_room_layout(rows: int, cols: int) -> RoomLayout:
    rows = max(rows, 1)
    cols = max(cols, 1)
    grid_w = cols * SEAT_WIDTH + (cols - 1) * SEAT_GAP_X
    podium = PodiumItem(x=ROOM_MARGIN, y=ROOM_MARGIN, w=max(grid_w, 220), h=PODIUM_HEIGHT)
    seats: list[SeatItem] = []
    origin_y = ROOM_MARGIN + PODIUM_HEIGHT + 16
    for row in range(rows):
        for col in range(cols):
            seats.append(
                SeatItem(
                    id=f"s-{row}-{col}",
                    x=ROOM_MARGIN + col * (SEAT_WIDTH + SEAT_GAP_X),
                    y=origin_y + row * (SEAT_HEIGHT + SEAT_GAP_Y),
                    w=SEAT_WIDTH,
                    h=SEAT_HEIGHT,
                )
            )
    return RoomLayout(podium=podium, seats=seats)


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_layout(raw: str | None, rows: int, cols: int) -> RoomLayout:
    layout = default_room_layout(rows, cols)
    if not raw:
        return layout
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return layout
    if isinstance(data, list):
        grid = json_to_grid(raw, rows, cols)
        for index, seat in enumerate(layout.seats):
            row, col = divmod(index, max(cols, 1))
            if row < len(grid) and col < len(grid[row]):
                seat.student_id = grid[row][col]
        return layout
    if not isinstance(data, dict):
        return layout
    podium_data = data.get("podium") if isinstance(data.get("podium"), dict) else {}
    layout.podium = PodiumItem(
        x=_as_int(podium_data.get("x"), layout.podium.x),
        y=_as_int(podium_data.get("y"), layout.podium.y),
        w=max(_as_int(podium_data.get("w"), layout.podium.w), 80),
        h=max(_as_int(podium_data.get("h"), layout.podium.h), 28),
    )
    seats_data = data.get("seats")
    if not isinstance(seats_data, list) or not seats_data:
        grid = json_to_grid(json.dumps(data.get("grid") or []), rows, cols)
        for index, seat in enumerate(layout.seats):
            row, col = divmod(index, max(cols, 1))
            if row < len(grid) and col < len(grid[row]):
                seat.student_id = grid[row][col]
        return layout
    seats: list[SeatItem] = []
    for index, item in enumerate(seats_data):
        if not isinstance(item, dict):
            continue
        student_raw = item.get("student_id")
        student_id = int(student_raw) if student_raw is not None and str(student_raw).lstrip("-").isdigit() else None
        seats.append(
            SeatItem(
                id=str(item.get("id") or f"s-{index}"),
                x=_as_int(item.get("x"), ROOM_MARGIN),
                y=_as_int(item.get("y"), ROOM_MARGIN + PODIUM_HEIGHT + 16),
                w=max(_as_int(item.get("w"), SEAT_WIDTH), 72),
                h=max(_as_int(item.get("h"), SEAT_HEIGHT), 48),
                student_id=student_id,
                locked=bool(item.get("locked")),
            )
        )
    if seats:
        layout.seats = seats
    return layout


def layout_to_json(layout: RoomLayout) -> str:
    return json.dumps(
        {
            "version": 2,
            "podium": {
                "x": layout.podium.x,
                "y": layout.podium.y,
                "w": layout.podium.w,
                "h": layout.podium.h,
            },
            "seats": [
                {
                    "id": seat.id,
                    "x": seat.x,
                    "y": seat.y,
                    "w": seat.w,
                    "h": seat.h,
                    "student_id": seat.student_id,
                    "locked": seat.locked,
                }
                for seat in layout.seats
            ],
        },
        ensure_ascii=False,
    )


def random_assignment(
    students: list[Student],
    rows: int,
    cols: int,
    locked: set[tuple[int, int]] | None = None,
    current: list[list[int | None]] | None = None,
) -> list[list[int | None]]:
    locked = locked or set()
    grid = [row[:] for row in (current or empty_grid(rows, cols))]
    locked_ids = {grid[r][c] for r, c in locked if grid[r][c] is not None}
    pool = [student.id for student in students if student.id not in locked_ids]
    random.shuffle(pool)
    seats = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in locked]
    random.shuffle(seats)
    for r, c in seats:
        grid[r][c] = None
    for seat, student_id in zip(seats, pool, strict=False):
        grid[seat[0]][seat[1]] = student_id
    return grid


def _ranges_near(start_a: int, end_a: int, start_b: int, end_b: int, threshold: int) -> bool:
    return not (end_a + threshold < start_b or end_b + threshold < start_a)


def snap_to_neighbors(
    x: int,
    y: int,
    w: int,
    h: int,
    others: list[tuple[int, int, int, int]],
    threshold: int = SNAP_THRESHOLD,
) -> tuple[int, int]:
    """把矩形貼齊相鄰物件：邊緣相接，並在接近時對齊頂／側邊。"""
    snapped_x, snapped_y = x, y
    best_dx = threshold + 1
    best_dy = threshold + 1
    for ox, oy, ow, oh in others:
        if _ranges_near(y, y + h, oy, oy + oh, threshold):
            for target in (ox - w, ox + ow, ox, ox + ow - w):
                dx = abs(target - x)
                if dx < best_dx:
                    best_dx = dx
                    snapped_x = target
        if _ranges_near(x, x + w, ox, ox + ow, threshold):
            for target in (oy - h, oy + oh, oy, oy + oh - h):
                dy = abs(target - y)
                if dy < best_dy:
                    best_dy = dy
                    snapped_y = target
    return max(0, snapped_x), max(0, snapped_y)


def randomize_layout(layout: RoomLayout, students: list[Student]) -> RoomLayout:
    locked_ids = {seat.student_id for seat in layout.seats if seat.locked and seat.student_id is not None}
    pool = [student.id for student in students if student.id not in locked_ids]
    random.shuffle(pool)
    open_seats = [seat for seat in layout.seats if not seat.locked]
    for seat in open_seats:
        seat.student_id = None
    for seat, student_id in zip(open_seats, pool, strict=False):
        seat.student_id = student_id
    return layout
