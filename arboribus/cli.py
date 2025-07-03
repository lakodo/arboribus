"""Arboribus CLI - Sync folders from monorepo to external targets."""

import fnmatch
import glob
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import toml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.logging import RichHandler

app = typer.Typer(help="🪵 Arboribus - Sync folders from monorepo to external targets")
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[RichHandler(console=console, show_time=False)]
)
logger = logging.getLogger("arboribus")


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


def get_git_tracked_files(source_dir: Path) -> Optional[set]:
    """Get all git-tracked files from the repository."""
    try:
        import subprocess
        
        # Check if we're in a gt repository
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=source_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            console.print(f"[yellow]Warning: {source_dir} is not a git repository. Skipping git-based filtering.[/yellow]")
            return None
        
        # Get all tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=source_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            console.print(f"[yellow]Warning: Failed to get git tracked files: {result.stderr}[/yellow]")
            return None
        
        # Return set of tracked file paths (relative to source_dir)
        tracked_files = set()
        for line in result.stdout.splitlines():
            if line.strip():
                tracked_files.add(line.strip())
        
        console.print(f"[dim]Found {len(tracked_files)} git-tracked files[/dim]")
        return tracked_files
        
    except Exception as e:
        console.print(f"[yellow]Warning: Could not get git tracked files: {e}[/yellow]")
        return None


def resolve_patterns(source_dir: Path, patterns: List[str], exclude_patterns: Optional[List[str]] = None, git_tracked_files: Optional[set] = None, include_files: bool = False) -> List[Path]:
    """Resolve glob patterns to actual directories and files."""
    matched_paths = []
    
    for pattern in patterns:
        # First, try direct path matching (for patterns like "frontend")
        direct_path = source_dir / pattern
        if direct_path.exists():
            if direct_path.is_dir() or (include_files and direct_path.is_file()):
                path_relative = direct_path.relative_to(source_dir)
                
                # Apply git filtering if available
                if git_tracked_files is not None:
                    if direct_path.is_file():
                        # For files, check if they're tracked
                        if str(path_relative) not in git_tracked_files:
                            continue
                    elif direct_path.is_dir():
                        # For directories, check if they contain any tracked files
                        has_tracked_files = any(
                            tracked_file.startswith(str(path_relative) + "/") or tracked_file == str(path_relative)
                            for tracked_file in git_tracked_files
                        )
                        if not has_tracked_files:
                            continue
                
                # Apply exclude patterns if specified
                if exclude_patterns:
                    if any(str(path_relative).startswith(f) for f in exclude_patterns):
                        continue
                
                matched_paths.append(direct_path)
                continue
        
        # Then try glob pattern matching
        full_pattern = source_dir / pattern
        matched_glob_paths = glob.glob(str(full_pattern))
        
        # Also try recursive matching for patterns with wildcards
        if '*' in pattern:
            matched_glob_paths.extend(glob.glob(str(full_pattern), recursive=True))
        
        for path in matched_glob_paths:
            path_obj = Path(path)
            
            # Include both files and directories if requested, otherwise only directories
            if path_obj.is_dir() or (include_files and path_obj.is_file()):
                path_relative = path_obj.relative_to(source_dir)
                
                # Apply git filtering if available
                if git_tracked_files is not None:
                    if path_obj.is_file():
                        # For files, check if they're tracked
                        if str(path_relative) not in git_tracked_files:
                            continue
                    elif path_obj.is_dir():
                        # For directories, check if they contain any tracked files
                        has_tracked_files = any(
                            tracked_file.startswith(str(path_relative) + "/") or tracked_file == str(path_relative)
                            for tracked_file in git_tracked_files
                        )
                        if not has_tracked_files:
                            continue
                
                # Apply exclude patterns if specified
                if exclude_patterns:
                    if any(str(path_relative).startswith(f) for f in exclude_patterns):
                        continue
                
                matched_paths.append(path_obj)
    
    return sorted(set(matched_paths))


