"""Extreme edge case tests to push core coverage to maximum."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from arboribus.core import (
    get_git_tracked_files,
    resolve_patterns,
    collect_files_recursive,
    get_file_statistics,
    process_file_sync,
    process_directory_sync,
    sync_directory,
    get_default_source,
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


def test_git_tracked_files_rev_parse_failure(temp_dirs):
    """Test get_git_tracked_files when git rev-parse fails (lines 78->105)."""
    source_dir, _ = temp_dirs
    
    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            # First call fails - not a git repo
            return MagicMock(returncode=1)
        else:
            return MagicMock(returncode=0, stdout="file.py")
    
    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        # Should return None when not a git repo
        assert result is None


def test_git_tracked_files_ls_files_failure(temp_dirs):
    """Test get_git_tracked_files when git ls-files fails (lines 85->97)."""
    source_dir, _ = temp_dirs
    
    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            # First call succeeds
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            # Second call fails
            return MagicMock(returncode=1, stdout="")
        return MagicMock(returncode=1)
    
    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        # Should return None when ls-files fails
        assert result is None


def test_git_tracked_files_empty_repo(temp_dirs):
    """Test get_git_tracked_files with empty git repo (lines 98-99)."""
    source_dir, _ = temp_dirs
    
    def mock_run(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            # Empty git repo
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=1)
    
    with patch("subprocess.run", side_effect=mock_run):
        result = get_git_tracked_files(source_dir)
        # Should return empty set for empty repo
        assert result == set()


def test_resolve_patterns_glob_no_matches(temp_dirs):
    """Test resolve_patterns when glob patterns don't match (lines 109->112)."""
    source_dir, _ = temp_dirs
    
    # Create some files
    (source_dir / "test.py").write_text("content")
    (source_dir / "other.txt").write_text("content")
    
    # Use patterns that won't match anything
    patterns = ["*.xyz", "missing/**", "nonexistent/*"]
    result = resolve_patterns(source_dir, patterns)
    
    # Should return empty when nothing matches
    assert len(result) == 0


def test_resolve_patterns_exclude_all_matches(temp_dirs):
    """Test resolve_patterns when exclude patterns match everything (lines 116->112)."""
    source_dir, _ = temp_dirs
    
    # Create files
    (source_dir / "file1.txt").write_text("content")
    (source_dir / "file2.txt").write_text("content")
    
    # Include all but exclude all
    patterns = ["*.txt"]
    exclude_patterns = ["*.txt"]  # Exclude everything we include
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should return empty when everything is excluded
    assert len(result) == 0


def test_resolve_patterns_file_vs_directory_precedence(temp_dirs):
    """Test resolve_patterns file vs directory handling (lines 125->135)."""
    source_dir, _ = temp_dirs
    
    # Create both file and directory with overlapping names
    (source_dir / "test").write_text("content")  # File named 'test'
    test_dir = source_dir / "test_dir"           # Directory
    test_dir.mkdir()
    (test_dir / "nested.py").write_text("content")
    
    # Test with include_files=False (default) - should only match directories
    patterns = ["test*"]
    result = resolve_patterns(source_dir, patterns, include_files=False)
    
    # Should only include directory, not file
    result_names = {p.name for p in result}
    assert "test_dir" in result_names
    assert "test" not in result_names  # File excluded when include_files=False


def test_collect_files_recursive_permission_error(temp_dirs):
    """Test collect_files_recursive with permission errors during glob."""
    source_dir, _ = temp_dirs
    
    test_dir = source_dir / "restricted"
    test_dir.mkdir()
    (test_dir / "file.py").write_text("content")
    
    # Mock rglob to raise PermissionError
    with patch.object(Path, "rglob", side_effect=PermissionError("Access denied")):
        files = collect_files_recursive(test_dir, source_dir)
        # Should handle error gracefully and return empty list
        assert files == []


def test_ignore_function_source_root_not_found(temp_dirs):
    """Test ignore function when source root detection fails (lines 168->173)."""
    source_dir, target_dir = temp_dirs
    
    # Don't create arboribus.toml - source root won't be found properly
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.py").write_text("content")
    
    # Test without git filtering to ensure basic functionality works
    sync_directory(test_dir, target_dir / "testdir", reverse=False, dry=False, git_tracked_files=None)
    
    # Should copy files when no git filtering is applied
    assert (target_dir / "testdir" / "file.py").exists()


