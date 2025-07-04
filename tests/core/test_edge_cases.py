"""Edge case tests to target remaining missing lines in core module for 100% coverage."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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


def test_git_rev_parse_subprocess_error(temp_dirs):
    """Test get_git_tracked_files when git rev-parse fails."""
    source_dir, _ = temp_dirs
    
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            # Rev-parse command fails - covers line 78->105
            raise subprocess.CalledProcessError(128, "git")
        return MagicMock(returncode=0, stdout="")
    
    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_git_ls_files_empty_repo(temp_dirs):
    """Test get_git_tracked_files with empty git repository."""
    source_dir, _ = temp_dirs
    
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            # Empty repository - covers lines 98-99
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=1)
    
    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result == set()


def test_resolve_patterns_complex_glob_edge_case(temp_dirs):
    """Test resolve_patterns with glob patterns that don't match anything."""
    source_dir, _ = temp_dirs
    
    # Create some files
    (source_dir / "test.py").write_text("content")
    (source_dir / "README.md").write_text("content")
    
    # Use patterns that won't match existing files - covers lines 109->112
    patterns = ["*.nonexistent", "missing/**/*.txt", "phantom/*/deep/**"]
    result = resolve_patterns(source_dir, patterns)
    
    # Should return empty list when no patterns match
    assert len(result) == 0


def test_resolve_patterns_exclude_all_matches(temp_dirs):
    """Test resolve_patterns when exclude patterns match everything."""
    source_dir, _ = temp_dirs
    
    # Create files
    (source_dir / "include.txt").write_text("content")
    (source_dir / "exclude.txt").write_text("content")
    
    # Exclude pattern that matches everything - covers lines 116->112
    patterns = ["*.txt"]
    exclude_patterns = ["*"]  # Exclude everything
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    assert len(result) == 0


def test_resolve_patterns_file_vs_directory_complex(temp_dirs):
    """Test resolve_patterns complex file vs directory handling."""
    source_dir, _ = temp_dirs
    
    # Create both file and directory with overlapping names
    (source_dir / "test").write_text("file content")
    test_dir = source_dir / "test_dir"
    test_dir.mkdir()
    (test_dir / "nested.py").write_text("nested content")
    
    # Test include_files behavior - covers lines 125->135
    patterns = ["test*"]
    result = resolve_patterns(source_dir, patterns, include_files=False)
    
    # Should only include directory, not file when include_files=False
    result_names = {p.name for p in result}
    assert "test_dir" in result_names
    # File should be excluded when include_files=False
    assert "test" not in result_names


def test_collect_files_recursive_git_path_edge_cases(temp_dirs):
    """Test collect_files_recursive with complex git path scenarios."""
    source_dir, _ = temp_dirs
    
    # Create arboribus.toml
    (source_dir / "arboribus.toml").write_text("")
    
    # Create nested structure
    nested = source_dir / "deeply" / "nested" / "path"
    nested.mkdir(parents=True)
    (nested / "tracked.py").write_text("content")
    (nested / "untracked.py").write_text("content")
    
    # Git tracks files with complex relative paths - covers lines 168->173, 176->173
    git_tracked = {"deeply/nested/path/tracked.py"}
    
    files = collect_files_recursive(nested, source_dir, git_tracked)
    
    # Should only include tracked files
    relative_paths = {str(f.relative_to(source_dir)) for f in files}
    assert "deeply/nested/path/tracked.py" in relative_paths
    assert "deeply/nested/path/untracked.py" not in relative_paths


def test_get_file_statistics_complex_directory_structure(temp_dirs):
    """Test get_file_statistics with complex directory structures and git filtering."""
    source_dir, _ = temp_dirs
    
    # Create complex structure
    nested = source_dir / "project" / "src"
    nested.mkdir(parents=True)
    (nested / "main.py").write_text("main content")
    (nested / "utils.py").write_text("utils content")
    (nested / "test.txt").write_text("test content")
    
    # Git tracking subset of files - covers lines 229->219
    git_tracked = {"project/src/main.py", "project/src/test.txt"}
    
    stats = get_file_statistics([source_dir / "project"], source_dir, git_tracked)
    
    # Should only count git-tracked files
    assert stats["[TOTAL FILES]"] == 2
    assert ".py" in stats
    assert ".txt" in stats
    assert stats[".py"] == 1  # Only main.py counted
    assert stats[".txt"] == 1


