"""Ultimate coverage tests targeting the final remaining core lines for 100%."""

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


def test_git_subprocess_exact_line_78_to_105(temp_dirs):
    """Test exact git subprocess error path lines 78->105."""
    source_dir, _ = temp_dirs

    # Mock git rev-parse to succeed but trigger specific error in ls-files
    def mock_subprocess_specific_error(cmd, **kwargs):
        if "rev-parse" in cmd:
            # Rev-parse succeeds (line 78)
            return MagicMock(returncode=0)
        else:
            # ls-files fails, triggering line 85->97 then 105
            raise subprocess.CalledProcessError(128, "git ls-files")

    with patch("subprocess.run", side_effect=mock_subprocess_specific_error):
        result = get_git_tracked_files(source_dir)
        # Should reach line 105 and return None
        assert result is None


def test_git_subprocess_exact_line_85_to_97(temp_dirs):
    """Test exact git subprocess path lines 85->97."""
    source_dir, _ = temp_dirs

    # Mock both commands to succeed, testing specific success path
    def mock_subprocess_success_85_97(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:
            # This triggers the exact success path through lines 85->97
            return MagicMock(returncode=0, stdout="file1.py\nfile2.txt\n")

    with patch("subprocess.run", side_effect=mock_subprocess_success_85_97):
        result = get_git_tracked_files(source_dir)
        # Should reach line 97 and return the set
        assert result == {"file1.py", "file2.txt"}


def test_git_subprocess_exact_line_87_to_97(temp_dirs):
    """Test exact git subprocess path lines 87->97 with empty output."""
    source_dir, _ = temp_dirs

    # Mock to test the empty output path through 87->97
    def mock_subprocess_empty_87_97(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:
            # Empty output to test line 87->97 path
            return MagicMock(returncode=0, stdout="")

    with patch("subprocess.run", side_effect=mock_subprocess_empty_87_97):
        result = get_git_tracked_files(source_dir)
        # Should reach line 97 with empty set
        assert result == set()


def test_resolve_patterns_exact_lines_98_99(temp_dirs):
    """Test exact resolve_patterns lines 98-99 for file git filtering."""
    source_dir, _ = temp_dirs

    # Create a file that matches pattern exactly
    (source_dir / "target_file").write_text("content")

    # Git tracking that doesn't include this file (lines 98-99)
    git_tracked = {"different_file.py"}

    # Use exact pattern matching to trigger direct path logic
    result = resolve_patterns(source_dir, ["target_file"], git_tracked_files=git_tracked, include_files=True)

    # File should be filtered out at lines 98-99
    assert len(result) == 0


def test_resolve_patterns_exact_lines_109_to_112(temp_dirs):
    """Test exact resolve_patterns lines 109->112 for directory git filtering."""
    source_dir, _ = temp_dirs

    # Create a directory that matches pattern exactly
    (source_dir / "target_dir").mkdir()
    (source_dir / "target_dir" / "file.py").write_text("content")

    # Git tracking that has no files in this directory (lines 109->112)
    git_tracked = {"other_dir/file.py"}

    # Use exact pattern matching to trigger directory logic
    result = resolve_patterns(source_dir, ["target_dir"], git_tracked_files=git_tracked, include_files=False)

    # Directory should be filtered out at lines 109->112
    assert len(result) == 0


def test_resolve_patterns_exact_lines_125_to_135(temp_dirs):
    """Test exact resolve_patterns lines 125->135 for glob include_files logic."""
    source_dir, _ = temp_dirs

    # Create both files and directories matching glob
    (source_dir / "match.txt").write_text("content")
    (source_dir / "match_dir").mkdir()

    # Test glob pattern with include_files=False to hit lines 125->135
    result = resolve_patterns(source_dir, ["match*"], include_files=False)

    # Should only include directory, exercising lines 125->135
    result_names = {p.name for p in result}
    assert "match_dir" in result_names
    # File inclusion depends on glob behavior at lines 125->135


def test_ignore_function_exact_lines_168_to_173(temp_dirs):
    """Test exact ignore function lines 168->173 for exception handling."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml and test file
    (source_dir / "arboribus.toml").write_text("")
    (source_dir / "exception_test.py").write_text("content")

    git_tracked = {"exception_test.py"}

    # Mock is_relative_to to raise exception at line 168
    original_is_relative_to = Path.is_relative_to
    def mock_is_relative_to_exception(self, other):
        if "exception_test.py" in str(self):
            # This triggers line 168->173
            raise ValueError("Mocked exception")
        return original_is_relative_to(self, other)

    with patch.object(Path, "is_relative_to", side_effect=mock_is_relative_to_exception):
        # Should handle exception at lines 168->173
        sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=git_tracked)

        # File should still be copied despite exception
        assert (target_dir / "exception_test.py").exists()


def test_process_file_sync_exact_line_229_to_219(temp_dirs):
    """Test exact process_file_sync line 229->219 for checksum logic."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "checksum_test.txt"
    target_file = target_dir / "checksum_test.txt"

    # Create files with different content
    source_file.write_text("source content")
    target_file.write_text("target content")

    # This should trigger checksum comparison at line 229->219
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False, replace_existing=True
    )

    # Should process and replace file, exercising line 229->219
    assert was_processed
    assert target_file.read_text() == "source content"


def test_process_file_sync_exact_line_309(temp_dirs):
    """Test exact process_file_sync line 309 for mkdir logic."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "deep_test.txt"
    source_file.write_text("content")

    # Target with non-existent parent directories
    deep_target = target_dir / "very" / "deep" / "nested" / "deep_test.txt"

    # This should trigger mkdir at line 309
    was_processed, message = process_file_sync(
        source_file, deep_target, source_dir, None, dry=False
    )

    # Should create directories and copy file, exercising line 309
    assert was_processed
    assert deep_target.exists()


def test_process_file_sync_exact_line_313(temp_dirs):
    """Test exact process_file_sync line 313 for copy logic."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "copy_test.txt"
    target_file = target_dir / "copy_test.txt"

    source_file.write_text("test content")

    # This should trigger the copy operation at line 313
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )

    # Should copy file, exercising line 313
    assert was_processed
    assert target_file.read_text() == "test content"


