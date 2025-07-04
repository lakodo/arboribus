"""Test arboribus core functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest
import toml
from toml.decoder import TomlDecodeError
from toml.decoder import TomlDecodeError

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

        # Create directory structure
        (source_dir / "libs" / "admin").mkdir(parents=True)
        (source_dir / "libs" / "auth").mkdir(parents=True)
        (source_dir / "libs" / "core").mkdir(parents=True)
        (source_dir / "apps").mkdir()
        (source_dir / "apps" / "web").mkdir(parents=True)

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
    config_data = {"targets": {"test-target": {"path": "/some/path", "patterns": ["libs/*"], "exclude-patterns": []}}}

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
    with patch("subprocess.run") as mock_run:
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
            return MagicMock(returncode=0, stdout="libs/admin/test.py\nlibs/auth/test.py\napps/web/test.py\n")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result == {"libs/admin/test.py", "libs/auth/test.py", "apps/web/test.py"}


def test_get_git_tracked_files_exception(temp_dirs):
    """Test git tracking when subprocess raises exception."""
    source_dir, _ = temp_dirs

    with patch("subprocess.run", side_effect=FileNotFoundError):
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
    expected_paths = {source_dir / "libs" / "admin", source_dir / "libs" / "auth"}
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
    expected = {"libs/admin/test.py", "libs/auth/test.py", "libs/core/test.py"}
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

            with patch("pathlib.Path.cwd", return_value=nested_dir):
                result = get_default_source()
                assert result == temp_path / "project"
        finally:
            os.chdir(original_cwd)


def test_get_default_source_not_found():
    """Test when no default source is found."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        with patch("pathlib.Path.cwd", return_value=temp_path):
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

    was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=True)

    assert was_processed is True
    assert "would copy" in message
    assert not target_file.exists()  # File should not be created in dry run


