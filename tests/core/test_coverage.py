"""Focused tests to achieve 100% coverage on core module."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arboribus.core import (
    collect_files_recursive,
    get_default_source,
    get_file_statistics,
    get_git_tracked_files,
    process_directory_sync,
    process_file_sync,
    resolve_patterns,
    sync_directory,
)


@pytest.fixture
def temp_dirs():
    """Create temporary source and target directories."""
    with tempfile.TemporaryDirectory() as temp_root:
        source_dir = Path(temp_root) / "source"
        target_dir = Path(temp_root) / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        yield source_dir, target_dir


def test_git_subprocess_error(temp_dirs):
    """Test get_git_tracked_files with subprocess CalledProcessError."""
    source_dir, _ = temp_dirs

    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_git_file_not_found(temp_dirs):
    """Test get_git_tracked_files with FileNotFoundError."""
    source_dir, _ = temp_dirs

    with patch("subprocess.run", side_effect=FileNotFoundError()):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_git_empty_output(temp_dirs):
    """Test get_git_tracked_files with empty git output."""
    source_dir, _ = temp_dirs

    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:  # ls-files
            return MagicMock(returncode=0, stdout="")

    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        assert result == set()


def test_resolve_patterns_no_git_matches(temp_dirs):
    """Test resolve_patterns when git filtering finds no matches."""
    source_dir, _ = temp_dirs

    # Create a directory
    test_dir = source_dir / "testdir"
    test_dir.mkdir()

    # Git tracks different files
    git_tracked = {"other/file.py"}

    result = resolve_patterns(source_dir, ["testdir"], git_tracked_files=git_tracked)
    assert len(result) == 0  # Should be filtered out


def test_resolve_patterns_no_glob_matches(temp_dirs):
    """Test resolve_patterns with patterns that don't match anything."""
    source_dir, _ = temp_dirs

    # Create some files
    (source_dir / "test.py").write_text("content")

    # Use pattern that won't match
    result = resolve_patterns(source_dir, ["*.nonexistent"])
    assert len(result) == 0


def test_resolve_patterns_include_files_git_filtering(temp_dirs):
    """Test resolve_patterns with include_files and git filtering."""
    source_dir, _ = temp_dirs

    # Create files
    (source_dir / "tracked.txt").write_text("content")
    (source_dir / "untracked.txt").write_text("content")

    # Only track one file
    git_tracked = {"tracked.txt"}

    result = resolve_patterns(source_dir, ["*.txt"], git_tracked_files=git_tracked, include_files=True)
    assert len(result) == 1
    assert result[0].name == "tracked.txt"


def test_collect_files_recursive_glob_error(temp_dirs):
    """Test collect_files_recursive when glob operation fails."""
    source_dir, _ = temp_dirs

    test_dir = source_dir / "testdir"
    test_dir.mkdir()

    with patch.object(Path, "rglob", side_effect=OSError("Permission denied")):
        files = collect_files_recursive(test_dir, source_dir)
        assert files == []


def test_get_file_statistics_no_extension(temp_dirs):
    """Test get_file_statistics with files that have no extension."""
    source_dir, _ = temp_dirs

    # Create file with no extension
    (source_dir / "noext").write_text("content")

    stats = get_file_statistics([source_dir / "noext"], source_dir)
    assert "(no extension)" in stats
    assert stats["(no extension)"] == 1


def test_process_file_sync_mkdir_error(temp_dirs):
    """Test process_file_sync when mkdir fails."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    source_file.write_text("content")
    target_file = target_dir / "deep" / "nested" / "test.txt"

    with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
        was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=False)
        assert not was_processed
        assert "error" in message.lower()


def test_process_file_sync_copy_error(temp_dirs):
    """Test process_file_sync when copy fails."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    source_file.write_text("content")
    target_file = target_dir / "test.txt"

    with patch("shutil.copy2", side_effect=OSError("Disk full")):
        was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=False)
        assert not was_processed
        assert "error" in message.lower()


def test_process_directory_sync_copytree_error(temp_dirs):
    """Test process_directory_sync when copytree fails."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml for ignore function
    (source_dir / "arboribus.toml").write_text("")

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    target_test = target_dir / "testdir"

    with patch("shutil.copytree", side_effect=OSError("Permission denied")):
        was_processed, message = process_directory_sync(test_dir, target_test, source_dir, None, dry=False)
        assert not was_processed
        assert "error" in message.lower()


def test_process_directory_sync_rmtree_error(temp_dirs):
    """Test process_directory_sync when rmtree fails during replace."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    # Create existing target
    target_test = target_dir / "testdir"
    target_test.mkdir()

    with patch("shutil.rmtree", side_effect=OSError("Permission denied")):
        was_processed, message = process_directory_sync(
            test_dir, target_test, source_dir, None, dry=False, replace_existing=True
        )
        assert not was_processed
        assert "error" in message.lower()


def test_sync_directory_reverse_nonexistent(temp_dirs):
    """Test sync_directory reverse mode with non-existent source."""
    source_dir, target_dir = temp_dirs

    # Use a non-existent path within the temp directory
    non_existent = source_dir.parent / "nonexistent"

    # Should handle gracefully without crashing
    sync_directory(non_existent, target_dir, reverse=True, dry=False)


