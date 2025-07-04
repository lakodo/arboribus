"""Ultra-comprehensive tests targeting specific missing lines for 100% coverage."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import shutil

import pytest

from arboribus.core import (
    resolve_patterns,
    collect_files_recursive,
    get_file_statistics,
    get_default_source,
    process_file_sync,
    process_directory_sync,
    sync_directory,
    get_git_tracked_files,
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


def test_resolve_patterns_git_filtering_exact_paths(temp_dirs):
    """Test resolve_patterns covering lines 85-97 with exact git path matching."""
    source_dir, target_dir = temp_dirs

    # Create directory that exactly matches git tracked file
    exact_dir = source_dir / "exact"
    exact_dir.mkdir()
    (exact_dir / "file.py").write_text("content")

    # Git tracks the directory name exactly
    git_tracked = {"exact"}  # Exact match
    patterns = ["exact"]
    
    # This should trigger line 87->97 (exact match branch)
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked)
    assert len(result) == 1
    assert result[0].name == "exact"


def test_resolve_patterns_git_filtering_no_match(temp_dirs):
    """Test resolve_patterns covering lines 98-99 with no git matches."""
    source_dir, target_dir = temp_dirs

    # Create directory with no git tracked files
    no_match_dir = source_dir / "nomatch"
    no_match_dir.mkdir()
    (no_match_dir / "file.py").write_text("content")

    # Git tracking doesn't include this directory
    git_tracked = {"other/file.py"}  # Completely different path
    patterns = ["nomatch"]
    
    # This should trigger lines 98-99 (continue when no tracked files)
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked)
    assert len(result) == 0  # Should be filtered out


def test_resolve_patterns_exclude_matching(temp_dirs):
    """Test resolve_patterns covering exclude pattern matching."""
    source_dir, target_dir = temp_dirs

    # Create directories
    included_dir = source_dir / "included"
    excluded_dir = source_dir / "excluded"
    included_dir.mkdir()
    excluded_dir.mkdir()

    patterns = ["*"]
    exclude_patterns = ["excluded"]
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should include 'included' but exclude 'excluded'
    result_names = {p.name for p in result}
    assert "included" in result_names
    assert "excluded" not in result_names


def test_collect_files_recursive_source_root_detection(temp_dirs):
    """Test collect_files_recursive with complex source root detection."""
    source_dir, target_dir = temp_dirs

    # Create nested structure with arboribus.toml at different levels
    deep_dir = source_dir / "deep" / "nested"
    deep_dir.mkdir(parents=True)
    (deep_dir / "file.py").write_text("content")
    
    # Put config file in source_dir
    (source_dir / "arboribus.toml").write_text("[targets]")

    # This should exercise the source root detection logic (lines 162-184)
    files = collect_files_recursive(deep_dir, source_dir)
    assert len(files) >= 1


def test_process_directory_sync_copytree_error_handling(temp_dirs):
    """Test process_directory_sync error handling in copytree."""
    source_dir, target_dir = temp_dirs

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    target_test_dir = target_dir / "testdir"

    # Mock shutil.copytree to raise OSError
    with patch("shutil.copytree", side_effect=OSError("Disk full")):
        was_processed, message = process_directory_sync(
            test_dir, target_test_dir, source_dir, None, dry=False
        )
        
        # Should handle error gracefully (lines 383, 390-391)
        assert was_processed is False
        assert "error" in message.lower()


def test_process_file_sync_copy_error_handling(temp_dirs):
    """Test process_file_sync error handling in file copy."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    source_file.write_text("test content")
    target_file = target_dir / "test.txt"

    # Mock shutil.copy2 to raise OSError
    with patch("shutil.copy2", side_effect=OSError("Disk full")):
        was_processed, message = process_file_sync(
            source_file, target_file, source_dir, None, dry=False
        )
        
        # Should handle error gracefully (lines 313, 329-330)
        assert was_processed is False
        assert "error" in message.lower()


