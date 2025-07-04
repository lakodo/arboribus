"""Test arboribus core functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest
import toml

from arboribus.core import (
    get_config_path,
    load_config,
    save_config,
    get_git_tracked_files,
    resolve_patterns,
    collect_files_recursive,
    get_file_statistics,
    get_default_source,
    get_file_checksum,
    is_same_file_content,
    process_file_sync,
    process_directory_sync,
    process_path,
)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        source_dir = temp_path / "source"
        target_dir = temp_path / "target"

        source_dir.mkdir()
        target_dir.mkdir()

        # Create some test directories
        (source_dir / "libs").mkdir()
        (source_dir / "libs" / "admin").mkdir()
        (source_dir / "libs" / "auth").mkdir()
        (source_dir / "libs" / "core").mkdir()
        (source_dir / "apps").mkdir()
        (source_dir / "apps" / "web").mkdir()

        # Create some test files
        (source_dir / "libs" / "admin" / "test.py").write_text("# admin code")
        (source_dir / "libs" / "auth" / "test.py").write_text("# auth code")
        (source_dir / "libs" / "core" / "test.py").write_text("# core code")
        (source_dir / "apps" / "web" / "test.py").write_text("# web code")

        yield source_dir, target_dir


def test_config_path():
    """Test config path generation."""
    source_dir = Path("/tmp/test")
    config_path = get_config_path(source_dir)
    assert config_path == source_dir / "arboribus.toml"


def test_load_config_nonexistent(temp_dirs):
    """Test loading config when file doesn't exist."""
    source_dir, _ = temp_dirs
    config = load_config(source_dir)
    assert config == {"targets": {}}


def test_save_and_load_config(temp_dirs):
    """Test saving and loading config."""
    source_dir, _ = temp_dirs
    
    # Test config data
    config_data = {
        "targets": {
            "test-target": {
                "path": "/some/path",
                "patterns": ["libs/*"],
                "exclude-patterns": []
            }
        }
    }
    
    # Save config
    save_config(source_dir, config_data)
    
    # Check file was created
    config_path = get_config_path(source_dir)
    assert config_path.exists()
    
    # Load and verify
    loaded_config = load_config(source_dir)
    assert loaded_config == config_data


def test_get_git_tracked_files_no_git(temp_dirs):
    """Test git tracking when not in a git repo."""
    source_dir, _ = temp_dirs
    
    # Mock subprocess to simulate not being in a git repo
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_get_git_tracked_files_success(temp_dirs):
    """Test git tracking when in a git repo."""
    source_dir, _ = temp_dirs
    
    # Mock subprocess to simulate successful git commands
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            return MagicMock(
                returncode=0, 
                stdout="libs/admin/test.py\nlibs/auth/test.py\napps/web/test.py\n"
            )
        return MagicMock(returncode=1)
    
    with patch('subprocess.run', side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result == {"libs/admin/test.py", "libs/auth/test.py", "apps/web/test.py"}


def test_get_git_tracked_files_exception(temp_dirs):
    """Test git tracking when subprocess raises exception."""
    source_dir, _ = temp_dirs
    
    with patch('subprocess.run', side_effect=FileNotFoundError):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_resolve_patterns_basic(temp_dirs):
    """Test basic pattern resolution."""
    source_dir, _ = temp_dirs
    
    # Test direct path matching
    patterns = ["libs/admin"]
    result = resolve_patterns(source_dir, patterns)
    
    assert len(result) == 1
    assert result[0] == source_dir / "libs" / "admin"


def test_resolve_patterns_glob(temp_dirs):
    """Test glob pattern resolution."""
    source_dir, _ = temp_dirs
    
    # Test glob pattern
    patterns = ["libs/a*"]
    result = resolve_patterns(source_dir, patterns)
    
    # Should match admin and auth
    expected_paths = {
        source_dir / "libs" / "admin",
        source_dir / "libs" / "auth"
    }
    assert set(result) == expected_paths


def test_resolve_patterns_with_git_filter(temp_dirs):
    """Test pattern resolution with git filtering."""
    source_dir, _ = temp_dirs
    
    # Only admin is tracked
    git_tracked = {"libs/admin/test.py"}
    
    patterns = ["libs/*"]
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked)
    
    # Should only match admin since it has tracked files
    assert len(result) == 1
    assert result[0] == source_dir / "libs" / "admin"


