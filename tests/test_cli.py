"""Test arboribus CLI functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from arboribus.cli import app


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


def test_init_command(temp_dirs):
    """Test the init command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Test init without target
    result = runner.invoke(app, ["init", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Configuration saved" in result.stdout

    # Check config file was created
    config_path = source_dir / "arboribus.toml"
    assert config_path.exists()

    # Test init with target
    with patch("typer.prompt", return_value="test-target"):
        result = runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])
        assert result.exit_code == 0
        assert "Added target 'test-target'" in result.stdout


def test_init_command_nonexistent_source():
    """Test init command with nonexistent source directory."""
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--source", "/nonexistent/path"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout


def test_init_command_nonexistent_target(temp_dirs):
    """Test init command with nonexistent target directory."""
    source_dir, _ = temp_dirs
    runner = CliRunner()
    
    with patch("typer.prompt", return_value="test-target"):
        result = runner.invoke(app, ["init", "--source", str(source_dir), "--target", "/nonexistent/path"])
        assert result.exit_code == 1
        assert "does not exist" in result.stdout


def test_add_rule_command(temp_dirs):
    """Test the add-rule command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # First init
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    # Add rule
    result = runner.invoke(
        app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/a*", "--target", "test-target"]
    )
    assert result.exit_code == 0
    assert "Added rule: pattern 'libs/a*'" in result.stdout


def test_add_rule_command_no_config():
    """Test add-rule command without existing configuration."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = Path(temp_dir) / "source"
        source_dir.mkdir()
        
        result = runner.invoke(
            app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/*", "--target", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.stdout


def test_add_rule_command_nonexistent_target(temp_dirs):
    """Test add-rule command with nonexistent target."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Init without target
    runner.invoke(app, ["init", "--source", str(source_dir)])

    # Try to add rule to nonexistent target
    result = runner.invoke(
        app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/*", "--target", "nonexistent"]
    )
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_remove_rule_command(temp_dirs):
    """Test the remove-rule command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()
    
    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])
    
    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/admin", "--target", "test-target"])
    
    # Remove existing rule
    result = runner.invoke(app, ["remove-rule", "--source", str(source_dir), "--pattern", "libs/admin", "--target", "test-target"])
    assert result.exit_code == 0
    assert "Removed pattern" in result.stdout
    
    # Try to remove non-existent rule
    result = runner.invoke(app, ["remove-rule", "--source", str(source_dir), "--pattern", "nonexistent", "--target", "test-target"])
    assert result.exit_code == 0
    assert "not found" in result.stdout
    
    # Test with non-existent target
    result = runner.invoke(app, ["remove-rule", "--source", str(source_dir), "--pattern", "test", "--target", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.stdout


def test_list_rules_command(temp_dirs):
    """Test the list-rules command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/a*", "--target", "test-target"])

    # List rules
    result = runner.invoke(app, ["list-rules", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Target: test-target" in result.stdout
    assert "libs/a*" in result.stdout


def test_list_rules_command_no_targets(temp_dirs):
    """Test list-rules command with no targets."""
    source_dir, _ = temp_dirs
    runner = CliRunner()

    # Init without targets
    runner.invoke(app, ["init", "--source", str(source_dir)])

    result = runner.invoke(app, ["list-rules", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "No targets configured" in result.stdout


def test_print_config_command(temp_dirs):
    """Test the print-config command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    # Print config
    result = runner.invoke(app, ["print-config", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Target: test-target" in result.stdout

    # Test JSON format
    result = runner.invoke(app, ["print-config", "--source", str(source_dir), "--format", "json"])
    assert result.exit_code == 0
    assert "targets" in result.stdout


def test_print_config_command_no_config(temp_dirs):
    """Test print-config command with no configuration."""
    source_dir, _ = temp_dirs
    runner = CliRunner()

    # No init, so no config
    result = runner.invoke(app, ["print-config", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "No configuration found" in result.stdout


def test_apply_command(temp_dirs):
    """Test the apply command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/a*", "--target", "test-target"])

    # Apply dry run
    result = runner.invoke(app, ["apply", "--source", str(source_dir), "--dry"])
    assert result.exit_code == 0
    assert "(would copy)" in result.stdout

    # Apply actual sync
    result = runner.invoke(app, ["apply", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Sync completed" in result.stdout

    # Check that files were synced
    assert (target_dir / "libs" / "admin" / "test.py").exists()
    assert (target_dir / "libs" / "auth" / "test.py").exists()
    assert not (target_dir / "libs" / "core" / "test.py").exists()  # Should not match libs/a*


def test_apply_command_no_targets(temp_dirs):
    """Test apply command with no targets configured."""
    source_dir, _ = temp_dirs
    runner = CliRunner()

    # Init without targets
    runner.invoke(app, ["init", "--source", str(source_dir)])

    result = runner.invoke(app, ["apply", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "No targets configured" in result.stdout


def test_apply_command_no_patterns(temp_dirs):
    """Test apply command with target but no patterns."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup target but no patterns
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    result = runner.invoke(app, ["apply", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "No patterns configured" in result.stdout


def test_apply_command_stats_only(temp_dirs):
    """Test apply command with stats-only mode."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/a*", "--target", "test-target"])

    # Apply with stats only
    result = runner.invoke(app, ["apply", "--source", str(source_dir), "--stats-only"])
    assert result.exit_code == 0
    assert "Stats-only mode" in result.stdout
    assert "File Statistics" in result.stdout

    # Check that no files were actually synced
    assert not (target_dir / "libs" / "admin" / "test.py").exists()


def test_apply_command_with_filter(temp_dirs):
    """Test apply command with pattern filter."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    # Add multiple patterns
    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "libs/a*", "--target", "test-target"])
    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "apps/*", "--target", "test-target"])

    # Apply with filter to only match admin pattern
    result = runner.invoke(app, ["apply", "--source", str(source_dir), "--filter", "admin", "--dry"])
    assert result.exit_code == 0
    assert "Filtered patterns" in result.stdout


def test_apply_command_no_matches(temp_dirs):
    """Test apply command when patterns don't match anything."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()

    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, ["init", "--source", str(source_dir), "--target", str(target_dir)])

    # Add pattern that won't match anything
    runner.invoke(app, ["add-rule", "--source", str(source_dir), "--pattern", "nonexistent/*", "--target", "test-target"])

    result = runner.invoke(app, ["apply", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "No paths matched" in result.stdout


def test_command_without_source_no_default():
    """Test commands without --source when no default is available."""
    runner = CliRunner()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Change to temp directory that has no arboribus.toml
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # Test various commands that should fail without source
            commands = [
                ["add-rule", "--pattern", "test", "--target", "test"],
                ["list-rules"],
                ["print-config"],
                ["apply"]
            ]
            
            for cmd in commands:
                result = runner.invoke(app, cmd)
                assert result.exit_code == 1
                assert "No arboribus.toml found" in result.stdout
        finally:
            os.chdir(original_cwd)


def test_main_function_no_args():
    """Test main function with no arguments shows help."""
    from arboribus.cli import main
    import sys
    
    # Mock sys.argv to have only the script name
    original_argv = sys.argv
    try:
        sys.argv = ["arboribus"]
        
        # The main function should call app with ["--help"]
        # This is tested indirectly by ensuring it doesn't crash
        # and the help behavior is handled by typer
        with patch("arboribus.cli.app") as mock_app:
            main()
            mock_app.assert_called_once_with(["--help"])
    finally:
        sys.argv = original_argv


def test_main_function_with_args():
    """Test main function with arguments."""
    from arboribus.cli import main
    import sys
    
    # Mock sys.argv with some arguments
    original_argv = sys.argv
    try:
        sys.argv = ["arboribus", "init"]
        
        with patch("arboribus.cli.app") as mock_app:
            main()
            mock_app.assert_called_once_with()
    finally:
        sys.argv = original_argv