def test_ignore_function_relative_path_error(temp_dirs):
    """Test ignore function when relative path calculation fails (lines 176->173)."""
    source_dir, target_dir = temp_dirs
    
    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")
    
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.py").write_text("content")
    
    # Mock is_relative_to to return False to trigger the relative path error
    with patch.object(Path, "is_relative_to", return_value=False):
        # Should handle case where file path is not relative to source root
        sync_directory(test_dir, target_dir / "testdir", reverse=False, dry=False, git_tracked_files={"testdir/file.py"})
    
    # Should still copy files even when relative path calculation fails
    assert (target_dir / "testdir" / "file.py").exists()


def test_get_file_statistics_directory_with_git_filtering(temp_dirs):
    """Test get_file_statistics with directory processing and git filtering (lines 229->219)."""
    source_dir, _ = temp_dirs
    
    # Create directory with mixed content
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "tracked.py").write_text("content")
    (test_dir / "untracked.py").write_text("content")
    (test_dir / "tracked.js").write_text("content")
    
    # Git only tracks specific files
    git_tracked = {"testdir/tracked.py", "testdir/tracked.js"}
    
    # Process directory with git filtering
    stats = get_file_statistics([test_dir], source_dir, git_tracked)
    
    # Should only count git-tracked files
    assert stats["[TOTAL FILES]"] == 2
    assert stats[".py"] == 1
    assert stats[".js"] == 1
    assert stats["[TOTAL DIRS]"] == 1


def test_process_file_sync_complex_path_creation(temp_dirs):
    """Test process_file_sync with complex nested path creation (lines 309, 313)."""
    source_dir, target_dir = temp_dirs
    
    # Create very deep source structure
    deep_source = source_dir / "a" / "b" / "c" / "d" / "e"
    deep_source.mkdir(parents=True)
    source_file = deep_source / "deep.txt"
    source_file.write_text("deep content")
    
    # Target with different deep structure
    deep_target = target_dir / "x" / "y" / "z"
    target_file = deep_target / "deep.txt"
    
    # This exercises complex path calculation and creation
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )
    
    assert was_processed
    assert target_file.exists()
    assert target_file.read_text() == "deep content"


def test_get_default_source_traversal_to_root(temp_dirs):
    """Test get_default_source traversal to filesystem root (lines 385->382, 389)."""
    source_dir, _ = temp_dirs
    
    # Create nested directory structure without arboribus.toml
    deep_dir = source_dir / "a" / "b" / "c"
    deep_dir.mkdir(parents=True)
    
    # Mock Path.cwd to return the deep directory
    with patch("pathlib.Path.cwd", return_value=deep_dir):
        # Mock exists to never find arboribus.toml
        with patch.object(Path, "exists", return_value=False):
            result = get_default_source()
            # Should return None when traversing to root without finding config
            assert result is None


def test_sync_directory_dry_run_early_return(temp_dirs):
    """Test sync_directory dry run early return."""
    source_dir, target_dir = temp_dirs
    
    # Create source content
    (source_dir / "file.txt").write_text("content")
    
    # Test dry run - should return early without doing anything
    sync_directory(source_dir, target_dir, reverse=False, dry=True)
    
    # Nothing should be copied in dry run
    assert not (target_dir / "file.txt").exists()


def test_process_file_sync_dry_run_mode(temp_dirs):
    """Test process_file_sync in dry run mode."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    source_file.write_text("content")
    target_file = target_dir / "test.txt"
    
    # Test dry run
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=True
    )
    
    assert was_processed
    assert "would copy" in message.lower()
    assert not target_file.exists()  # No actual copy in dry run


def test_process_directory_sync_dry_run_mode(temp_dirs):
    """Test process_directory_sync in dry run mode."""
    source_dir, target_dir = temp_dirs
    
    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")
    
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")
    
    target_test = target_dir / "testdir"
    
    # Test dry run
    was_processed, message = process_directory_sync(
        test_dir, target_test, source_dir, None, dry=True
    )
    
    assert was_processed
    assert "would sync" in message.lower()  # Correct message text
    assert not target_test.exists()  # No actual copy in dry run