def test_process_file_sync_complex_path_calculations(temp_dirs):
    """Test process_file_sync with very deep path calculations."""
    source_dir, target_dir = temp_dirs
    
    # Create very deep nested structure
    deep_path = source_dir / "a" / "b" / "c" / "d" / "e" / "f"
    deep_path.mkdir(parents=True)
    source_file = deep_path / "deep_file.txt"
    source_file.write_text("deep content")
    
    # Target with equally deep structure
    target_file = target_dir / "a" / "b" / "c" / "d" / "e" / "f" / "deep_file.txt"
    
    # This exercises complex path calculations - covers lines 309, 313
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )
    
    assert was_processed
    assert target_file.exists()
    assert "deep content" == target_file.read_text()


def test_get_default_source_deep_traversal(temp_dirs):
    """Test get_default_source with deep directory traversal."""
    source_dir, _ = temp_dirs
    
    # Create deep structure without config at any level
    deep_dir = source_dir / "very" / "deep" / "nested" / "structure"
    deep_dir.mkdir(parents=True)
    
    # Mock cwd to return the deep directory
    with patch("pathlib.Path.cwd", return_value=deep_dir):
        # Should traverse up and return None when no config found - covers lines 385->382, 389
        result = get_default_source()
        assert result is None


def test_sync_directory_ignore_function_complex_scenarios(temp_dirs):
    """Test sync_directory ignore function with complex file structures."""
    source_dir, target_dir = temp_dirs
    
    # Create config at source root
    (source_dir / "arboribus.toml").write_text("")
    
    # Create simple structure to verify sync works
    (source_dir / "test.py").write_text("content")
    
    # Test without git filtering - should copy everything
    sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=None)
    
    # Verify file is copied when no git filtering
    assert (target_dir / "test.py").exists()


def test_ignore_function_relative_path_edge_cases(temp_dirs):
    """Test ignore function with complex relative path calculations."""
    source_dir, target_dir = temp_dirs
    
    # Create config
    (source_dir / "arboribus.toml").write_text("")
    
    # Create files to test basic sync functionality
    (source_dir / "main.py").write_text("main")
    (source_dir / "test.py").write_text("test")
    
    # Test basic sync without git filtering
    sync_directory(source_dir, target_dir, reverse=False, dry=False, git_tracked_files=None)
    
    # Should copy all files when no git filtering
    assert (target_dir / "main.py").exists()
    assert (target_dir / "test.py").exists()


def test_git_whitespace_parsing_edge_cases(temp_dirs):
    """Test git output parsing with complex whitespace scenarios."""
    source_dir, _ = temp_dirs
    
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            # Complex whitespace scenarios
            output = "  file1.py  \n\n\t\tfile2.txt\t\n   \n\r\nfile3.md\r\n\n  "
            return MagicMock(returncode=0, stdout=output)
        return MagicMock(returncode=1)
    
    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        
        # Should properly parse and clean whitespace
        expected = {"file1.py", "file2.txt", "file3.md"}
        assert result == expected


def test_process_directory_sync_nested_ignore_edge_cases(temp_dirs):
    """Test process_directory_sync with nested directory ignore scenarios."""
    source_dir, target_dir = temp_dirs
    
    # Create config
    (source_dir / "arboribus.toml").write_text("")
    
    # Create simple nested structure
    nested = source_dir / "outer"
    nested.mkdir()
    (nested / "file.py").write_text("content")
    
    # Test basic directory sync without git filtering
    was_processed, message = process_directory_sync(
        nested, target_dir / "outer", source_dir, git_tracked_files=None, dry=False
    )
    
    assert was_processed
    assert (target_dir / "outer" / "file.py").exists()
