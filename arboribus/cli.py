"""Arboribus CLI - Sync folders from monorepo to external targets."""

import fnmatch
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.prompt import Confirm
from rich.table import Table

from .core import (
    collect_files_recursive,
    get_config_path,
    get_default_source,
    get_file_statistics,
    get_git_tracked_files,
    load_config,
    process_path,
    resolve_patterns,
    save_config,
)

app = typer.Typer(help="🪵 Arboribus - Sync folders from monorepo to external targets")
console = Console()


def print_file_statistics(stats: dict[str, int]) -> None:
    """Print file statistics in a nice table."""
    if not stats:
        console.print("[yellow]No files found.[/yellow]")
        return

    # Separate summary from extensions
    total_files = stats.pop("[TOTAL FILES]", 0)
    total_dirs = stats.pop("[TOTAL DIRS]", 0)

    console.print("\n[bold blue]📊 File Statistics:[/bold blue]")
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


@app.command()
def init(
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
    target: Optional[str] = typer.Option(None, "--target", "-t", help="Target directory"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Target name"),
) -> None:
    """Initialize arboribus configuration."""
    source_dir = Path(source).resolve() if source else Path.cwd()

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

        config["targets"][name] = {"path": str(target_dir), "patterns": [], "exclude-patterns": []}

        console.print(f"[green]✓[/green] Added target '{name}' -> {target_dir}")

    # Save config
    save_config(source_dir, config)
    console.print(f"[green]✓[/green] Configuration saved to {get_config_path(source_dir)}")


@app.command()
def add_rule(
    pattern: str = typer.Option(..., "--pattern", "-p", help="Glob pattern to include"),
    target_name: str = typer.Option(..., "--target", "-t", help="Target name"),
    exclude_pattern: Optional[str] = typer.Option(None, "--exclude", "-e", help="Exclude pattern"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
) -> None:
    """Add a sync rule to a target."""
    source_dir = Path(source).resolve() if source else get_default_source()
    if source_dir is None:
        console.print(
            "[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory."
        )
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
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
) -> None:
    """Remove a sync rule from a target."""
    source_dir = Path(source).resolve() if source else get_default_source()
    if source_dir is None:
        console.print(
            "[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory."
        )
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
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
) -> None:
    """List all sync rules and their resolved paths."""
    source_dir = Path(source).resolve() if source else get_default_source()
    if source_dir is None:
        console.print(
            "[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory."
        )
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
            if git_tracked_files is not None:
                console.print(f"[dim]Found {len(git_tracked_files)} git-tracked files[/dim]")
            else:
                console.print(
                    f"[yellow]Warning: {source_dir} is not a git repository. Skipping git-based filtering.[/yellow]"
                )

            matched_dirs = resolve_patterns(
                source_dir, [pattern], target_config.get("exclude-patterns", []), git_tracked_files
            )

            exclude_patterns_str = ", ".join(target_config.get("exclude-patterns", [])) or "None"
            if matched_dirs:
                matched_str = "\n".join([str(d.relative_to(source_dir)) for d in matched_dirs])
                target_paths = "\n".join([
                    str(Path(target_config["path"]) / d.relative_to(source_dir)) for d in matched_dirs
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
    limit: int = typer.Option(-1, "--limit", "-l", help="Limit number of files to display (default: not applied)"),
    stats_only: bool = typer.Option(False, "--stats-only", help="Only show statistics, don't sync"),
    include_files: bool = typer.Option(False, "--include-files", help="Include individual files in pattern matching"),
    replace_existing: bool = typer.Option(
        False, "--replace-existing", help="Replace existing files/directories in target"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
) -> None:
    """Apply sync rules with file statistics and preview."""
    source_dir = Path(source).resolve() if source else get_default_source()
    if source_dir is None:
        console.print(
            "[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory."
        )
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
    if git_tracked_files is not None:
        console.print(f"[dim]Found {len(git_tracked_files)} git-tracked files[/dim]")
    else:
        console.print(f"[yellow]Warning: {source_dir} is not a git repository. Skipping git-based filtering.[/yellow]")

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
                console.print(
                    f"[yellow]No patterns matched filter '{filter_pattern}' for target '{target_name}'[/yellow]"
                )
                continue

        # Collect all matched paths from all patterns
        all_matched_paths = []
        for pattern in patterns_to_sync:
            matched_paths = resolve_patterns(
                source_dir, [pattern], target_config.get("exclude-patterns", []), git_tracked_files, include_files
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

            console.print(
                f"\n[bold blue]📋 Preview (showing first {min(limit, len(all_files_to_sync))} files):[/bold blue]"
            )
            console.print(f"[dim]Total files to sync: {len(all_files_to_sync):,}[/dim]")

            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Type", style="green")
            table.add_column("Path", style="blue")
            table.add_column("Target", style="cyan")
            table.add_column("Size", style="yellow")

            for file_path in all_files_to_sync[:limit]:
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

        # Apply limit to actual processing, not just preview
        if limit > 0 and len(all_files_to_process) > limit:
            console.print(
                f"[yellow]⚠️  Limiting processing to first {limit} files (out of {len(all_files_to_process):,} total)[/yellow]"
            )
            all_files_to_process = all_files_to_process[:limit]

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
            task = progress.add_task(f"[cyan]Syncing {target_name}...", total=len(all_files_to_process))

            for source_file in all_files_to_process:
                relative_path = source_file.relative_to(source_dir)
                target_path = Path(target_config["path"]) / relative_path

                # Update progress description
                progress.update(task, description=f"[cyan]Processing {relative_path}...")

                try:
                    if reverse:
                        # In reverse mode, swap source and target
                        was_processed, message = process_path(
                            target_path, source_file, source_dir, git_tracked_files, dry, replace_existing
                        )
                    else:
                        was_processed, message = process_path(
                            source_file, target_path, source_dir, git_tracked_files, dry, replace_existing
                        )

                    if was_processed:
                        processed_count += 1
                        if dry:
                            console.print(f"[yellow]{message}[/yellow]")
                        else:
                            console.print(f"[green]{message}[/green]")
                    else:
                        skipped_count += 1
                        console.print(f"[dim]{message}[/dim]")

                except Exception as e:
                    error_count += 1
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
    output_format: str = typer.Option("table", "--format", "-f", help="Output format: table or json"),
    source: Optional[str] = typer.Option(
        None, "--source", "-s", help="Source root directory (default: current directory)"
    ),
) -> None:
    """Print the current configuration."""
    source_dir = Path(source).resolve() if source else get_default_source()
    if source_dir is None:
        console.print(
            "[red]Error:[/red] No arboribus.toml found in current directory. Use --source or run from a configured directory."
        )
        raise typer.Exit(1)

    if not source_dir.exists():
        console.print(f"[red]Error:[/red] Source directory {source_dir} does not exist")
        raise typer.Exit(1)

    config = load_config(source_dir)

    if output_format == "json":
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
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        app(["--help"])
    else:
        app()


if __name__ == "__main__":
    main()