def sync_directory(source: Path, target: Path, reverse: bool = False, dry: bool = False, git_tracked_files: Optional[set] = None) -> None:
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
        if git_tracked_files is None:
            return []
        
        ignored = []
        dir_path = Path(directory)
        
        # Find the source root directory
        try:
            source_root = source
            while source_root.parent != source_root:
                if (source_root / "arboribus.toml").exists():
                    break
                source_root = source_root.parent
            
            for file in files:
                file_path = dir_path / file
                # Calculate relative path from the source root (monorepo root)
                if file_path.is_relative_to(source_root):
                    relative_path = file_path.relative_to(source_root)
                    # Check if file is git-tracked
                    if str(relative_path) not in git_tracked_files:
                        ignored.append(file)
        except Exception as e:
            console.print(f"[yellow]Warning: Error in ignore function: {e}[/yellow]")
        
        return ignored
    
    try:
        shutil.copytree(source, target, ignore=ignore_func)
        console.print(f"[green]✓[/green] Synced [blue]{source}[/blue] -> [green]{target}[/green]")
    except Exception as e:
        console.print(f"[red]Error during sync: {e}[/red]")
        raise


def collect_files_recursive(directory: Path, source_dir: Path, git_tracked_files: Optional[set] = None) -> List[Path]:
    """Recursively collect files from a directory, respecting git tracking."""
    files = []
    
    try:
        for item in directory.rglob("*"):
            if item.is_file():
                # Calculate relative path from source root
                relative_path = item.relative_to(source_dir)
                
                # Check if file is git-tracked
                if git_tracked_files is not None and str(relative_path) not in git_tracked_files:
                    continue
                
                files.append(item)
    except (PermissionError, OSError) as e:
        console.print(f"[yellow]Warning: Cannot access some files in {directory}: {e}[/yellow]")
    
    return files


def get_file_statistics(paths: List[Path], source_dir: Path, git_tracked_files: Optional[set] = None) -> Dict[str, int]:
    """Get statistics about files by extension, respecting git tracking."""
    stats = {}
    total_files = 0
    total_dirs = 0
    
    for path in paths:
        if path.is_file():
            # Check if file is git-tracked
            relative_path = path.relative_to(source_dir)
            if git_tracked_files is not None and str(relative_path) not in git_tracked_files:
                continue
                
            total_files += 1
            ext = path.suffix.lower() if path.suffix else "(no extension)"
            stats[ext] = stats.get(ext, 0) + 1
        elif path.is_dir():
            total_dirs += 1
            # Recursively collect files from directory with git filtering
            files = collect_files_recursive(path, source_dir, git_tracked_files)
            for file_path in files:
                total_files += 1
                ext = file_path.suffix.lower() if file_path.suffix else "(no extension)"
                stats[ext] = stats.get(ext, 0) + 1
    
    # Add summary
    stats["[TOTAL FILES]"] = total_files
    stats["[TOTAL DIRS]"] = total_dirs
    
    return stats


def print_file_statistics(stats: Dict[str, int]) -> None:
    """Print file statistics in a nice table."""
    if not stats:
        console.print("[yellow]No files found.[/yellow]")
        return
    
    # Separate summary from extensions
    total_files = stats.pop("[TOTAL FILES]", 0)
    total_dirs = stats.pop("[TOTAL DIRS]", 0)
    
    console.print(f"\n[bold blue]📊 File Statistics:[/bold blue]")
    console.print(f"[green]Total files: {total_files:,}[/green]")
    console.print(f"[green]Total directories: {total_dirs:,}[/green]")
    
    if not stats:
        return
    
    # Create table for extensions
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Extension", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_column("Percentage", style="yellow", justify="right")
    
    # Sort by count (descending)
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    
    for ext, count in sorted_stats:
        percentage = (count / total_files * 100) if total_files > 0 else 0
        table.add_row(ext, f"{count:,}", f"{percentage:.1f}%")
    
    console.print(table)


def get_default_source() -> Path:
    """Get the default source directory (current directory if it has arboribus.toml)."""
    current_dir = Path.cwd()
    if (current_dir / "arboribus.toml").exists():
        return current_dir
    return None


def get_file_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    import hashlib
    
    hash_sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        console.print(f"[yellow]Warning: Could not calculate checksum for {file_path}: {e}[/yellow]")
        return ""