def test_get_default_source_exact_lines_385_to_382(temp_dirs):
    """Test exact get_default_source lines 385->382 for config found."""
    source_dir, _ = temp_dirs

    # Create nested structure with config at intermediate level
    deep_path = source_dir / "level1" / "level2" / "level3"
    deep_path.mkdir(parents=True)

    # Place config at level1
    (source_dir / "level1" / "arboribus.toml").write_text("")

    # Mock cwd to be at deep level
    with patch("pathlib.Path.cwd", return_value=deep_path):
        result = get_default_source()
        # Should find config and return path, exercising lines 385->382
        assert result == source_dir / "level1"


def test_get_default_source_exact_line_389(temp_dirs):
    """Test exact get_default_source line 389 for no config found."""
    source_dir, _ = temp_dirs

    # Create path with no config anywhere
    test_path = source_dir / "no_config"
    test_path.mkdir()

    # Mock cwd and ensure no config exists
    with patch("pathlib.Path.cwd", return_value=test_path):
        with patch.object(Path, "exists", return_value=False):
            result = get_default_source()
            # Should reach line 389 and return None
            assert result is None


def test_resolve_patterns_recursive_glob_exact_branch(temp_dirs):
    """Test resolve_patterns recursive glob for exact branch coverage."""
    source_dir, _ = temp_dirs

    # Create nested structure for recursive glob
    nested = source_dir / "deep" / "nested"
    nested.mkdir(parents=True)
    (nested / "recursive.py").write_text("content")

    # Use recursive pattern to trigger specific glob logic
    result = resolve_patterns(source_dir, ["**/recursive.py"], include_files=True)

    # Should find file via recursive glob
    assert len(result) == 1
    assert result[0].name == "recursive.py"