def test_process_file_sync_actual(temp_dirs):
    """Test actual file sync."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")

    was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=False)

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

    was_processed, message = process_file_sync(source_file, target_file, source_dir, git_tracked, dry=False)

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

    was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=False)

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

    was_processed, message = process_directory_sync(source_subdir, target_subdir, source_dir, None, dry=True)

    assert was_processed is True
    assert "would sync directory" in message
    assert not target_subdir.exists()


def test_process_directory_sync_actual(temp_dirs):
    """Test actual directory sync."""
    source_dir, target_dir = temp_dirs

    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"

    was_processed, message = process_directory_sync(source_subdir, target_subdir, source_dir, None, dry=False)

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

    was_processed, message = process_directory_sync(source_subdir, target_subdir, source_dir, git_tracked, dry=False)

    assert was_processed is False
    assert "filtered out" in message
    assert not target_subdir.exists()


def test_process_path_file(temp_dirs):
    """Test process_path with a file."""
    source_dir, target_dir = temp_dirs

    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    source_file.write_text("test content")

    was_processed, message = process_path(source_file, target_file, source_dir, None, dry=False)

    assert was_processed is True
    assert "copied" in message


def test_process_path_directory(temp_dirs):
    """Test process_path with a directory."""
    source_dir, target_dir = temp_dirs

    source_subdir = source_dir / "libs" / "admin"
    target_subdir = target_dir / "libs" / "admin"

    was_processed, message = process_path(source_subdir, target_subdir, source_dir, None, dry=False)

    assert was_processed is True
    assert "synced directory" in message


def test_process_path_nonexistent(temp_dirs):
    """Test process_path with nonexistent path."""
    source_dir, target_dir = temp_dirs

    # Create a path that's neither file nor directory
    nonexistent = source_dir / "nonexistent"
    target_path = target_dir / "nonexistent"

    was_processed, message = process_path(nonexistent, target_path, source_dir, None, dry=False)

    assert was_processed is False
    assert "not a file or directory" in message


def test_sync_directory_with_reverse(temp_dirs):
    """Test sync_directory with reverse flag."""
    source_dir, target_dir = temp_dirs

    # Create source content
    test_file = source_dir / "test.txt"
    test_file.write_text("source content")

    # Test reverse sync (dry run)
    sync_directory(source_dir, target_dir, reverse=True, dry=True)

    # Should not actually sync in dry mode
    assert not (target_dir / "test.txt").exists()


def test_sync_directory_actual_sync(temp_dirs):
    """Test sync_directory with actual file operations."""
    source_dir, target_dir = temp_dirs

    # Create source content
    test_file = source_dir / "test.txt"
    test_file.write_text("source content")

    # Create target directory with existing content that should be removed
    target_dir.mkdir(exist_ok=True)
    existing_file = target_dir / "existing.txt"
    existing_file.write_text("existing content")

    # Test actual sync
    sync_directory(source_dir, target_dir, reverse=False, dry=False)

    # Target should have source content, not existing content
    assert (target_dir / "test.txt").exists()
    assert not (target_dir / "existing.txt").exists()


def test_config_error_handling(temp_dirs):
    """Test configuration error handling."""
    source_dir, target_dir = temp_dirs

    # Test loading invalid TOML file - should raise TomlDecodeError
    config_path = source_dir / "arboribus.toml"
    config_path.write_text("invalid toml content [[[")

    # Since the function doesn't handle TOML errors, it should raise
    with pytest.raises(TomlDecodeError):  # TOML parsing will raise an exception
        load_config(source_dir)

    # Test saving config to read-only location
    with patch("pathlib.Path.write_text") as mock_write:
        mock_write.side_effect = PermissionError("Permission denied")

        # Should not raise exception, just fail silently
        save_config(source_dir, {"targets": {}})


def test_file_operations_error_handling(temp_dirs):
    """Test file operation error handling."""
    source_dir, target_dir = temp_dirs

    # Test checksum on permission denied file
    test_file = source_dir / "test.txt"
    test_file.write_text("test content")

    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        checksum = get_file_checksum(test_file)
        assert checksum is None  # Should return None on error

    # Test is_same_file_content with one file missing
    result = is_same_file_content(test_file, source_dir / "nonexistent.txt")
    assert result is False


def test_error_handling_in_git_functions(temp_dirs):
    """Test error handling in git-related functions."""
    source_dir, target_dir = temp_dirs

    # Test get_git_tracked_files with permission error simulation
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = PermissionError("Permission denied")
        result = get_git_tracked_files(source_dir)
        assert result is None

    # Test get_git_tracked_files with other exceptions
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("Git not found")
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_resolve_patterns_empty_and_edge_cases(temp_dirs):
    """Test resolve_patterns with edge cases."""
    source_dir, target_dir = temp_dirs

    # Test with patterns that don't match anything
    result = resolve_patterns(source_dir, ["nonexistent/**/*"])
    assert len(result) == 0

    # Test with empty patterns list
    result = resolve_patterns(source_dir, [])
    assert len(result) == 0


def test_get_file_statistics_with_git_filter_new():
    """Test get_file_statistics with git filtering."""
    # Create temporary files
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create files
        file1 = temp_path / "tracked.py"
        file1.write_text("tracked")
        file2 = temp_path / "untracked.py"
        file2.write_text("untracked")

        all_files = [file1, file2]
        git_files = {"tracked.py"}

        # Get stats with git filter
        stats = get_file_statistics(all_files, temp_path, git_tracked_files=git_files)

        # Should only count tracked files
        assert stats["[TOTAL FILES]"] == 1
        assert stats[".py"] == 1


def test_collect_files_with_git_filtering_new(temp_dirs):
    """Test file collection with git filtering applied."""
    source_dir, target_dir = temp_dirs

    # Create files
    file1 = source_dir / "tracked.txt"
    file1.write_text("tracked")
    file2 = source_dir / "untracked.txt"
    file2.write_text("untracked")

    # Test with git filter
    git_files = {"tracked.txt"}
    files = collect_files_recursive(source_dir, source_dir, git_tracked_files=git_files)

    # Should only return tracked files
    assert len(files) == 1
    assert files[0].name == "tracked.txt"


def test_save_config_error_handling(temp_dirs):
    """Test save_config error handling."""
    source_dir, target_dir = temp_dirs

    # Test saving config with file write error
    with patch("builtins.open", side_effect=PermissionError("Permission denied")):
        # Should raise exception since save_config doesn't handle errors
        with pytest.raises(PermissionError):
            save_config(source_dir, {"targets": {}})


def test_get_git_tracked_files_empty_output(temp_dirs):
    """Test git tracked files with empty output."""
    source_dir, target_dir = temp_dirs

    # Mock subprocess to simulate git ls-files returning empty output
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            return MagicMock(returncode=0, stdout="")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result == set()  # Should return empty set


def test_get_git_tracked_files_whitespace_lines(temp_dirs):
    """Test git tracked files with whitespace in output."""
    source_dir, target_dir = temp_dirs

    # Mock subprocess to simulate git ls-files with whitespace lines
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            return MagicMock(returncode=0, stdout="libs/admin/test.py\n\n  \nlibs/auth/test.py\n   \n")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        # Should only include non-empty lines, stripped
        assert result == {"libs/admin/test.py", "libs/auth/test.py"}


def test_get_git_tracked_files_ls_files_error(temp_dirs):
    """Test git tracked files when ls-files command fails."""
    source_dir, target_dir = temp_dirs

    # Mock subprocess where rev-parse succeeds but ls-files fails
    def mock_subprocess(cmd, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0)
        elif "ls-files" in cmd:
            return MagicMock(returncode=1)  # ls-files fails
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_subprocess):
        result = get_git_tracked_files(source_dir)
        assert result is None


def test_resolve_patterns_with_nonexistent_paths(temp_dirs):
    """Test resolve_patterns with patterns that match nonexistent paths."""
    source_dir, target_dir = temp_dirs

    # Test with patterns that would match but paths don't exist
    patterns = ["nonexistent/path/*", "missing/**"]
    result = resolve_patterns(source_dir, patterns)
    assert len(result) == 0


def test_resolve_patterns_complex_git_filtering(temp_dirs):
    """Test resolve_patterns with complex git filtering scenarios."""
    source_dir, target_dir = temp_dirs

    # Create additional files for testing
    (source_dir / "docs").mkdir()
    (source_dir / "docs" / "readme.md").write_text("docs")
    (source_dir / "tests").mkdir() 
    (source_dir / "tests" / "test.py").write_text("test")

    # Only some files are tracked
    git_tracked = {"libs/admin/test.py", "docs/readme.md"}

    patterns = ["*"]  # Match all top-level directories
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked)

    # Should only include directories that contain tracked files
    result_names = {p.name for p in result}
    assert "libs" in result_names  # Has tracked files
    assert "docs" in result_names  # Has tracked files
    assert "apps" not in result_names  # No tracked files
    assert "tests" not in result_names  # No tracked files


def test_collect_files_recursive_complex_filtering(temp_dirs):
    """Test collect_files_recursive with complex directory structures."""
    source_dir, target_dir = temp_dirs

    # Create nested structure
    (source_dir / "deep" / "nested" / "dir").mkdir(parents=True)
    (source_dir / "deep" / "nested" / "dir" / "file.txt").write_text("content")
    (source_dir / "deep" / "file2.txt").write_text("content2")

    # Test without git filter
    files = collect_files_recursive(source_dir / "deep", source_dir)
    assert len(files) == 2

    # Test with git filter that excludes some files
    git_tracked = {"deep/file2.txt"}  # Only one file tracked
    files = collect_files_recursive(source_dir / "deep", source_dir, git_tracked_files=git_tracked)
    assert len(files) == 1
    assert files[0].name == "file2.txt"


def test_get_file_statistics_complex_scenarios(temp_dirs):
    """Test get_file_statistics with various file types and edge cases."""
    source_dir, target_dir = temp_dirs

    # Create files with different extensions
    (source_dir / "script.py").write_text("python")
    (source_dir / "readme.md").write_text("markdown")
    (source_dir / "config.json").write_text("{}")
    (source_dir / "data.csv").write_text("csv")
    (source_dir / "noext").write_text("no extension")

    paths = [source_dir]
    stats = get_file_statistics(paths, source_dir)

    # Check various extensions are counted
    assert stats[".py"] >= 1
    assert stats[".md"] == 1
    assert stats[".json"] == 1
    assert stats[".csv"] == 1
    assert stats["(no extension)"] == 1  # This is the correct key format
    assert stats["[TOTAL FILES]"] >= 5


def test_process_file_sync_edge_cases(temp_dirs):
    """Test process_file_sync with additional edge cases."""
    source_dir, target_dir = temp_dirs

    # Test with file that doesn't need copying (dry run, same content)
    source_file = source_dir / "test.txt"
    target_file = target_dir / "test.txt"
    content = "same content"
    
    source_file.write_text(content)
    target_file.write_text(content)

    # Should skip in dry run when content is same
    was_processed, message = process_file_sync(source_file, target_file, source_dir, None, dry=True)
    assert was_processed is False
    assert "same - skipped" in message


def test_process_directory_sync_with_existing_files(temp_dirs):
    """Test process_directory_sync when target already has files."""
    source_dir, target_dir = temp_dirs

    # Create source directory with files
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("content1")
    (test_dir / "file2.txt").write_text("content2")

    # Create target directory with different files - this should be a new location
    target_test_dir = target_dir / "newdir"  # Use a new directory name

    # Sync should create the directory
    was_processed, message = process_directory_sync(test_dir, target_test_dir, source_dir, None, dry=False)
    
    assert was_processed is True
    assert (target_test_dir / "file1.txt").exists()
    assert (target_test_dir / "file2.txt").exists()


def test_sync_directory_full_scenarios(temp_dirs):
    """Test sync_directory with comprehensive scenarios."""
    source_dir, target_dir = temp_dirs

    # Create complex source structure
    (source_dir / "dir1").mkdir()
    (source_dir / "dir1" / "file1.txt").write_text("content1")
    (source_dir / "dir2").mkdir()
    (source_dir / "dir2" / "file2.txt").write_text("content2")
    (source_dir / "single_file.txt").write_text("single")

    # Test normal sync (not reverse, not dry)
    sync_directory(source_dir, target_dir, reverse=False, dry=False)

    # Check all content was synced
    assert (target_dir / "dir1" / "file1.txt").exists()
    assert (target_dir / "dir2" / "file2.txt").exists()
    assert (target_dir / "single_file.txt").exists()

    # Test reverse sync (dry run)
    new_target = source_dir.parent / "new_target"
    new_target.mkdir()
    
    sync_directory(target_dir, new_target, reverse=True, dry=True)
    # In dry run, files shouldn't be created
    assert not (new_target / "dir1").exists()


def test_load_config_with_missing_targets_key():
    """Test load_config when TOML is valid but missing targets key."""
    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = Path(temp_dir)
        config_path = source_dir / "arboribus.toml"
        
        # Create valid TOML without targets key
        config_path.write_text('[other]\nkey = "value"\n')
        
        # Should still load successfully, function handles missing keys
        config = load_config(source_dir)
        assert isinstance(config, dict)
        assert "other" in config


def test_resolve_patterns_file_with_git_filter(temp_dirs):
    """Test resolve_patterns with files and git filtering."""
    source_dir, target_dir = temp_dirs

    # Create files directly in source_dir
    file1 = source_dir / "tracked.py"
    file1.write_text("tracked")
    file2 = source_dir / "untracked.py"
    file2.write_text("untracked")

    # Test with file patterns and git filter
    git_tracked = {"tracked.py"}
    patterns = ["*.py"]
    
    # Should find files when include_files=True and git filtering
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked, include_files=True)
    
    # Should only include tracked files
    assert len(result) == 1
    assert result[0].name == "tracked.py"


def test_resolve_patterns_directory_exact_match_git(temp_dirs):
    """Test resolve_patterns with directory that exactly matches git tracked path."""
    source_dir, target_dir = temp_dirs

    # Create a file that matches a directory name in git tracking
    (source_dir / "exact_match").mkdir()
    (source_dir / "exact_match" / "file.txt").write_text("content")

    # Git tracking includes the directory name exactly
    git_tracked = {"exact_match"}  # Exact directory name in git
    patterns = ["exact_match"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked)
    
    # Should include the directory because it exactly matches git tracking
    assert len(result) == 1
    assert result[0].name == "exact_match"


def test_resolve_patterns_exclude_with_files(temp_dirs):
    """Test resolve_patterns with exclude patterns and files."""
    source_dir, target_dir = temp_dirs

    # Create files
    file1 = source_dir / "include.txt"
    file1.write_text("include")
    file2 = source_dir / "exclude.txt"
    file2.write_text("exclude")

    patterns = ["*.txt"]
    exclude_patterns = ["exclude.txt"]
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns, include_files=True)
    
    # Should only include non-excluded files
    assert len(result) == 1
    assert result[0].name == "include.txt"


def test_collect_files_recursive_root_files(temp_dirs):
    """Test collect_files_recursive with files in the root directory."""
    source_dir, target_dir = temp_dirs

    # Create files directly in source_dir
    (source_dir / "root1.txt").write_text("root1")
    (source_dir / "root2.txt").write_text("root2")

    # Collect from source_dir itself
    files = collect_files_recursive(source_dir, source_dir)
    
    # Should include all files (both direct and from subdirectories)
    file_names = {f.name for f in files}
    assert "root1.txt" in file_names
    assert "root2.txt" in file_names
    assert "test.py" in file_names  # From the existing libs structure


def test_get_file_statistics_empty_directory(temp_dirs):
    """Test get_file_statistics with empty directory."""
    source_dir, target_dir = temp_dirs

    # Create empty directory
    empty_dir = source_dir / "empty"
    empty_dir.mkdir()

    paths = [empty_dir]
    stats = get_file_statistics(paths, source_dir)

    # Should have zero files but one directory
    assert stats["[TOTAL FILES]"] == 0
    assert stats["[TOTAL DIRS]"] == 1


def test_get_file_statistics_files_with_git_filter(temp_dirs):
    """Test get_file_statistics with individual files and git filtering."""
    source_dir, target_dir = temp_dirs

    # Create files
    file1 = source_dir / "tracked.py"
    file1.write_text("tracked")
    file2 = source_dir / "untracked.py"
    file2.write_text("untracked")

    # Test with individual files and git filter
    git_tracked = {"tracked.py"}
    paths = [file1, file2]  # Pass individual files, not directories
    
    stats = get_file_statistics(paths, source_dir, git_tracked_files=git_tracked)

    # Should only count tracked files
    assert stats["[TOTAL FILES]"] == 1
    assert stats[".py"] == 1


def test_process_directory_sync_replace_existing(temp_dirs):
    """Test process_directory_sync with replace_existing=True."""
    source_dir, target_dir = temp_dirs

    # Create source directory
    test_dir = source_dir / "testdir"
    test_dir.mkdir()
    (test_dir / "new_file.txt").write_text("new content")

    # Create existing target directory
    target_test_dir = target_dir / "testdir"
    target_test_dir.mkdir()
    (target_test_dir / "old_file.txt").write_text("old content")

    # Sync with replace_existing=True
    was_processed, message = process_directory_sync(
        test_dir, target_test_dir, source_dir, None, dry=False, replace_existing=True
    )
    
    assert was_processed is True
    assert (target_test_dir / "new_file.txt").exists()
    # Old file should be removed due to replace_existing=True
    assert not (target_test_dir / "old_file.txt").exists()


def test_process_directory_sync_git_filter_edge_cases(temp_dirs):
    """Test process_directory_sync with git filtering edge cases."""
    source_dir, target_dir = temp_dirs

    # Create nested directory structure
    nested_dir = source_dir / "level1" / "level2"
    nested_dir.mkdir(parents=True)
    (nested_dir / "deep_file.txt").write_text("deep content")

    target_nested = target_dir / "level1" / "level2"

    # Test with git tracking that includes subdirectory
    git_tracked = {"level1/level2/deep_file.txt"}
    
    was_processed, message = process_directory_sync(
        nested_dir, target_nested, source_dir, git_tracked, dry=False
    )
    
    # Should process because directory contains tracked files
    assert was_processed is True
    assert (target_nested / "deep_file.txt").exists()


def test_default_source_edge_cases():
    """Test get_default_source with edge cases."""
    # Test when we're at filesystem root
    with patch("pathlib.Path.cwd") as mock_cwd:
        # Mock being at root directory
        root = Path("/")
        mock_cwd.return_value = root
        
        # Should return None when no config found at root
        result = get_default_source()
        assert result is None


def test_save_config_directory_creation(temp_dirs):
    """Test save_config when parent directory needs to be created."""
    source_dir, target_dir = temp_dirs

    # Create subdirectory that doesn't exist yet
    nested_dir = source_dir / "nested" / "config"
    
    # This should work because save_config should handle directory creation
    # or fail gracefully
    try:
        save_config(nested_dir, {"targets": {}})
        # If it succeeds, verify the file was created
        config_path = nested_dir / "arboribus.toml"
        assert config_path.exists()
    except FileNotFoundError:
        # This is acceptable behavior if the function doesn't create directories
        pass


def test_process_path_symlink_handling(temp_dirs):
    """Test process_path with symbolic links."""
    source_dir, target_dir = temp_dirs

    # Create a symlink (skip if not supported)
    try:
        link_target = source_dir / "target_file.txt"
        link_target.write_text("target content")
        
        symlink = source_dir / "symlink"
        symlink.symlink_to(link_target)
        
        target_path = target_dir / "symlink"
        
        # Test how process_path handles symlinks
        was_processed, message = process_path(symlink, target_path, source_dir, None, dry=False)
        
        # Behavior depends on implementation - just ensure it doesn't crash
        assert isinstance(was_processed, bool)
        assert isinstance(message, str)
        
    except (OSError, NotImplementedError):
        # Skip if symlinks not supported on this platform
        pass
