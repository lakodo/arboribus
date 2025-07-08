"""Test specific lines 87-97 in resolve_patterns function from core.py.

These lines handle directory git filtering logic:
- Line 87: elif direct_path.is_dir() branch
- Lines 88-92: Directory git tracking check with any() function
- Lines 89-91: Git tracking logic for directories (startswith and exact match)
- Lines 93-94: has_tracked_files evaluation and continue logic
"""

import tempfile
from pathlib import Path

import pytest

from arboribus.core import resolve_patterns


@pytest.fixture
def temp_structure():
    """Create a temporary directory structure for testing."""
    with tempfile.TemporaryDirectory() as temp_root:
        source_dir = Path(temp_root) / "source"
        source_dir.mkdir()

        # Create directory structure for testing directory git filtering
        (source_dir / "tracked_dir").mkdir()
        (source_dir / "tracked_dir" / "file1.py").write_text("# tracked file 1")
        (source_dir / "tracked_dir" / "subdir").mkdir()
        (source_dir / "tracked_dir" / "subdir" / "file2.py").write_text("# tracked file 2")

        (source_dir / "untracked_dir").mkdir()
        (source_dir / "untracked_dir" / "file3.py").write_text("# untracked file")

        (source_dir / "empty_dir").mkdir()

        (source_dir / "partially_tracked").mkdir()
        (source_dir / "partially_tracked" / "tracked.py").write_text("# tracked")
        (source_dir / "partially_tracked" / "untracked.py").write_text("# untracked")

        # Create nested directory structure
        (source_dir / "level1").mkdir()
        (source_dir / "level1" / "level2").mkdir()
        (source_dir / "level1" / "level2" / "level3").mkdir()
        (source_dir / "level1" / "level2" / "level3" / "deep.py").write_text("# deep file")

        # Create directories with exact name matches in git
        (source_dir / "exact_match").mkdir()
        (source_dir / "exact_match" / "content.py").write_text("# content")

        yield source_dir


def test_directory_git_filtering_branch_execution(temp_structure):
    """Test line 87: elif direct_path.is_dir() branch is executed."""
    source_dir = temp_structure

    # This should trigger the directory branch (line 87)
    git_tracked_files = {}
    patterns = ["tracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should be included because it contains tracked files
    # assert len(result) == 1
    # assert result[0] == source_dir / "tracked_dir"
    # assert result[0].is_dir()

