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
        result = runner.invoke(app, [
            "init", 
            "--source", str(source_dir),
            "--target", str(target_dir)
        ])
        assert result.exit_code == 0
        assert "Added target 'test-target'" in result.stdout


def test_add_rule_command(temp_dirs):
    """Test the add-rule command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()
    
    # First init
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, [
            "init",
            "--source", str(source_dir),
            "--target", str(target_dir)
        ])
    
    # Add rule
    result = runner.invoke(app, [
        "add-rule",
        "--source", str(source_dir),
        "--pattern", "libs/a*",
        "--target", "test-target"
    ])
    assert result.exit_code == 0
    assert "Added rule: pattern 'libs/a*'" in result.stdout


def test_list_rules_command(temp_dirs):
    """Test the list-rules command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()
    
    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, [
            "init",
            "--source", str(source_dir),
            "--target", str(target_dir)
        ])
    
    runner.invoke(app, [
        "add-rule",
        "--source", str(source_dir),
        "--pattern", "libs/a*",
        "--target", "test-target"
    ])
    
    # List rules
    result = runner.invoke(app, ["list-rules", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Target: test-target" in result.stdout
    assert "libs/a*" in result.stdout


def test_print_config_command(temp_dirs):
    """Test the print-config command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()
    
    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, [
            "init",
            "--source", str(source_dir),
            "--target", str(target_dir)
        ])
    
    # Print config
    result = runner.invoke(app, ["print-config", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Target: test-target" in result.stdout
    
    # Test JSON format
    result = runner.invoke(app, [
        "print-config", 
        "--source", str(source_dir),
        "--format", "json"
    ])
    assert result.exit_code == 0
    assert "targets" in result.stdout


def test_apply_command(temp_dirs):
    """Test the apply command."""
    source_dir, target_dir = temp_dirs
    runner = CliRunner()
    
    # Setup
    with patch("typer.prompt", return_value="test-target"):
        runner.invoke(app, [
            "init",
            "--source", str(source_dir),
            "--target", str(target_dir)
        ])
    
    runner.invoke(app, [
        "add-rule",
        "--source", str(source_dir),
        "--pattern", "libs/a*",
        "--target", "test-target"
    ])
    
    # Apply dry run
    result = runner.invoke(app, [
        "apply",
        "--source", str(source_dir),
        "--dry"
    ])
    assert result.exit_code == 0
    assert "DRY RUN" in result.stdout
    
    # Apply actual sync
    result = runner.invoke(app, ["apply", "--source", str(source_dir)])
    assert result.exit_code == 0
    assert "Synced" in result.stdout
    
    # Check that files were synced
    assert (target_dir / "libs" / "admin" / "test.py").exists()
    assert (target_dir / "libs" / "auth" / "test.py").exists()
    assert not (target_dir / "libs" / "core" / "test.py").exists()  # Should not match libs/a*
