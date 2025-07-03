"""Arboribus CLI - Sync folders from monorepo to external targets."""

import glob
import json
import os
import shutil
import toml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pathspec
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="🪵 Arboribus - Sync folders from monorepo to external targets")
console = Console()


def get_config_path(source_dir: Path) -> Path:
    """Get the path to the arboribus.toml config file."""
    return source_dir / "arboribus.toml"


def load_config(source_dir: Path) -> Dict:
    """Load the arboribus.toml config file."""
    config_path = get_config_path(source_dir)
    if not config_path.exists():
        return {"targets": {}}
    
    with open(config_path, "r") as f:
        return toml.load(f)


def save_config(source_dir: Path, config: Dict) -> None:
    """Save the arboribus.toml config file."""
    config_path = get_config_path(source_dir)
    with open(config_path, "w") as f:
        toml.dump(config, f)


def get_gitignore_spec(source_dir: Path) -> Optional[pathspec.PathSpec]:
    """Load .gitignore patterns from source directory."""
    gitignore_path = source_dir / ".gitignore"
    if not gitignore_path.exists():
        return None
    
    with open(gitignore_path, "r") as f:
        patterns = f.read().splitlines()
    
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def resolve_patterns(source_dir: Path, patterns: List[str], filters: Optional[List[str]] = None, gitignore_spec: Optional[pathspec.PathSpec] = None) -> List[Path]:
    """Resolve glob patterns to actual directories."""
    matched_dirs = []
    
    for pattern in patterns:
        # Use glob to find matching directories
        full_pattern = source_dir / pattern
        matched_paths = glob.glob(str(full_pattern))
        
        # Also try recursive matching for patterns with wildcards
        if '*' in pattern:
            matched_paths.extend(glob.glob(str(full_pattern), recursive=True))
        
        for path in matched_paths:
            path_obj = Path(path)
            if path_obj.is_dir():
                path_relative = path_obj.relative_to(source_dir)
                
                # Apply gitignore filtering
                if gitignore_spec and gitignore_spec.match_file(str(path_relative)):
                    continue
                
                # Apply filters if specified
                if filters:
                    if any(str(path_relative).startswith(f) for f in filters):
                        continue
                
                matched_dirs.append(path_obj)
    
    return sorted(set(matched_dirs))


def sync_directory(source: Path, target: Path, reverse: bool = False, dry: bool = False, gitignore_spec: Optional[pathspec.PathSpec] = None) -> None:
    """Sync a single directory."""
    if reverse:
        source, target = target, source
    
    if dry:
        console.print(f"[yellow]DRY RUN:[/yellow] Would sync [blue]{source}[/blue] -> [green]{target}[/green]")
        return
    
    if target.exists():
        shutil.rmtree(target)
    
    def ignore_func(directory: str, files: List[str]) -> List[str]:
        """Ignore function for shutil.copytree."""
        if gitignore_spec is None:
            return []
        
        ignored = []
        for file in files:
            file_path = Path(directory) / file
            relative_path = file_path.relative_to(source)
            if gitignore_spec.match_file(str(relative_path)):
                ignored.append(file)
        return ignored
    
    shutil.copytree(source, target, ignore=ignore_func)
    console.print(f"[green]✓[/green] Synced [blue]{source}[/blue] -> [green]{target}[/green]")


def get_default_source() -> Path:
    """Get the default source directory (current directory if it has arboribus.toml)."""
    current_dir = Path.cwd()
    if (current_dir / "arboribus.toml").exists():
        return current_dir
    return None


@app.command()
def init(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Target directory"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Target name"),
) -> None:
    """Initialize arboribus configuration."""
    if source:
        source_dir = Path(source).resolve()
    else:
        source_dir = Path.cwd()
    
    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)
    
    # Load existing config or create new one
    config = load_config(source_dir)
    
    # Add target if specified
    if target:
        if not name:
            name = typer.prompt("Enter a name for this target")
        
        target_dir = Path(target).resolve()
        if not target_dir.exists():
            console.print(f"[red]Error:[/red] Target directory {target_dir} does not exist")
            raise typer.Exit(1)
        
        if "targets" not in config:
            config["targets"] = {}
        
        config["targets"][name] = {
            "path": str(target_dir),
            "patterns": [],
            "filters": []
        }
        
        console.print(f"[green]✓[/green] Added target '{name}' -> {target_dir}")
    
    # Save config
    save_config(source_dir, config)
    console.print(f"[green]✓[/green] Configuration saved to {get_config_path(source_dir)}")