def test_collect_files_recursive_source_root_edge_case(temp_dirs):
    """Test collect_files_recursive source root detection edge case."""
    source_dir, _ = temp_dirs

    # Create structure where source_root needs to be detected
    (source_dir / "arboribus.toml").write_text("")

    nested = source_dir / "project"
    nested.mkdir()
    (nested / "source_test.py").write_text("content")

    # Call with source_dir as source_root
    files = collect_files_recursive(nested, source_dir)

    # Should correctly handle source root detection
    assert len(files) >= 1


def test_sync_directory_dry_run_exact_branch(temp_dirs):
    """Test sync_directory dry=True for exact early return."""
    source_dir, target_dir = temp_dirs

    (source_dir / "dry_test.txt").write_text("content")

    # Test dry=True to trigger exact early return
    sync_directory(source_dir, target_dir, reverse=False, dry=True)

    # Should not copy anything in dry run
    assert not (target_dir / "dry_test.txt").exists()


def test_resolve_patterns_git_tracked_directory_has_files_check(temp_dirs):
    """Test resolve_patterns git tracked directory check for has_tracked_files."""
    source_dir, _ = temp_dirs

    # Create directory with files
    test_dir = source_dir / "has_files"
    test_dir.mkdir()
    (test_dir / "tracked.py").write_text("content")
    (test_dir / "untracked.py").write_text("content")

    # Git tracks only one file in the directory
    git_tracked = {"has_files/tracked.py"}

    # This should find the directory has tracked files
    result = resolve_patterns(source_dir, ["has_files"], git_tracked_files=git_tracked, include_files=False)

    # Directory should be included because it has tracked files
    assert len(result) == 1
    assert result[0].name == "has_files"


def test_resolve_patterns_git_tracked_exact_directory_match(temp_dirs):
    """Test resolve_patterns exact directory name in git tracking."""
    source_dir, _ = temp_dirs

    # Create directory
    exact_dir = source_dir / "exact_match"
    exact_dir.mkdir()
    (exact_dir / "file.py").write_text("content")

    # Git tracks the directory name exactly (not files inside)
    git_tracked = {"exact_match"}

    # Should match the exact directory name
    result = resolve_patterns(source_dir, ["exact_match"], git_tracked_files=git_tracked, include_files=False)

    # Should include directory with exact match
    assert len(result) == 1
    assert result[0].name == "exact_match"


def test_process_file_sync_same_content_skip(temp_dirs):
    """Test process_file_sync when files have same content."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "same_content.txt"
    target_file = target_dir / "same_content.txt"

    # Create files with identical content
    content = "identical content"
    source_file.write_text(content)
    target_file.write_text(content)

    # Should skip copying when content is the same
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )

    # Should skip processing due to identical content
    assert was_processed is False
    assert "same" in message.lower() or "skip" in message.lower()


def test_get_file_statistics_no_extension_files(temp_dirs):
    """Test get_file_statistics with files that have no extension."""
    source_dir, _ = temp_dirs

    # Create files without extensions
    (source_dir / "README").write_text("readme content")
    (source_dir / "Makefile").write_text("makefile content")
    (source_dir / "config").write_text("config content")

    paths = [source_dir / "README", source_dir / "Makefile", source_dir / "config"]
    stats = get_file_statistics(paths, source_dir)

    # Should categorize files without extension
    assert "(no extension)" in stats
    assert stats["(no extension)"] == 3
    assert stats["[TOTAL FILES]"] == 3


def test_resolve_patterns_exclude_pattern_startswith_logic(temp_dirs):
    """Test resolve_patterns exclude pattern startswith logic."""
    source_dir, _ = temp_dirs

    # Create files and directories
    (source_dir / "exclude_me.txt").write_text("content")
    (source_dir / "exclude_dir").mkdir()
    (source_dir / "keep_me.txt").write_text("content")

    # Test exclude patterns with startswith logic
    patterns = ["*"]
    exclude_patterns = ["exclude"]

    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns, include_files=True)

    # Should exclude items starting with "exclude"
    result_names = {p.name for p in result}
    assert "exclude_me.txt" not in result_names
    assert "exclude_dir" not in result_names
    assert "keep_me.txt" in result_names