def process_path(source_path: Path, target_path: Path, source_dir: Path, git_tracked_files: Optional[set], dry: bool = False, replace_existing: bool = False) -> bool:
    """
    Process a single path (file or directory) for syncing.
    
    Returns True if the path was processed (or would be in dry mode), False if ignored.
    """
    relative_path = source_path.relative_to(source_dir)
    
    # Check if path is git-tracked
    if git_tracked_files is not None:
        if source_path.is_file():
            # For files, check if they're tracked
            if str(relative_path) not in git_tracked_files:
                console.print(f"[dim]Ignoring {relative_path} (not git-tracked)[/dim]")
                return False
        elif source_path.is_dir():
            # For directories, check if they contain any tracked files
            has_tracked_files = any(
                tracked_file.startswith(str(relative_path) + "/") or tracked_file == str(relative_path)
                for tracked_file in git_tracked_files
            )
            if not has_tracked_files:
                console.print(f"[dim]Ignoring {relative_path} (no git-tracked files)[/dim]")
                return False
    
    # Check if target already exists (only for files, not directories)
    if target_path.exists() and source_path.is_file():
        # For files, check if they have the same checksum
        if target_path.is_file():
            source_checksum = get_file_checksum(source_path)
            target_checksum = get_file_checksum(target_path)
            
            if source_checksum and target_checksum and source_checksum == target_checksum:
                console.print(f"[dim]Skipping {relative_path} (identical checksum - already up to date)[/dim]")
                return False
        
        if not replace_existing:
            console.print(f"[dim]Ignoring {relative_path} (target exists, use --replace-existing to overwrite)[/dim]")
            return False
        else:
            if dry:
                console.print(f"[yellow]DRY RUN:[/yellow] Would replace existing [cyan]{target_path}[/cyan]")
            else:
                console.print(f"[yellow]Replacing existing {target_path}[/yellow]")
    
    # Process the path
    if source_path.is_file():
        if dry:
            console.print(f"[yellow]DRY RUN:[/yellow] Would copy file [blue]{source_path}[/blue] -> [green]{target_path}[/green]")
        else:
            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            console.print(f"[green]✓[/green] Copied file [blue]{relative_path}[/blue]")
    elif source_path.is_dir():
        if dry:
            console.print(f"[yellow]DRY RUN:[/yellow] Would sync directory [blue]{source_path}[/blue] -> [green]{target_path}[/green]")
        else:
            # Remove target if it exists and we're replacing
            if target_path.exists() and replace_existing:
                shutil.rmtree(target_path)
            
            def ignore_func(directory: str, files: List[str]) -> List[str]:
                """Ignore function for shutil.copytree."""
                if git_tracked_files is None:
                    return []
                
                ignored = []
                dir_path = Path(directory)
                
                for file in files:
                    file_path = dir_path / file
                    # Calculate relative path from the source root (monorepo root)
                    if file_path.is_relative_to(source_dir):
                        relative_file_path = file_path.relative_to(source_dir)
                        # Check if file is git-tracked
                        if str(relative_file_path) not in git_tracked_files:
                            ignored.append(file)
                
                return ignored
            
            try:
                shutil.copytree(source_path, target_path, ignore=ignore_func, dirs_exist_ok=replace_existing)
                console.print(f"[green]✓[/green] Synced directory [blue]{relative_path}[/blue]")
            except Exception as e:
                console.print(f"[red]Error syncing directory {relative_path}: {e}[/red]")
                return False
    
    return True


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
            "exclude-patterns": []
        }
        
        console.print(f"[green]✓[/green] Added target '{name}' -> {target_dir}")
    
    # Save config
    save_config(source_dir, config)
    console.print(f"[green]✓[/green] Configuration saved to {get_config_path(source_dir)}")


