"""The fixture copy of a rig script carries what the script sources (native/261).

WHY THIS FILE RUNS EVERYWHERE AND THE BAND IT PROTECTS DOES NOT
---------------------------------------------------------------
`test_native_shoot_binary_resolution.py` and `test_native_gates_tree_resolution.py`
are macOS-only (BSD `stat`/`date`, `simctl`), so CI skips them. When
`tools/reserved-sim-guard.sh` was factored out on 2026-09-18 and sourced by
`native-shoot.sh`, the shoot fixture's hand-written copy list did not learn about
it and all ten of its tests died inside a subshell —

    tools/native-shoot.sh: line 86: <tree>/tools/reserved-sim-guard.sh: No such file

— visibly only to a Mac lane, which reads a red native band as somebody else's
stale tree. Two days.

The fix was to derive the copy list from the script (`lib_rig_tree.py`). These
tests are the part of that fix CI can actually run: pure text, no simulator, no
BSD utilities. If a rig script grows a sourcing form the fixtures cannot follow,
or names a sibling that is not in the checkout, this file goes red on Linux
before any Mac lane loses a session to it.
"""

from pathlib import Path

import pytest

from tests.lib_rig_tree import copy_rig_script, rig_script_deps

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools"

# Every rig script a fixture drives a copy of. Adding one here is free; the point
# is that its DEPENDENCIES are never listed anywhere.
COPIED_BY_FIXTURES = ["native-shoot.sh", "native-gates.sh", "native-upload.sh"]


@pytest.mark.parametrize("name", COPIED_BY_FIXTURES)
def test_every_sourced_sibling_is_discoverable_and_present(name):
    script = TOOLS / name
    if not script.is_file():
        pytest.skip(f"{name} is not in this checkout")
    # rig_script_deps raises on an unparseable source line or an absent sibling;
    # the assertion is that it returns at all.
    for dep in rig_script_deps(script):
        assert dep.is_file(), dep


def test_the_dependency_that_went_stale_is_found_by_derivation():
    """The specimen: native-shoot.sh sources the reserved-simulator guard."""
    script = TOOLS / "native-shoot.sh"
    guard = TOOLS / "reserved-sim-guard.sh"
    if not script.is_file() or not guard.is_file():
        pytest.skip("native rig is not in this checkout")
    assert guard.read_text().strip(), "the guard is empty — copying it proves nothing"
    assert guard in rig_script_deps(script), (
        "native-shoot.sh sources reserved-sim-guard.sh; the fixture copy must follow it"
    )


def test_a_copied_tree_holds_the_script_and_its_sources(tmp_path):
    script = TOOLS / "native-shoot.sh"
    if not script.is_file():
        pytest.skip("native rig is not in this checkout")
    copied = copy_rig_script(script, tmp_path / "tools")
    assert copied.is_file()
    for dep in rig_script_deps(script):
        assert (tmp_path / "tools" / dep.name).read_text() == dep.read_text(), dep.name


def test_an_unfollowable_source_line_raises_instead_of_copying_too_little(tmp_path):
    """Silently copying too little IS the bug; an unreadable form must be loud."""
    tools = tmp_path / "src"
    tools.mkdir()
    (tools / "rig.sh").write_text('set -u\n. "$RIG_HOME/helper.sh"\necho hi\n')
    with pytest.raises(AssertionError, match="cannot follow"):
        copy_rig_script(tools / "rig.sh", tmp_path / "dest")


def test_a_named_sibling_that_does_not_exist_raises(tmp_path):
    tools = tmp_path / "src"
    tools.mkdir()
    (tools / "rig.sh").write_text('. "$(dirname "$0")/gone.sh"\n')
    with pytest.raises(AssertionError, match="does not exist"):
        copy_rig_script(tools / "rig.sh", tmp_path / "dest")


def test_sources_are_followed_transitively(tmp_path):
    tools = tmp_path / "src"
    tools.mkdir()
    (tools / "rig.sh").write_text('. "$(dirname "$0")/mid.sh"\n')
    (tools / "mid.sh").write_text('. "$(dirname "$0")/leaf.sh"\n')
    (tools / "leaf.sh").write_text("leaf() { :; }\n")
    copy_rig_script(tools / "rig.sh", tmp_path / "dest")
    assert sorted(p.name for p in (tmp_path / "dest").iterdir()) == [
        "leaf.sh",
        "mid.sh",
        "rig.sh",
    ]


def test_a_cycle_does_not_hang(tmp_path):
    tools = tmp_path / "src"
    tools.mkdir()
    (tools / "a.sh").write_text('. "$(dirname "$0")/b.sh"\n')
    (tools / "b.sh").write_text('. "$(dirname "$0")/a.sh"\n')
    copy_rig_script(tools / "a.sh", tmp_path / "dest")
    assert sorted(p.name for p in (tmp_path / "dest").iterdir()) == ["a.sh", "b.sh"]