@app.command()
def add_rule(
    pattern: str = typer.Option(..., "--pattern", "-p", help="Glob pattern to include"),
    target_name: str = typer.Option(..., "--target", "-t", help="Target name"),
    filter_pattern: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter pattern to exclude"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """Add a sync rule to a target."""
    if source:
        source_dir = Path(source).resolve()
    else:
        source_dir = get_default_source()
        if source_dir is None:
            console.print("[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory.")
            raise typer.Exit(1)
    
    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)
    
    config = load_config(source_dir)
    
    if "targets" not in config or target_name not in config["targets"]:
        console.print(f"[red]Error:[/red] Target '{target_name}' not found. Use 'arboribus init' first.")
        raise typer.Exit(1)
    
    target_config = config["targets"][target_name]
    
    # Add pattern
    if pattern not in target_config["patterns"]:
        target_config["patterns"].append(pattern)
    
    # Add filter if specified
    if filter_pattern and filter_pattern not in target_config["filters"]:
        target_config["filters"].append(filter_pattern)
    
    # Save config
    save_config(source_dir, config)
    console.print(f"[green]✓[/green] Added rule: pattern '{pattern}' to target '{target_name}'")
    if filter_pattern:
        console.print(f"[green]✓[/green] Added filter: '{filter_pattern}'")


@app.command()
def list_rules(
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """List all sync rules and their resolved paths."""
    if source:
        source_dir = Path(source).resolve()
    else:
        source_dir = get_default_source()
        if source_dir is None:
            console.print("[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory.")
            raise typer.Exit(1)
    
    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)
    
    config = load_config(source_dir)
    
    if "targets" not in config or not config["targets"]:
        console.print("[yellow]No targets configured.[/yellow]")
        return
    
    for target_name, target_config in config["targets"].items():
        console.print(f"\n[bold blue]Target: {target_name}[/bold blue]")
        console.print(f"Path: {target_config['path']}")
        
        if not target_config["patterns"]:
            console.print("[yellow]No patterns configured.[/yellow]")
            continue
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Pattern")
        table.add_column("Filters")
        table.add_column("Matched Directories")
        table.add_column("Target Path")
        
        for pattern in target_config["patterns"]:
            matched_dirs = resolve_patterns(
                source_dir, 
                [pattern], 
                target_config.get("filters", [])
            )
            
            filters_str = ", ".join(target_config.get("filters", [])) or "None"
            if matched_dirs:
                matched_str = "\n".join([str(d.relative_to(source_dir)) for d in matched_dirs])
                target_paths = "\n".join([
                    str(Path(target_config["path"]) / d.relative_to(source_dir)) 
                    for d in matched_dirs
                ])
            else:
                matched_str = f"No matches for pattern '{pattern}'"
                target_paths = "N/A"
            
            table.add_row(pattern, filters_str, matched_str, target_paths)
        
        console.print(table)


@app.command()
def apply(
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Sync from target to source"),
    dry: bool = typer.Option(False, "--dry", "-d", help="Dry run - show what would be done"),
    filter_pattern: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter to specific pattern"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """Apply sync rules."""
    if source:
        source_dir = Path(source).resolve()
    else:
        source_dir = get_default_source()
        if source_dir is None:
            console.print("[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory.")
            raise typer.Exit(1)
    
    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)
    
    config = load_config(source_dir)
    
    if "targets" not in config or not config["targets"]:
        console.print("[yellow]No targets configured.[/yellow]")
        return
    
    # Load .gitignore patterns
    gitignore_spec = get_gitignore_spec(source_dir)
    
    for target_name, target_config in config["targets"].items():
        if not target_config["patterns"]:
            console.print(f"[yellow]No patterns configured for target '{target_name}'.[/yellow]")
            continue
        
        console.print(f"\n[bold blue]Syncing target: {target_name}[/bold blue]")
        
        patterns_to_sync = target_config["patterns"]
        if filter_pattern:
            patterns_to_sync = [p for p in patterns_to_sync if filter_pattern in p]
        
        for pattern in patterns_to_sync:
            matched_dirs = resolve_patterns(
                source_dir, 
                [pattern], 
                target_config.get("filters", [])
            )
            
            for source_path in matched_dirs:
                relative_path = source_path.relative_to(source_dir)
                target_path = Path(target_config["path"]) / relative_path
                
                try:
                    sync_directory(source_path, target_path, reverse, dry, gitignore_spec)
                except Exception as e:
                    console.print(f"[red]Error syncing {source_path}: {e}[/red]")


@app.command()
def print_config(
    format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """Print the current configuration."""
    if source:
        source_dir = Path(source).resolve()
    else:
        source_dir = get_default_source()
        if source_dir is None:
            console.print("[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory.")
            raise typer.Exit(1)
    
    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)
    
    config = load_config(source_dir)
    
    if format == "json":
        console.print(json.dumps(config, indent=2))
        return
    
    if "targets" not in config or not config["targets"]:
        console.print("[yellow]No configuration found.[/yellow]")
        return
    
    for target_name, target_config in config["targets"].items():
        console.print(f"\n[bold blue]Target: {target_name}[/bold blue]")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Property")
        table.add_column("Value")
        
        table.add_row("Path", str(target_config["path"]))
        table.add_row("Patterns", ", ".join(target_config.get("patterns", [])) or "None")
        table.add_row("Filters", ", ".join(target_config.get("filters", [])) or "None")
        
        console.print(table)


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