def test_resolve_patterns_with_exclude(temp_dirs):
    """Test pattern resolution with exclude patterns."""
    source_dir, _ = temp_dirs
    
    patterns = ["libs/*"]
    exclude_patterns = ["libs/core"]
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should match admin and auth, but not core
    result_names = {p.name for p in result}
    assert "admin" in result_names
    assert "auth" in result_names
    assert "core" not in result_names


def test_resolve_patterns_include_files(temp_dirs):
    """Test pattern resolution including files."""
    source_dir, _ = temp_dirs
    
    # Create a direct file
    test_file = source_dir / "test.txt"
    test_file.write_text("test")
    
    patterns = ["test.txt"]
    result = resolve_patterns(source_dir, patterns, include_files=True)
    
    assert len(result) == 1
    assert result[0] == test_file


def test_collect_files_recursive(temp_dirs):
    """Test recursive file collection."""
    source_dir, _ = temp_dirs
    
    libs_dir = source_dir / "libs"
    result = collect_files_recursive(libs_dir, source_dir)
    
    # Should find all .py files in libs
    result_paths = {str(f.relative_to(source_dir)) for f in result}
    expected = {
        "libs/admin/test.py",
        "libs/auth/test.py", 
        "libs/core/test.py"
    }
    assert result_paths == expected


def test_collect_files_recursive_with_git_filter(temp_dirs):
    """Test recursive file collection with git filtering."""
    source_dir, _ = temp_dirs
    
    # Only admin file is tracked
    git_tracked = {"libs/admin/test.py"}
    
    libs_dir = source_dir / "libs"
    result = collect_files_recursive(libs_dir, source_dir, git_tracked_files=git_tracked)
    
    # Should only find the tracked file
    assert len(result) == 1
    assert result[0].relative_to(source_dir) == Path("libs/admin/test.py")


def test_get_file_statistics(temp_dirs):
    """Test file statistics generation."""
    source_dir, _ = temp_dirs
    
    paths = [source_dir / "libs" / "admin", source_dir / "libs" / "auth"]
    stats = get_file_statistics(paths, source_dir)
    
    assert stats[".py"] == 2  # Two .py files
    assert stats["[TOTAL FILES]"] == 2
    assert stats["[TOTAL DIRS]"] == 2


def test_get_file_statistics_with_git_filter(temp_dirs):
    """Test file statistics with git filtering."""
    source_dir, _ = temp_dirs
    
    # Only one file is tracked
    git_tracked = {"libs/admin/test.py"}
    
    paths = [source_dir / "libs"]
    stats = get_file_statistics(paths, source_dir, git_tracked_files=git_tracked)
    
    assert stats[".py"] == 1  # Only one tracked .py file
    assert stats["[TOTAL FILES]"] == 1
    assert stats["[TOTAL DIRS]"] == 1


def test_get_default_source_found():
    """Test finding default source directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create nested directory structure
        nested_dir = temp_path / "project" / "subdir"
        nested_dir.mkdir(parents=True)
        
        # Create config file in project root
        config_file = temp_path / "project" / "arboribus.toml"
        config_file.write_text("[targets]\n")
        
        # Change to nested directory and test
        original_cwd = Path.cwd()
        try:
            import os
            os.chdir(nested_dir)
            
            with patch('pathlib.Path.cwd', return_value=nested_dir):
                result = get_default_source()
                assert result == temp_path / "project"
        finally:
            os.chdir(original_cwd)


def test_get_default_source_not_found():
    """Test when no default source is found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        with patch('pathlib.Path.cwd', return_value=temp_path):
            result = get_default_source()
            assert result is None


def test_get_file_checksum(temp_dirs):
    """Test file checksum calculation."""
    source_dir, _ = temp_dirs
    
    test_file = source_dir / "test.txt"
    test_file.write_text("hello world")
    
    checksum = get_file_checksum(test_file)
    assert checksum is not None
    assert isinstance(checksum, str)
    assert len(checksum) == 32  # MD5 hex length


def test_get_file_checksum_nonexistent():
    """Test checksum of nonexistent file."""
    nonexistent = Path("/nonexistent/file.txt")
    checksum = get_file_checksum(nonexistent)
    assert checksum is None


