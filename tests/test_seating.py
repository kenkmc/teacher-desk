from teacher_desk.db import Student
from teacher_desk.services.seating import (
    SEAT_HEIGHT,
    SEAT_WIDTH,
    empty_grid,
    grid_to_json,
    json_to_grid,
    layout_to_json,
    parse_layout,
    random_assignment,
    randomize_layout,
    snap_to_neighbors,
)


def test_json_roundtrip() -> None:
    grid = empty_grid(2, 3)
    grid[0][1] = 9
    restored = json_to_grid(grid_to_json(grid), 2, 3)
    assert restored[0][1] == 9
    assert restored[1][2] is None


def test_layout_roundtrip_and_legacy_grid() -> None:
    layout = parse_layout("[[1,null],[null,2]]", 2, 2)
    assert layout.seats[0].student_id == 1
    assert layout.seats[3].student_id == 2
    layout.podium.x = 40
    layout.seats[1].x = 200
    restored = parse_layout(layout_to_json(layout), 2, 2)
    assert restored.podium.x == 40
    assert restored.seats[1].x == 200
    assert restored.seats[0].student_id == 1


def test_random_keeps_locked_seats() -> None:
    students = [Student(i, 1, str(i), f"S{i}") for i in range(1, 5)]
    current = empty_grid(2, 2)
    current[0][0] = 1
    result = random_assignment(students, 2, 2, locked={(0, 0)}, current=current)
    assert result[0][0] == 1
    seated = [cell for row in result for cell in row if cell is not None]
    assert 1 in seated
    assert len(seated) == 4


def test_randomize_layout_keeps_locked_students() -> None:
    layout = parse_layout(None, 2, 2)
    layout.seats[0].student_id = 1
    layout.seats[0].locked = True
    students = [Student(i, 1, str(i), f"S{i}") for i in range(1, 5)]
    result = randomize_layout(layout, students)
    assert result.seats[0].student_id == 1
    seated = [seat.student_id for seat in result.seats if seat.student_id is not None]
    assert 1 in seated
    assert len(seated) == 4


def test_snap_to_adjacent_seat() -> None:
    neighbor = (0, 0, SEAT_WIDTH, SEAT_HEIGHT)
    x, y = snap_to_neighbors(SEAT_WIDTH - 8, 6, SEAT_WIDTH, SEAT_HEIGHT, [neighbor])
    assert x == SEAT_WIDTH
    assert y == 0
    x, y = snap_to_neighbors(4, SEAT_HEIGHT - 10, SEAT_WIDTH, SEAT_HEIGHT, [neighbor])
    assert x == 0
    assert y == SEAT_HEIGHT
