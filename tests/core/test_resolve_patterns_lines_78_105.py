"""Test specific lines 78-105 in resolve_patterns function from core.py."""

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

        # Create directory structure
        (source_dir / "frontend").mkdir()
        (source_dir / "frontend" / "src").mkdir()
        (source_dir / "frontend" / "src" / "app.js").write_text("// frontend app")
        (source_dir / "frontend" / "package.json").write_text('{"name": "frontend"}')
        
        (source_dir / "backend").mkdir()
        (source_dir / "backend" / "src").mkdir()
        (source_dir / "backend" / "src" / "main.py").write_text("# backend main")
        (source_dir / "backend" / "requirements.txt").write_text("django")

        (source_dir / "docs").mkdir()
        (source_dir / "docs" / "readme.md").write_text("# Documentation")

        (source_dir / "config.yaml").write_text("settings: {}")
        (source_dir / "script.sh").write_text("#!/bin/bash\necho 'test'")

        yield source_dir


def test_direct_path_matching_directory_exists(temp_structure):
    """Test line 75-77: Direct path matching when directory exists."""
    source_dir = temp_structure
    
    # Test direct directory matching
    patterns = ["frontend"]
    result = resolve_patterns(source_dir, patterns)
    
    assert len(result) == 1
    assert result[0] == source_dir / "frontend"
    assert result[0].is_dir()


def test_direct_path_matching_file_with_include_files(temp_structure):
    """Test line 78: include_files condition for direct file matching."""
    source_dir = temp_structure
    
    # Test direct file matching with include_files=True
    patterns = ["config.yaml"]
    result = resolve_patterns(source_dir, patterns, include_files=True)
    
    assert len(result) == 1
    assert result[0] == source_dir / "config.yaml"
    assert result[0].is_file()


def test_direct_path_matching_file_without_include_files(temp_structure):
    """Test line 78: file not included when include_files=False."""
    source_dir = temp_structure
    
    # Test direct file matching with include_files=False (default)
    patterns = ["config.yaml"]
    result = resolve_patterns(source_dir, patterns, include_files=False)
    
    assert len(result) == 0  # File should not be included


def test_path_relative_calculation(temp_structure):
    """Test line 79: path_relative calculation."""
    source_dir = temp_structure
    
    patterns = ["frontend"]
    result = resolve_patterns(source_dir, patterns)
    
    # Verify the relative path calculation works correctly
    assert len(result) == 1
    relative_path = result[0].relative_to(source_dir)
    assert str(relative_path) == "frontend"


def test_git_filtering_file_tracked(temp_structure):
    """Test lines 82-87: Git filtering for tracked files."""
    source_dir = temp_structure
    
    # Test file that is tracked in git
    git_tracked_files = {"config.yaml", "frontend/package.json"}
    patterns = ["config.yaml"]
    
    result = resolve_patterns(
        source_dir, 
        patterns, 
        git_tracked_files=git_tracked_files, 
        include_files=True
    )
    
    assert len(result) == 1
    assert result[0] == source_dir / "config.yaml"


def test_git_filtering_file_not_tracked(temp_structure):
    """Test lines 82-87: Git filtering excludes untracked files."""
    source_dir = temp_structure
    
    # Test file that is NOT tracked in git
    git_tracked_files = {"frontend/package.json"}  # config.yaml not tracked
    patterns = ["config.yaml"]
    
    result = resolve_patterns(
        source_dir, 
        patterns, 
        git_tracked_files=git_tracked_files, 
        include_files=True
    )
    
    assert len(result) == 0  # File should be filtered out


def test_git_filtering_directory_has_tracked_files(temp_structure):
    """Test lines 88-95: Git filtering for directories with tracked files."""
    source_dir = temp_structure
    
    # Directory contains tracked files
    git_tracked_files = {"frontend/src/app.js", "frontend/package.json"}
    patterns = ["frontend"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)
    
    assert len(result) == 1
    assert result[0] == source_dir / "frontend"


def test_git_filtering_directory_no_tracked_files(temp_structure):
    """Test lines 88-95: Git filtering excludes directories without tracked files."""
    source_dir = temp_structure
    
    # Directory contains NO tracked files
    git_tracked_files = {"backend/src/main.py"}  # frontend has no tracked files
    patterns = ["frontend"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)
    
    assert len(result) == 0  # Directory should be filtered out


def test_git_filtering_directory_exact_match(temp_structure):
    """Test lines 90-92: Git filtering with exact directory name match."""
    source_dir = temp_structure
    
    # Test when directory name exactly matches a tracked path
    git_tracked_files = {"frontend"}  # Exact directory name
    patterns = ["frontend"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)
    
    assert len(result) == 1
    assert result[0] == source_dir / "frontend"


def test_git_filtering_directory_prefix_match(temp_structure):
    """Test lines 90-92: Git filtering with path prefix matching."""
    source_dir = temp_structure
    
    # Test when tracked files start with directory path + "/"
    git_tracked_files = {"frontend/package.json", "frontend/src/app.js"}
    patterns = ["frontend"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)
    
    assert len(result) == 1
    assert result[0] == source_dir / "frontend"


def test_exclude_patterns_filtering(temp_structure):
    """Test lines 98-101: Exclude patterns filtering."""
    source_dir = temp_structure
    
    # Test exclude patterns
    patterns = ["frontend", "backend", "docs"]
    exclude_patterns = ["backend", "docs"]
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should only include frontend (backend and docs excluded)
    assert len(result) == 1
    assert result[0] == source_dir / "frontend"


