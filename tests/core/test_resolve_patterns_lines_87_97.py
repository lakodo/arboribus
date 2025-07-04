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
    git_tracked_files = {"tracked_dir/file1.py"}
    patterns = ["tracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should be included because it contains tracked files
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"
    assert result[0].is_dir()


def test_directory_has_tracked_files_any_function(temp_structure):
    """Test lines 89-92: any() function for checking tracked files in directory."""
    source_dir = temp_structure

    # Test directory with tracked files - should trigger the any() function
    git_tracked_files = {"tracked_dir/file1.py", "tracked_dir/subdir/file2.py"}
    patterns = ["tracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # The any() function should return True, directory should be included
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_directory_no_tracked_files_any_function_false(temp_structure):
    """Test lines 89-92: any() function returns False when no tracked files."""
    source_dir = temp_structure

    # Test directory with NO tracked files - any() should return False
    git_tracked_files = {"other_dir/file.py"}  # No files in untracked_dir
    patterns = ["untracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # The any() function should return False, directory should be filtered out
    assert len(result) == 0


def test_git_tracking_startswith_logic(temp_structure):
    """Test line 90: tracked_file.startswith(str(path_relative) + "/") logic."""
    source_dir = temp_structure

    # Test with files that start with directory path + "/"
    git_tracked_files = {
        "level1/level2/level3/deep.py",  # Should match "level1/" prefix
        "other/file.py",  # Should not match
    }
    patterns = ["level1"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should be included because tracked file starts with "level1/"
    assert len(result) == 1
    assert result[0] == source_dir / "level1"


def test_git_tracking_exact_match_logic(temp_structure):
    """Test line 90: tracked_file == str(path_relative) exact match logic."""
    source_dir = temp_structure

    # Test with exact directory name match
    git_tracked_files = {"exact_match"}  # Exact match with directory name
    patterns = ["exact_match"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should be included because of exact name match
    assert len(result) == 1
    assert result[0] == source_dir / "exact_match"


def test_has_tracked_files_false_continue_execution(temp_structure):
    """Test lines 93-94: if not has_tracked_files: continue logic."""
    source_dir = temp_structure

    # Test multiple directories where some have tracked files, some don't
    git_tracked_files = {"tracked_dir/file1.py"}  # Only tracked_dir has files
    patterns = ["tracked_dir", "untracked_dir", "empty_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Only tracked_dir should be included, others should continue (be skipped)
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_directory_git_filtering_with_nested_structure(temp_structure):
    """Test directory git filtering with deeply nested tracked files."""
    source_dir = temp_structure

    # Test deeply nested file
    git_tracked_files = {"level1/level2/level3/deep.py"}
    patterns = ["level1"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # level1 should be included because it contains tracked files in subdirectories
    assert len(result) == 1
    assert result[0] == source_dir / "level1"


def test_directory_git_filtering_partial_tracking(temp_structure):
    """Test directory with some tracked and some untracked files."""
    source_dir = temp_structure

    # Only some files in directory are tracked
    git_tracked_files = {"partially_tracked/tracked.py"}  # untracked.py not tracked
    patterns = ["partially_tracked"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should still be included because it has some tracked files
    assert len(result) == 1
    assert result[0] == source_dir / "partially_tracked"


def test_directory_git_filtering_empty_directory(temp_structure):
    """Test empty directory with git filtering."""
    source_dir = temp_structure

    # Empty directory with no tracked files
    git_tracked_files = {"tracked_dir/file1.py"}
    patterns = ["empty_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Empty directory should be filtered out
    assert len(result) == 0


def test_directory_git_filtering_multiple_directories(temp_structure):
    """Test git filtering with multiple directories having different tracking states."""
    source_dir = temp_structure

    git_tracked_files = {
        "tracked_dir/file1.py",
        "level1/level2/level3/deep.py",
        "exact_match",  # Exact match
    }
    patterns = ["tracked_dir", "untracked_dir", "level1", "exact_match", "empty_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should include: tracked_dir, level1, exact_match
    # Should exclude: untracked_dir, empty_dir
    assert len(result) == 3
    result_names = {p.name for p in result}
    assert "tracked_dir" in result_names
    assert "level1" in result_names
    assert "exact_match" in result_names
    assert "untracked_dir" not in result_names
    assert "empty_dir" not in result_names


def test_git_tracking_prefix_match_edge_cases(temp_structure):
    """Test edge cases for prefix matching in git tracking."""
    source_dir = temp_structure

    # Create directories with similar names to test precise prefix matching
    (source_dir / "test").mkdir()
    (source_dir / "test_similar").mkdir()
    (source_dir / "test" / "file.py").write_text("# test file")
    (source_dir / "test_similar" / "file.py").write_text("# similar file")

    # Only track file in "test" directory
    git_tracked_files = {"test/file.py"}
    patterns = ["test", "test_similar"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Only "test" should be included, not "test_similar"
    # This tests that the prefix matching uses exact "test/" not just "test"
    assert len(result) == 1
    assert result[0] == source_dir / "test"


def test_directory_exact_name_vs_prefix_matching(temp_structure):
    """Test the OR condition: exact match vs prefix match."""
    source_dir = temp_structure

    # Test both conditions of the OR: exact match and prefix match
    (source_dir / "exact_dir").mkdir()
    (source_dir / "prefix_dir").mkdir()
    (source_dir / "prefix_dir" / "sub").mkdir(parents=True)
    (source_dir / "prefix_dir" / "sub" / "file.py").write_text("# prefix file")

    git_tracked_files = {
        "exact_dir",  # Exact match for exact_dir
        "prefix_dir/sub/file.py",  # Prefix match for prefix_dir
    }
    patterns = ["exact_dir", "prefix_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Both should be included: one by exact match, one by prefix match
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "exact_dir" in result_names
    assert "prefix_dir" in result_names


def test_git_tracking_with_special_characters_in_paths(temp_structure):
    """Test git tracking with special characters in directory names."""
    source_dir = temp_structure

    # Create directories with special characters
    (source_dir / "dir-with-dashes").mkdir()
    (source_dir / "dir_with_underscores").mkdir()
    (source_dir / "dir.with.dots").mkdir()

    (source_dir / "dir-with-dashes" / "file.py").write_text("# dash file")
    (source_dir / "dir_with_underscores" / "file.py").write_text("# underscore file")
    (source_dir / "dir.with.dots" / "file.py").write_text("# dot file")

    git_tracked_files = {
        "dir-with-dashes/file.py",
        "dir_with_underscores/file.py",
        # dir.with.dots not tracked
    }
    patterns = ["dir-with-dashes", "dir_with_underscores", "dir.with.dots"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should include directories with tracked files
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "dir-with-dashes" in result_names
    assert "dir_with_underscores" in result_names
    assert "dir.with.dots" not in result_names


def test_any_function_with_large_git_tracked_set(temp_structure):
    """Test any() function performance with larger set of tracked files."""
    source_dir = temp_structure

    # Create a directory with many files
    (source_dir / "large_dir").mkdir()
    for i in range(10):
        (source_dir / "large_dir" / f"file_{i}.py").write_text(f"# file {i}")

    # Track only some files
    git_tracked_files = {
        f"large_dir/file_{i}.py"
        for i in range(5)  # Track first 5 files
    }
    # Add many other unrelated tracked files
    git_tracked_files.update({f"other/file_{i}.py" for i in range(100)})

    patterns = ["large_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Directory should be included because it has some tracked files
    assert len(result) == 1
    assert result[0] == source_dir / "large_dir"


def test_continue_statement_execution_flow(temp_structure):
    """Test that continue statement properly skips to next pattern."""
    source_dir = temp_structure

    # Create pattern where first directory is filtered out, second is included
    git_tracked_files = {"tracked_dir/file1.py"}
    patterns = ["untracked_dir", "tracked_dir"]  # First will continue, second will be included

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should only include tracked_dir (untracked_dir should be continued/skipped)
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_path_relative_string_conversion_in_git_check(temp_structure):
    """Test str(path_relative) conversion in git tracking check."""
    source_dir = temp_structure

    # Test that path_relative is properly converted to string for comparison
    git_tracked_files = {"tracked_dir/file1.py"}
    patterns = ["tracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # This tests that str(path_relative) works correctly
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_directory_filtering_with_mixed_file_and_dir_patterns(temp_structure):
    """Test directory git filtering when mixed with file patterns."""
    source_dir = temp_structure

    # Create a file alongside directories
    (source_dir / "standalone_file.py").write_text("# standalone")

    git_tracked_files = {"tracked_dir/file1.py", "standalone_file.py"}
    patterns = ["tracked_dir", "untracked_dir", "standalone_file.py"]

    # Test with include_files=True to include the file
    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files, include_files=True)

    # Should include tracked_dir and standalone_file.py, but not untracked_dir
    assert len(result) == 2
    result_names = {p.name for p in result}
    assert "tracked_dir" in result_names
    assert "standalone_file.py" in result_names
    assert "untracked_dir" not in result_names


def test_line_86_file_continue_statement(temp_structure):
    """Test line 86: continue statement for untracked files."""
    source_dir = temp_structure

    # Create a file that is NOT tracked
    (source_dir / "untracked_file.py").write_text("# untracked")

    git_tracked_files = {"tracked_dir/file1.py"}  # untracked_file.py not included
    patterns = ["untracked_file.py", "tracked_dir"]  # Mix untracked file with tracked dir

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files, include_files=True)

    # Should only include tracked_dir, untracked_file.py should hit continue on line 86
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_line_95_directory_continue_statement(temp_structure):
    """Test line 95: continue statement for directories with no tracked files."""
    source_dir = temp_structure

    git_tracked_files = {"tracked_dir/file1.py"}  # Only tracked_dir has files
    patterns = ["untracked_dir", "empty_dir", "tracked_dir"]  # Mix untracked dirs with tracked

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should only include tracked_dir, others should hit continue on line 95
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_line_98_99_exclude_patterns_continue(temp_structure):
    """Test lines 98-99: exclude patterns continue statement."""
    source_dir = temp_structure

    # Test exclude patterns that should trigger the continue statement
    git_tracked_files = {"tracked_dir/file1.py", "partially_tracked/tracked.py"}
    patterns = ["tracked_dir", "partially_tracked"]
    exclude_patterns = ["partially_tracked"]  # Exclude one of the tracked directories

    result = resolve_patterns(
        source_dir, patterns, exclude_patterns=exclude_patterns, git_tracked_files=git_tracked_files
    )

    # Should only include tracked_dir, partially_tracked should hit continue on line 99
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_multiple_continue_statements_in_sequence(temp_structure):
    """Test hitting multiple different continue statements."""
    source_dir = temp_structure

    # Create additional test files/dirs
    (source_dir / "untracked_file.txt").write_text("# untracked file")
    (source_dir / "excluded_dir").mkdir()
    (source_dir / "excluded_dir" / "file.py").write_text("# excluded")

    git_tracked_files = {
        "tracked_dir/file1.py",  # tracked_dir is tracked
        "excluded_dir/file.py",  # excluded_dir is tracked but will be excluded
    }
    patterns = [
        "untracked_file.txt",  # Should hit line 86 continue (untracked file)
        "untracked_dir",  # Should hit line 95 continue (untracked directory)
        "excluded_dir",  # Should hit line 99 continue (excluded directory)
        "tracked_dir",  # Should be included
    ]
    exclude_patterns = ["excluded_dir"]

    result = resolve_patterns(
        source_dir, patterns, exclude_patterns=exclude_patterns, git_tracked_files=git_tracked_files, include_files=True
    )

    # Only tracked_dir should be included, all others should hit various continue statements
    assert len(result) == 1
    assert result[0] == source_dir / "tracked_dir"


def test_any_function_generator_expression_execution(temp_structure):
    """Test that the any() function generator expression is fully executed."""
    source_dir = temp_structure

    # Create a directory structure that will cause the any() function to iterate
    # through multiple git tracked files before finding/not finding a match
    (source_dir / "test_dir").mkdir()
    (source_dir / "test_dir" / "file1.py").write_text("# file 1")

    # Create git tracked files that don't match the directory we're testing
    # This should cause the generator expression to evaluate multiple conditions
    git_tracked_files = {
        "other_dir/file1.py",  # Doesn't start with "test_dir/"
        "another_dir/file2.py",  # Doesn't start with "test_dir/"
        "different_dir/file3.py",  # Doesn't start with "test_dir/"
        "test_dir_different/file.py",  # Similar name but different
        "test_dir",  # Exact match - this should make has_tracked_files True
    }
    patterns = ["test_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should be included because "test_dir" is an exact match
    assert len(result) == 1
    assert result[0] == source_dir / "test_dir"


def test_has_tracked_files_false_forces_continue_line_95(temp_structure):
    """Test specifically to force line 95 continue statement execution."""
    source_dir = temp_structure

    # Create directory that has NO tracked files
    (source_dir / "completely_untracked").mkdir()
    (source_dir / "completely_untracked" / "file.py").write_text("# untracked")

    # Use EMPTY git tracked files set - this forces any() to return False
    git_tracked_files = set()  # Empty set - no files are tracked!
    patterns = ["completely_untracked"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should be empty because completely_untracked has no tracked files
    # This should execute: has_tracked_files = any(...) -> False
    # Then: if not has_tracked_files: continue -> line 95
    assert len(result) == 0


def test_empty_git_tracked_files_forces_any_false(temp_structure):
    """Test with empty git_tracked_files to force any() to return False."""
    source_dir = temp_structure

    # Multiple directories, but NO tracked files
    git_tracked_files = set()  # Empty - no files tracked at all
    patterns = ["tracked_dir", "untracked_dir", "empty_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # All directories should be filtered out because any() returns False for all
    assert len(result) == 0


def test_line_95_continue_with_tracing(temp_structure):
    """Test line 95 continue with explicit tracing."""
    source_dir = temp_structure

    # Create multiple directories to ensure we go through the loop multiple times
    (source_dir / "dir1").mkdir()
    (source_dir / "dir2").mkdir()
    (source_dir / "dir3").mkdir()

    # Empty git tracked files - should cause all directories to hit continue on line 95
    git_tracked_files = set()
    patterns = ["dir1", "dir2", "dir3", "tracked_dir", "untracked_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # All should be filtered out due to empty git tracking
    assert len(result) == 0


def test_mixed_scenarios_force_all_continue_paths(temp_structure):
    """Test to force all different continue statements to execute."""
    source_dir = temp_structure

    # Create files and directories for comprehensive testing
    (source_dir / "untracked_file.py").write_text("# untracked file")
    (source_dir / "empty_tracked_dir").mkdir()
    (source_dir / "excluded_tracked_dir").mkdir()
    (source_dir / "excluded_tracked_dir" / "file.py").write_text("# tracked but excluded")

    # Mix of scenarios:
    # - empty git tracked files should cause line 95 continue for directories
    # - untracked files should cause line 86 continue
    # - exclude patterns should cause line 99 continue
    git_tracked_files = set()  # Empty set
    patterns = [
        "untracked_file.py",  # File, should be filtered by git (line 86)
        "empty_tracked_dir",  # Dir, should be filtered by git (line 95)
        "excluded_tracked_dir",  # Dir, would be filtered by exclude (but git first)
    ]
    exclude_patterns = ["excluded_tracked_dir"]

    result = resolve_patterns(
        source_dir, patterns, exclude_patterns=exclude_patterns, git_tracked_files=git_tracked_files, include_files=True
    )

    # All should be filtered out by git filtering (empty set)
    assert len(result) == 0


def test_generator_expression_multiple_iterations(temp_structure):
    """Test generator expression with multiple iterations to hit lines 90-91."""
    source_dir = temp_structure

    # Create a scenario where the generator needs to check many files
    (source_dir / "target_dir").mkdir()

    # Create many git tracked files that will cause multiple iterations
    # of the generator expression before finding a match
    git_tracked_files = set()

    # Add many unrelated files first
    for i in range(20):
        git_tracked_files.add(f"unrelated_{i}/file.py")

    # Add one file that will match via startswith
    git_tracked_files.add("target_dir/matching_file.py")

    patterns = ["target_dir"]

    result = resolve_patterns(source_dir, patterns, git_tracked_files=git_tracked_files)

    # Should be included because "target_dir/matching_file.py" starts with "target_dir/"
    assert len(result) == 1
    assert result[0] == source_dir / "target_dir"