@app.command()
def add_rule(
    pattern: str = typer.Option(..., "--pattern", "-p", help="Glob pattern to include"),
    target_name: str = typer.Option(..., "--target", "-t", help="Target name"),
    exclude_pattern: Optional[str] = typer.Option(None, "--exclude", "-e", help="Exclude pattern"),
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
    
    # Add exclude pattern if specified
    if exclude_pattern and exclude_pattern not in target_config["exclude-patterns"]:
        target_config["exclude-patterns"].append(exclude_pattern)
    
    # Save config
    save_config(source_dir, config)
    console.print(f"[green]✓[/green] Added rule: pattern '{pattern}' to target '{target_name}'")
    if exclude_pattern:
        console.print(f"[green]✓[/green] Added exclude pattern: '{exclude_pattern}'")


@app.command()
def remove_rule(
    pattern: str = typer.Option(..., "--pattern", "-p", help="Pattern to remove"),
    target_name: str = typer.Option(..., "--target", "-t", help="Target name"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """Remove a sync rule from a target."""
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
        console.print(f"[red]Error:[/red] Target '{target_name}' not found.")
        raise typer.Exit(1)
    
    target_config = config["targets"][target_name]
    
    # Remove pattern if it exists
    if pattern in target_config["patterns"]:
        target_config["patterns"].remove(pattern)
        # Save config
        save_config(source_dir, config)
        console.print(f"[green]✓[/green] Removed pattern '{pattern}' from target '{target_name}'")
    else:
        console.print(f"[yellow]Pattern '{pattern}' not found in target '{target_name}'[/yellow]")
        console.print(f"Available patterns: {', '.join(target_config['patterns'])}")


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
        table.add_column("Exclude Patterns")
        table.add_column("Matched Directories")
        table.add_column("Target Path")
        
        for pattern in target_config["patterns"]:
            # Get git tracked files for filtering
            git_tracked_files = get_git_tracked_files(source_dir)
            
            matched_dirs = resolve_patterns(
                source_dir, 
                [pattern], 
                target_config.get("exclude-patterns", []),
                git_tracked_files
            )
            
            exclude_patterns_str = ", ".join(target_config.get("exclude-patterns", [])) or "None"
            if matched_dirs:
                matched_str = "\n".join([str(d.relative_to(source_dir)) for d in matched_dirs])
                target_paths = "\n".join([
                    str(Path(target_config["path"]) / d.relative_to(source_dir)) 
                    for d in matched_dirs
                ])
            else:
                matched_str = f"No matches for pattern '{pattern}'"
                target_paths = "N/A"
            
            table.add_row(pattern, exclude_patterns_str, matched_str, target_paths)
        
        console.print(table)


@app.command()
def apply(
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Sync from target to source"),
    dry: bool = typer.Option(False, "--dry", "-d", help="Dry run - show what would be done"),
    filter_pattern: Optional[str] = typer.Option(None, "--filter", "-f", help="Filter to specific pattern"),
    limit: int = typer.Option(100, "--limit", "-l", help="Limit number of files to display (default: 100)"),
    stats_only: bool = typer.Option(False, "--stats-only", help="Only show statistics, don't sync"),
    include_files: bool = typer.Option(False, "--include-files", help="Include individual files in pattern matching"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Replace existing files/directories in target"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Source root directory (default: current directory)"),
) -> None:
    """Apply sync rules with file statistics and preview."""
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
    
    # Load git tracked files
    git_tracked_files = get_git_tracked_files(source_dir)
    
    for target_name, target_config in config["targets"].items():
        if not target_config["patterns"]:
            console.print(f"[yellow]No patterns configured for target '{target_name}'.[/yellow]")
            continue
        
        console.print(f"\n[bold blue]Processing target: {target_name}[/bold blue]")
        console.print(f"Target path: {target_config['path']}")
        
        patterns_to_sync = target_config["patterns"]
        if filter_pattern:
            # Support glob pattern matching for filter
            patterns_to_sync = []
            for p in target_config["patterns"]:
                if filter_pattern in p or fnmatch.fnmatch(p, filter_pattern):
                    patterns_to_sync.append(p)
            console.print(f"[cyan]Filtered patterns:[/cyan] {patterns_to_sync}")
            if not patterns_to_sync:
                console.print(f"[yellow]No patterns matched filter '{filter_pattern}' for target '{target_name}'[/yellow]")
                continue
        
        # Collect all matched paths from all patterns
        all_matched_paths = []
        for pattern in patterns_to_sync:
            matched_paths = resolve_patterns(
                source_dir, 
                [pattern], 
                target_config.get("exclude-patterns", []),
                git_tracked_files,
                include_files
            )
            all_matched_paths.extend(matched_paths)
        
        # Remove duplicates and sort
        all_matched_paths = sorted(set(all_matched_paths))
        
        if not all_matched_paths:
            console.print(f"[yellow]No paths matched the patterns for target '{target_name}'.[/yellow]")
            continue
        
        # Show statistics
        console.print(f"\n[bold green]Found {len(all_matched_paths)} matching paths[/bold green]")
        stats = get_file_statistics(all_matched_paths, source_dir, git_tracked_files)
        print_file_statistics(stats)
        
        # Show preview of paths (limited)
        if limit > 0:
            # Collect all actual files that will be synced
            all_files_to_sync = []
            for path in all_matched_paths:
                if path.is_file():

                    all_files_to_sync.append(path)
                elif path.is_dir():
                    # Get files from directory with git filtering
                    files = collect_files_recursive(path, source_dir, git_tracked_files)
                    all_files_to_sync.extend(files)
            
            console.print(f"\n[bold blue]📋 Preview (showing first {min(limit, len(all_files_to_sync))} files):[/bold blue]")
            console.print(f"[dim]Total files to sync: {len(all_files_to_sync):,}[/dim]")
            
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Type", style="green")
            table.add_column("Path", style="blue")
            table.add_column("Target", style="cyan")
            table.add_column("Size", style="yellow")
            
            for i, file_path in enumerate(all_files_to_sync[:limit]):
                relative_path = file_path.relative_to(source_dir)
                target_path = Path(target_config["path"]) / relative_path
                
                # Get file size
                try:
                    size = file_path.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                except Exception:
                    size_str = "Unknown"
                
                table.add_row("📄 FILE", str(relative_path), str(target_path), size_str)
            
            console.print(table)
            
            if len(all_files_to_sync) > limit:
                console.print(f"[dim]... and {len(all_files_to_sync) - limit:,} more files[/dim]")
        
        # Stop here if stats-only mode
        if stats_only:
            console.print(f"[yellow]Stats-only mode: skipping actual sync for target '{target_name}'[/yellow]")
            continue
        
        # Ask for confirmation unless it's a dry run
        if not dry:
            total_files = stats.get("[TOTAL FILES]", 0)
            if total_files > 1000:
                console.print(f"[yellow]⚠️  Warning: This will sync {total_files:,} files![/yellow]")
                if not Confirm.ask(f"Continue with syncing target '{target_name}'?"):
                    console.print(f"[yellow]Skipped target '{target_name}'[/yellow]")
                    continue
        
        # Collect all individual files to process (for detailed progress tracking)
        all_files_to_process = []
        for path in all_matched_paths:
            if path.is_file():
                all_files_to_process.append(path)
            elif path.is_dir():
                # Get files from directory with git filtering
                files = collect_files_recursive(path, source_dir, git_tracked_files)
                all_files_to_process.extend(files)
        
        # Sync selected files with progress bar
        console.print(f"\n[bold green]🚀 Starting sync of {len(all_files_to_process)} files...[/bold green]")
        
        processed_count = 0
        skipped_count = 0
        error_count = 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            
            task = progress.add_task(
                f"[cyan]Syncing {target_name}...",
                total=len(all_files_to_process)
            )
            
            for i, source_file in enumerate(all_files_to_process):
                relative_path = source_file.relative_to(source_dir)
                target_path = Path(target_config["path"]) / relative_path
                
                # Update progress description
                progress.update(task, description=f"[cyan]Processing {relative_path}...")
                
                try:
                    logger.info(f"Processing {relative_path} -> {target_path}")
                    
                    if reverse:
                        # In reverse mode, swap source and target
                        was_processed = process_path(target_path, source_file, source_dir, git_tracked_files, dry, replace_existing)
                    else:
                        was_processed = process_path(source_file, target_path, source_dir, git_tracked_files, dry, replace_existing)
                    
                    if was_processed:
                        processed_count += 1
                        logger.info(f"✓ Successfully processed {relative_path}")
                    else:
                        skipped_count += 1
                        logger.info(f"⊘ Skipped {relative_path}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"✗ Error processing {relative_path}: {e}")
                    console.print(f"[red]Error processing {relative_path}: {e}[/red]")
                
                # Update progress
                progress.update(task, advance=1)
        
        # Summary
        console.print(f"\n[bold green]✓ Sync completed for target '{target_name}'[/bold green]")
        console.print(f"[green]  • Processed: {processed_count}/{len(all_files_to_process)} files[/green]")
        console.print(f"[yellow]  • Skipped: {skipped_count} files[/yellow]")
        if error_count > 0:
            console.print(f"[red]  • Errors: {error_count} files[/red]")


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
        table.add_row("Exclude Patterns", ", ".join(target_config.get("exclude-patterns", [])) or "None")
        
        console.print(table)


def main() -> None:
    """Main entry point for the CLI."""
    import sys
    
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        app(["--help"])
    else:
        app()


if __name__ == "__main__":
    main()