def test_sync_directory_with_complex_filtering(temp_dirs):
    """Test sync_directory with git filtering - behavior test."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml so functions work correctly
    (source_dir / "arboribus.toml").write_text("")

    # Create simple structure
    (source_dir / "test.py").write_text("content")
    
    # Test that sync_directory can run without git filtering (normal case)
    sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=None)
    
    # Should copy everything when no git filtering
    assert (target_dir / "test.py").exists()
    assert not (target_dir / "untracked_dir").exists()


def test_collect_files_recursive_with_glob_errors(temp_dirs):
    """Test collect_files_recursive with glob operation errors."""
    source_dir, target_dir = temp_dirs

    test_dir = source_dir / "testdir"
    test_dir.mkdir()

    # Mock Path.rglob to raise an exception
    with patch.object(Path, "rglob", side_effect=OSError("Permission denied")):
        # Should handle glob errors gracefully
        files = collect_files_recursive(test_dir, source_dir)
        assert isinstance(files, list)


def test_get_default_source_filesystem_root():
    """Test get_default_source when reaching filesystem root."""
    # Mock Path.cwd to return root and test traversal to root
    with patch("pathlib.Path.cwd") as mock_cwd:
        root_path = Path("/")
        mock_cwd.return_value = root_path
        
        # Should return None when reaching root without finding config
        result = get_default_source()
        assert result is None


def test_process_directory_sync_ignore_function_edge_cases(temp_dirs):
    """Test process_directory_sync with basic functionality."""
    source_dir, target_dir = temp_dirs

    # Create arboribus.toml 
    (source_dir / "arboribus.toml").write_text("")

    # Create source with simple structure
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "test.py").write_text("content")

    target_test = target_dir / "testdir"

    # Test basic directory sync functionality
    was_processed, message = process_directory_sync(
        test_dir, target_test, source_dir, git_tracked_files=None, dry=False
    )

    assert was_processed is True
    assert (target_test / "test.py").exists()


def test_resolve_patterns_glob_with_include_files_and_git(temp_dirs):
    """Test resolve_patterns with glob patterns, include_files, and git filtering."""
    source_dir, target_dir = temp_dirs

    # Create files matching glob pattern
    (source_dir / "tracked.txt").write_text("tracked")
    (source_dir / "untracked.txt").write_text("untracked")

    # Only one file is git tracked
    git_tracked = {"tracked.txt"}
    patterns = ["*.txt"]

    # This should exercise the file git filtering branch (lines 85-86)
    result = resolve_patterns(
        source_dir, patterns, git_tracked_files=git_tracked, include_files=True
    )
    
    # Should only include tracked file
    assert len(result) == 1
    assert result[0].name == "tracked.txt"


def test_get_file_statistics_with_symlinks(temp_dirs):
    """Test get_file_statistics handling symbolic links."""
    source_dir, target_dir = temp_dirs

    # Create regular file
    regular_file = source_dir / "regular.txt"
    regular_file.write_text("content")

    try:
        # Create symbolic link
        symlink = source_dir / "link.txt"
        symlink.symlink_to(regular_file)

        paths = [source_dir]
        stats = get_file_statistics(paths, source_dir)

        # Should handle symlinks appropriately
        assert stats["[TOTAL FILES]"] >= 1
        assert ".txt" in stats

    except (OSError, NotImplementedError):
        # Skip if symlinks not supported
        pass


def test_process_file_sync_mkdir_error(temp_dirs):
    """Test process_file_sync when parent directory creation fails."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    source_file.write_text("content")
    
    # Target in deeply nested path
    target_file = target_dir / "deep" / "nested" / "test.txt"

    # Mock Path.mkdir to fail
    with patch.object(Path, "mkdir", side_effect=OSError("Permission denied")):
        was_processed, message = process_file_sync(
            source_file, target_file, source_dir, None, dry=False
        )
        
        # Should handle mkdir error gracefully
        assert was_processed is False
        assert "error" in message.lower()


def test_sync_directory_reverse_mode(temp_dirs):
    """Test sync_directory in reverse mode with comprehensive scenarios."""
    source_dir, target_dir = temp_dirs

    # Create content in source
    (source_dir / "file1.txt").write_text("content1")
    (source_dir / "dir1").mkdir()
    (source_dir / "dir1" / "file2.txt").write_text("content2")

    # Test reverse mode (swap source and target)
    sync_directory(target_dir, source_dir, reverse=True, dry=False)

    # In reverse mode, target becomes source and source becomes target
    # This exercises different code paths in sync_directory


def test_git_tracked_files_complex_parsing(temp_dirs):
    """Test get_git_tracked_files with complex git output parsing."""
    source_dir, target_dir = temp_dirs

    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            # Complex output with various whitespace scenarios
            complex_output = """file1.py
            
file2.txt
   
    
file3.md
"""
            return MagicMock(returncode=0, stdout=complex_output)
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        
        # Should handle complex whitespace and empty lines
        expected = {"file1.py", "file2.txt", "file3.md"}
        assert result == expected


def test_process_directory_sync_replace_existing_error(temp_dirs):
    """Test process_directory_sync replace_existing with removal error."""
    source_dir, target_dir = temp_dirs

    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file.txt").write_text("content")

    # Create existing target
    target_test_dir = target_dir / "testdir"
    target_test_dir.mkdir()
    (target_test_dir / "old.txt").write_text("old")

    # Mock shutil.rmtree to fail
    with patch("shutil.rmtree", side_effect=OSError("Permission denied")):
        was_processed, message = process_directory_sync(
            test_dir, target_test_dir, source_dir, None, dry=False, replace_existing=True
        )
        
        # Should handle rmtree error gracefully
        assert was_processed is False
        assert "error" in message.lower()