def test_get_default_source_not_found():
    """Test get_default_source when no config file is found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch("pathlib.Path.cwd", return_value=Path(temp_dir)):
            # No arboribus.toml exists
            result = get_default_source()
            assert result is None


def test_ignore_function_coverage(temp_dirs):
    """Test the ignore function logic in collect_files_recursive."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml at source root
    (source_dir / "arboribus.toml").write_text("")

    # Create nested structure
    nested = source_dir / "nested"
    nested.mkdir()
    (nested / "tracked.py").write_text("content")
    (nested / "untracked.py").write_text("content")

    # Only track one file
    git_tracked = {"nested/tracked.py"}

    files = collect_files_recursive(source_dir, source_dir, git_tracked)
    relative_paths = {str(f.relative_to(source_dir)) for f in files}

    assert "nested/tracked.py" in relative_paths
    assert "nested/untracked.py" not in relative_paths


def test_complex_git_output_parsing(temp_dirs):
    """Test git output with complex whitespace."""
    source_dir, _ = temp_dirs

    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:
            # Complex output with whitespace
            return MagicMock(returncode=0, stdout="file1.py\n\n  \nfile2.txt\n   \n")

    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        assert result == {"file1.py", "file2.txt"}


def test_resolve_patterns_exact_git_match(temp_dirs):
    """Test resolve_patterns with exact git path match."""
    source_dir, _ = temp_dirs

    exact_dir = source_dir / "exact"
    exact_dir.mkdir()

    # Exact match in git tracking
    git_tracked = {"exact"}

    result = resolve_patterns(source_dir, ["exact"], git_tracked_files=git_tracked)
    assert len(result) == 1
    assert result[0].name == "exact"


def test_git_rev_parse_error(temp_dirs):
    """Test get_git_tracked_files when rev-parse fails."""
    source_dir, _ = temp_dirs

    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            # First command fails
            return MagicMock(returncode=1)
        else:
            return MagicMock(returncode=0, stdout="")

    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_resolve_patterns_directory_with_files(temp_dirs):
    """Test resolve_patterns when include_files=False but directory contains files."""
    source_dir, _ = temp_dirs

    # Create directory with files
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file1.py").write_text("content")
    (test_dir / "file2.py").write_text("content")

    # This should exercise the directory vs file handling logic
    result = resolve_patterns(source_dir, ["testdir"], include_files=False)
    assert len(result) == 1
    assert result[0].name == "testdir"


def test_collect_files_recursive_no_source_root(temp_dirs):
    """Test collect_files_recursive when no source root is found."""
    source_dir, _ = temp_dirs

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.py").write_text("content")

    # Don't create arboribus.toml - should use source_dir as source_root
    files = collect_files_recursive(test_dir, source_dir, git_tracked_files=None)
    assert len(files) >= 1


def test_get_file_statistics_with_directories(temp_dirs):
    """Test get_file_statistics when processing directories with git filtering."""
    source_dir, _ = temp_dirs

    # Create directory with files
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "tracked.py").write_text("content")
    (test_dir / "untracked.py").write_text("content")

    # Only track one file
    git_tracked = {"testdir/tracked.py"}

    stats = get_file_statistics([test_dir], source_dir, git_tracked)

    # Should only count tracked files
    assert stats["[TOTAL FILES]"] == 1
    assert ".py" in stats


def test_sync_directory_copytree_error_handling(temp_dirs):
    """Test sync_directory when copytree fails."""
    source_dir, target_dir = temp_dirs

    # Create source
    (source_dir / "file.txt").write_text("content")

    with patch("shutil.copytree", side_effect=OSError("Permission denied")):
        # Should re-raise the error (lines 188-189)
        with pytest.raises(OSError, match="Permission denied"):
            sync_directory(source_dir, target_dir, reverse=False, dry=False)


def test_ignore_function_edge_cases(temp_dirs):
    """Test the ignore function in sync_directory with complex edge cases."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml at source root
    (source_dir / "arboribus.toml").write_text("")

    # Create files directly in source
    (source_dir / "tracked.py").write_text("content")
    (source_dir / "untracked.py").write_text("content")

    # Git tracks only one file
    git_tracked = {"tracked.py"}

    # This should exercise the complex ignore function logic (lines 162-184)
    sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=git_tracked)

    # Should only copy tracked files
    assert (target_dir / "tracked.py").exists()
    # Untracked files should not be copied
    assert not (target_dir / "untracked.py").exists()


def test_ignore_function_exception_handling(temp_dirs):
    """Test ignore function exception handling in sync_directory."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.py").write_text("content")

    # Create a git_tracked_files set that will cause an error
    git_tracked = {"testdir/file.py"}

    # Mock Path.relative_to to raise an exception to test exception handling
    original_relative_to = Path.relative_to
    def mock_relative_to(self, other):
        if "arboribus.toml" in str(self):
            return original_relative_to(self, other)
        raise ValueError("Mock error")

    with patch.object(Path, "relative_to", side_effect=mock_relative_to):
        # Should handle exception gracefully (lines 181-183)
        sync_directory(test_dir, target_dir / "testdir", reverse=False, dry=False, git_tracked_files=git_tracked)

    # Should still copy files even when ignore function fails
    assert (target_dir / "testdir" / "file.py").exists()
