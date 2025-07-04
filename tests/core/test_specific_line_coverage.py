"""Final comprehensive tests to achieve 100% core module coverage."""

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


def test_git_lines_78_to_105_edge_case(temp_dirs):
    """Test git tracked files with edge case that covers lines 78->105."""
    source_dir, _ = temp_dirs
    
    # Mock git rev-parse to succeed but ls-files to fail with different error
    def mock_run_special_case(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:  # ls-files command
            # This should trigger line 85->97 by raising CalledProcessError
            raise subprocess.CalledProcessError(1, cmd)
    
    with patch("subprocess.run", side_effect=mock_run_special_case):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_git_lines_85_to_97_specific_branch(temp_dirs):
    """Test specific branch in git tracking lines 85->97."""
    source_dir, _ = temp_dirs
    
    # Mock both commands to succeed but test specific path through lines 85->97
    def mock_run_success_path(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        else:  # ls-files
            # Return minimal output to test the success path but cover line 87->97
            return MagicMock(returncode=0, stdout="file1.py\nfile2.py\n")
    
    with patch("subprocess.run", side_effect=mock_run_success_path):
        result = get_git_tracked_files(source_dir)
        expected = {"file1.py", "file2.py"}
        assert result == expected


def test_resolve_patterns_lines_98_99_direct_path_git_filtering(temp_dirs):
    """Test resolve_patterns lines 98-99 for direct path git filtering."""
    source_dir, _ = temp_dirs
    
    # Create a direct file that matches pattern exactly
    (source_dir / "frontend").write_text("content")
    
    # Test with git filtering where the direct path file is NOT tracked
    git_tracked = {"other/file.py"}  # Doesn't include "frontend"
    
    # Use exact pattern "frontend" to trigger direct path matching (line ~78)
    # but with git filtering that excludes it (should reach lines 98-99)
    result = resolve_patterns(source_dir, ["frontend"], git_tracked_files=git_tracked, include_files=True)
    
    # The file should be filtered out by git tracking
    assert len(result) == 0


def test_resolve_patterns_lines_109_to_112_directory_git_check(temp_dirs):
    """Test resolve_patterns lines 109->112 for directory git filtering."""
    source_dir, _ = temp_dirs
    
    # Create a directory with the exact pattern name
    (source_dir / "backend").mkdir()
    (source_dir / "backend" / "app.py").write_text("content")
    
    # Git tracks files but not in this directory
    git_tracked = {"frontend/file.py", "other/app.py"}  # No files in backend/
    
    # Use exact pattern "backend" to trigger direct path matching for directory
    # but with git filtering that should exclude it (lines 109->112)
    result = resolve_patterns(source_dir, ["backend"], git_tracked_files=git_tracked, include_files=False)
    
    # Directory should be filtered out since it has no tracked files
    assert len(result) == 0


def test_resolve_patterns_lines_125_to_135_include_files_logic(temp_dirs):
    """Test resolve_patterns lines 125->135 for include_files logic in glob matching."""
    source_dir, _ = temp_dirs
    
    # Create both file and directory that match glob pattern
    (source_dir / "test.py").write_text("content")
    (source_dir / "test_dir").mkdir()
    
    # Test with include_files=False (should only include directories)
    result = resolve_patterns(source_dir, ["test*"], include_files=False)
    result_names = {p.name for p in result}
    
    # Should include directory but logic about files is in lines 125->135
    assert "test_dir" in result_names
    # File inclusion depends on the glob behavior, this tests the logic path


def test_ignore_function_lines_168_to_173_exception_handling(temp_dirs):
    """Test ignore function lines 168->173 for exception handling."""
    source_dir, target_dir = temp_dirs
    
    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")
    
    # Create test file
    test_file = source_dir / "test.py"
    test_file.write_text("content")
    
    git_tracked = {"test.py"}
    
    # Mock is_relative_to to raise exception (line 168->173)
    original_is_relative_to = Path.is_relative_to
    def mock_is_relative_to_exception(self, other):
        if "test.py" in str(self):
            raise OSError("Mock filesystem error")
        return original_is_relative_to(self, other)
    
    with patch.object(Path, "is_relative_to", side_effect=mock_is_relative_to_exception):
        # This should trigger exception handling in ignore function
        sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=git_tracked)
        
        # File should still be copied despite exception
        assert (target_dir / "test.py").exists()


def test_process_file_sync_line_229_to_219_checksum_branch(temp_dirs):
    """Test process_file_sync line 229->219 for checksum comparison branch."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    
    # Create source file
    source_file.write_text("original content")
    
    # Create target file with DIFFERENT content
    target_file.write_text("different content")
    
    # This should trigger the checksum comparison and reach line 229->219
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False, replace_existing=True
    )
    
    assert was_processed
    assert "replaced" in message
    assert target_file.read_text() == "original content"


def test_process_file_sync_lines_309_313_complex_mkdir(temp_dirs):
    """Test process_file_sync lines 309, 313 for complex path creation."""
    source_dir, target_dir = temp_dirs
    
    # Create source file
    source_file = source_dir / "test.txt"
    source_file.write_text("content")
    
    # Target with deeply nested path that doesn't exist
    deep_target = target_dir / "very" / "deep" / "nested" / "path" / "test.txt"
    
    # This should trigger line 309 and 313 for mkdir logic
    was_processed, message = process_file_sync(
        source_file, deep_target, source_dir, None, dry=False
    )
    
    assert was_processed
    assert deep_target.exists()
    assert deep_target.read_text() == "content"


def test_get_default_source_lines_385_to_382_389_traversal(temp_dirs):
    """Test get_default_source lines 385->382, 389 for parent traversal."""
    source_dir, _ = temp_dirs
    
    # Create nested structure
    deep_path = source_dir / "level1" / "level2" / "level3"
    deep_path.mkdir(parents=True)
    
    # Place config at intermediate level
    config_path = source_dir / "level1" / "arboribus.toml"
    config_path.write_text("")
    
    # Mock cwd to be at the deep level
    with patch("pathlib.Path.cwd", return_value=deep_path):
        result = get_default_source()
        # Should find config at level1 and return that path (line 385->382)
        assert result == source_dir / "level1"


def test_get_default_source_line_389_no_config_found():
    """Test get_default_source line 389 when no config is found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a clean directory with no arboribus.toml anywhere
        test_path = Path(temp_dir) / "clean"
        test_path.mkdir()
        
        # Mock cwd to be in this clean directory
        with patch("pathlib.Path.cwd", return_value=test_path):
            # This should traverse up to filesystem root and return None (line 389)
            result = get_default_source()
            assert result is None


def test_resolve_patterns_glob_edge_case_include_files_branch(temp_dirs):
    """Test resolve_patterns glob matching with include_files edge case."""
    source_dir, _ = temp_dirs
    
    # Create files that will be matched by glob
    (source_dir / "match1.py").write_text("content")
    (source_dir / "match2.py").write_text("content")
    (source_dir / "nomatch.txt").write_text("content")
    
    # Use a glob pattern and test the include_files logic in glob section
    result = resolve_patterns(source_dir, ["*.py"], include_files=True)
    result_names = {p.name for p in result}
    
    assert "match1.py" in result_names
    assert "match2.py" in result_names
    assert "nomatch.txt" not in result_names


def test_resolve_patterns_recursive_glob_branch(temp_dirs):
    """Test resolve_patterns recursive glob branch."""
    source_dir, _ = temp_dirs
    
    # Create nested structure
    nested = source_dir / "subdir"
    nested.mkdir()
    (nested / "deep.py").write_text("content")
    
    # Use a recursive pattern to trigger the recursive glob logic
    result = resolve_patterns(source_dir, ["**/*.py"], include_files=True)
    result_names = {p.name for p in result}
    
    assert "deep.py" in result_names


def test_collect_files_recursive_edge_case_source_root_detection(temp_dirs):
    """Test collect_files_recursive source root detection edge case."""
    source_dir, _ = temp_dirs
    
    # Create arboribus.toml at a specific level
    (source_dir / "arboribus.toml").write_text("")
    
    # Create nested structure
    nested = source_dir / "project"
    nested.mkdir()
    (nested / "file.py").write_text("content")
    
    # Call with the nested directory and source_dir provided
    files = collect_files_recursive(nested, source_dir)
    
    # Should find files and determine correct source root
    assert len(files) >= 1
    assert any(f.name == "file.py" for f in files)


def test_sync_directory_various_edge_branches(temp_dirs):
    """Test various edge branches in sync_directory."""
    source_dir, target_dir = temp_dirs
    
    # Test dry=True early return
    (source_dir / "test.txt").write_text("content")
    
    # Call with dry=True - should return early and not copy anything
    sync_directory(source_dir, target_dir, reverse=False, dry=True)
    
    # Nothing should be copied
    assert not (target_dir / "test.txt").exists()
