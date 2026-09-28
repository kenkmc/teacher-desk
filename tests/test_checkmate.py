from pathlib import Path

from teacher_desk.services.checkmate import (
    CheckMateHit,
    _repo_from_release_page,
    _tag_from_release_page,
    iter_checkmate_exes,
    parse_sha256sums,
    pick_best_hit,
    version_from_path,
    version_key,
)


def test_iter_checkmate_exes_finds_nested_file(tmp_path: Path) -> None:
    target = tmp_path / "Apps" / "CheckMate_v1.7.1"
    target.mkdir(parents=True)
    exe = target / "CheckMate.exe"
    exe.write_bytes(b"fake")
    (tmp_path / "Windows").mkdir()
    (tmp_path / "Windows" / "CheckMate.exe").write_bytes(b"skip")
    hits = iter_checkmate_exes([tmp_path])
    assert [hit.path for hit in hits] == [exe]
    assert hits[0].version == "1.7.1"


def test_pick_best_hit_prefers_newer_non_build(tmp_path: Path) -> None:
    old = CheckMateHit(tmp_path / "old" / "CheckMate.exe", "1.6.4", 10)
    build = CheckMateHit(tmp_path / "dist" / "CheckMate.exe", "1.7.1", 99)
    newer = CheckMateHit(tmp_path / "CheckMate" / "CheckMate.exe", "1.7.1", 50)
    assert pick_best_hit([old, build, newer]) == newer


def test_parse_sha256sums_and_version_key() -> None:
    text = "f268ca28fce3165e23c820cd5fd119ed8c352025d1c0c9a738486610f92d57aa  CheckMate_Setup_v1.7.1.exe\n"
    mapping = parse_sha256sums(text)
    assert mapping["CheckMate_Setup_v1.7.1.exe"].startswith("f268ca28")
    assert version_key("1.7.1") > version_key("1.7.0")
    assert version_from_path(Path(r"C:\Users\x\Downloads\CheckMate_v1.6.4\CheckMate.exe")) == "1.6.4"
    url = "https://github.com/kenkmc/Checkmate/releases/tag/v1.7.1"
    assert _tag_from_release_page(url) == "v1.7.1"
    assert _repo_from_release_page(url) == "kenkmc/Checkmate"