def test_is_same_file_content(temp_dirs):
    """Test file content comparison."""
    source_dir, target_dir = temp_dirs
    
    # Create identical files
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    
    content = "hello world"
    source_file.write_text(content)
    target_file.write_text(content)
    
    assert is_same_file_content(source_file, target_file) is True
    
    # Change target content
    target_file.write_text("different content")
    assert is_same_file_content(source_file, target_file) is False


def test_is_same_file_content_nonexistent(temp_dirs):
    """Test file content comparison with nonexistent files."""
    source_dir, _ = temp_dirs
    
    source_file = source_dir / "test.txt"
    nonexistent = source_dir / "nonexistent.txt"
    
    source_file.write_text("hello")
    
    assert is_same_file_content(source_file, nonexistent) is False
    assert is_same_file_content(nonexistent, source_file) is False


def test_process_file_sync_dry_run(temp_dirs):
    """Test file sync in dry run mode."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")
    
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=True
    )
    
    assert was_processed is True
    assert "would copy" in message
    assert not target_file.exists()  # File should not be created in dry run


def test_process_file_sync_actual(temp_dirs):
    """Test actual file sync."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")
    
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )
    
    assert was_processed is True
    assert "copied" in message
    assert target_file.exists()
    assert target_file.read_text() == "test content"


def test_process_file_sync_git_filtered(temp_dirs):
    """Test file sync with git filtering."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")
    
    # File not in git tracking
    git_tracked = {"other_file.txt"}
    
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, git_tracked, dry=False
    )
    
    assert was_processed is False
    assert "filtered out" in message
    assert not target_file.exists()


def test_process_file_sync_existing_same_content(temp_dirs):
    """Test file sync when target exists with same content."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    content = "test content"
    
    source_file.write_text(content)
    target_file.write_text(content)
    
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False
    )
    
    assert was_processed is False
    assert "same - skipped" in message


def test_process_file_sync_existing_replace(temp_dirs):
    """Test file sync with replace existing."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    
    source_file.write_text("new content")
    target_file.write_text("old content")
    
    was_processed, message = process_file_sync(
        source_file, target_file, source_dir, None, dry=False, replace_existing=True
    )
    
    assert was_processed is True
    assert "replaced" in message
    assert target_file.read_text() == "new content"


def test_process_directory_sync_dry_run(temp_dirs):
    """Test directory sync in dry run mode."""
    source_dir, target_dir = temp_dirs
    
    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"
    
    was_processed, message = process_directory_sync(
        source_subdir, target_subdir, source_dir, None, dry=True
    )
    
    assert was_processed is True
    assert "would sync directory" in message
    assert not target_subdir.exists()


def test_process_directory_sync_actual(temp_dirs):
    """Test actual directory sync."""
    source_dir, target_dir = temp_dirs
    
    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"
    
    was_processed, message = process_directory_sync(
        source_subdir, target_subdir, source_dir, None, dry=False
    )
    
    assert was_processed is True
    assert "synced directory" in message
    assert target_subdir.exists()
    assert (target_subdir / "test.py").exists()


def test_process_directory_sync_git_filtered(temp_dirs):
    """Test directory sync with git filtering."""
    source_dir, target_dir = temp_dirs
    
    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"
    
    # Directory has no tracked files
    git_tracked = {"other/file.py"}
    
    was_processed, message = process_directory_sync(
        source_subdir, target_subdir, source_dir, git_tracked, dry=False
    )
    
    assert was_processed is False
    assert "filtered out" in message
    assert not target_subdir.exists()


def test_process_path_file(temp_dirs):
    """Test process_path with a file."""
    source_dir, target_dir = temp_dirs
    
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")
    
    was_processed, message = process_path(
        source_file, target_file, source_dir, None, dry=False
    )
    
    assert was_processed is True
    assert "copied" in message


def test_process_path_directory(temp_dirs):
    """Test process_path with a directory."""
    source_dir, target_dir = temp_dirs
    
    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"
    
    was_processed, message = process_path(
        source_subdir, target_subdir, source_dir, None, dry=False
    )
    
    assert was_processed is True
    assert "synced directory" in message


def test_process_path_nonexistent(temp_dirs):
    """Test process_path with nonexistent path."""
    source_dir, target_dir = temp_dirs
    
    # Create a path that's neither file nor directory
    nonexistent = source_dir / "nonexistent"
    target_path = target_dir / "nonexistent"
    
    was_processed, message = process_path(
        nonexistent, target_path, source_dir, None, dry=False
    )
    
    assert was_processed is False
    assert "not a file or directory" in message