def test_exclude_patterns_prefix_matching(temp_structure):
    """Test lines 99-100: Exclude patterns with prefix matching."""
    source_dir = temp_structure
    
    # Create nested structure to test prefix matching
    (source_dir / "test").mkdir()
    (source_dir / "test_exclude").mkdir()
    (source_dir / "test_exclude" / "sub").mkdir()
    
    patterns = ["test", "test_exclude"]
    exclude_patterns = ["test_"]  # Should exclude test_exclude but not test
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should only include "test" directory
    assert len(result) == 1
    assert result[0] == source_dir / "test"


def test_matched_paths_append_and_continue(temp_structure):
    """Test lines 103-104: matched_paths.append and continue logic."""
    source_dir = temp_structure
    
    # Test that direct path matching adds to results and continues to next pattern
    patterns = ["frontend", "backend"]
    result = resolve_patterns(source_dir, patterns)
    
    # Both directories should be found via direct path matching
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "frontend" in result_names
    assert "backend" in result_names


def test_combined_git_and_exclude_filtering(temp_structure):
    """Test combined git filtering and exclude patterns."""
    source_dir = temp_structure
    
    # Test both git filtering and exclude patterns together
    git_tracked_files = {"frontend/src/app.js", "backend/src/main.py", "docs/readme.md"}
    patterns = ["frontend", "backend", "docs"]
    exclude_patterns = ["docs"]
    
    result = resolve_patterns(
        source_dir, 
        patterns, 
        exclude_patterns=exclude_patterns,
        git_tracked_files=git_tracked_files
    )
    
    # Should include frontend and backend (have tracked files), but exclude docs
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "frontend" in result_names
    assert "backend" in result_names
    assert "docs" not in result_names


def test_git_filtering_none_skips_filter(temp_structure):
    """Test that git_tracked_files=None skips git filtering."""
    source_dir = temp_structure
    
    patterns = ["frontend", "backend"]
    result = resolve_patterns(source_dir, patterns, git_tracked_files=None)
    
    # Without git filtering, both directories should be included
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "frontend" in result_names
    assert "backend" in result_names


def test_empty_exclude_patterns_no_filtering(temp_structure):
    """Test that empty exclude_patterns list performs no filtering."""
    source_dir = temp_structure
    
    patterns = ["frontend", "backend"]
    exclude_patterns = []  # Empty list
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Empty exclude patterns should not filter anything
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "frontend" in result_names
    assert "backend" in result_names


def test_none_exclude_patterns_no_filtering(temp_structure):
    """Test that exclude_patterns=None performs no filtering."""
    source_dir = temp_structure
    
    patterns = ["frontend", "backend"]
    exclude_patterns = None
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # None exclude patterns should not filter anything
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "frontend" in result_names
    assert "backend" in result_names


def test_file_and_directory_mixed_patterns(temp_structure):
    """Test mixed file and directory patterns with include_files."""
    source_dir = temp_structure
    
    patterns = ["frontend", "config.yaml", "script.sh"]
    result = resolve_patterns(source_dir, patterns, include_files=True)
    
    # Should include directory and files
    assert len(result) == 3
    paths_by_type = {"dirs": [], "files": []}
    for path in result:
        if path.is_dir():
            paths_by_type["dirs"].append(path.name)
        else:
            paths_by_type["files"].append(path.name)
    
    assert "frontend" in paths_by_type["dirs"]
    assert "config.yaml" in paths_by_type["files"]
    assert "script.sh" in paths_by_type["files"]


def test_git_filtering_edge_case_nested_paths(temp_structure):
    """Test git filtering with nested directory structures."""
    source_dir = temp_structure
    
    # Create deeper nesting
    (source_dir / "deep" / "nested" / "dir").mkdir(parents=True)
    (source_dir / "deep" / "nested" / "dir" / "file.txt").write_text("content")
    
    # Test directory that has tracked files in subdirectories
    git_tracked_files = {"deep/nested/dir/file.txt"}
    patterns = ["deep"]
    
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)
    
    # Directory should be included because it contains tracked files
    assert len(result) == 1
    assert result[0] == source_dir / "deep"


def test_exclude_patterns_case_sensitivity(temp_structure):
    """Test exclude patterns are case sensitive."""
    source_dir = temp_structure
    
    # Create directories with different cases (avoid conflict with existing "frontend")
    (source_dir / "Frontend_caps").mkdir()
    (source_dir / "BACKEND_caps").mkdir()
    
    patterns = ["Frontend_caps", "BACKEND_caps", "frontend"]
    exclude_patterns = ["frontend"]  # Should only exclude lowercase
    
    result = resolve_patterns(source_dir, patterns, exclude_patterns=exclude_patterns)
    
    # Should exclude only the lowercase "frontend"
    result_names = {p.name for p in result}
    assert "Frontend_caps" in result_names
    assert "BACKEND_caps" in result_names
    assert "frontend" not in result_names


def test_path_relative_with_special_characters(temp_structure):
    """Test path relative calculation with special characters in names."""
    source_dir = temp_structure
    
    # Create directories with special characters
    special_dir = source_dir / "dir-with-dashes"
    special_dir.mkdir()
    (special_dir / "file_with_underscores.txt").write_text("content")
    
    patterns = ["dir-with-dashes"]
    result = resolve_patterns(source_dir, patterns)
    
    assert len(result) == 1
    assert result[0] == special_dir
    
    # Verify relative path calculation works with special characters
    relative_path = result[0].relative_to(source_dir)
    assert str(relative_path) == "dir-with-dashes"
