"""Arboribus core functionality - Configuration, file operations, and sync logic."""

import glob
import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import toml


def get_config_path(source_dir: Path) -> Path:
    """Get the path to the arboribus.toml config file."""
    return source_dir / "arboribus.toml"


def load_config(source_dir: Path) -> dict:
    """Load the arboribus.toml config file."""
    config_path = get_config_path(source_dir)
    if not config_path.exists():
        return {"targets": {}}

    with open(config_path) as f:
        return toml.load(f)


def save_config(source_dir: Path, config: dict) -> None:
    """Save the arboribus.toml config file."""
    config_path = get_config_path(source_dir)
    with open(config_path, "w") as f:
        toml.dump(config, f)


def get_git_tracked_files(source_dir: Path) -> Optional[set]:
    """Get all git-tracked files from the repository."""
    try:
        # Check if we're in a git repository
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=source_dir, capture_output=True, text=True
        )

        if result.returncode != 0:
            return None

        # Get all tracked files
        result = subprocess.run(["git", "ls-files"], cwd=source_dir, capture_output=True, text=True)

        if result.returncode != 0:
            return None

        # Return set of tracked file paths (relative to source_dir)
        tracked_files = set()
        for line in result.stdout.splitlines():
            if line.strip():
                tracked_files.add(line.strip())

        return tracked_files

    except Exception:
        return None


def resolve_patterns(
    source_dir: Path,
    patterns: list[str],
    exclude_patterns: Optional[list[str]] = None,
    git_tracked_files: Optional[set] = None,
    include_files: bool = False,
) -> list[Path]:
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
        if "*" in pattern:
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


def sync_directory(
    source: Path, target: Path, reverse: bool = False, dry: bool = False, git_tracked_files: Optional[set] = None
) -> None:
    """Sync a single directory."""
    if reverse:
        source, target = target, source

    if dry:
        return

    if target.exists():
        shutil.rmtree(target)

    def ignore_func(directory: str, files: list[str]) -> list[str]:
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
        except Exception:
            pass

        return ignored

    try:
        shutil.copytree(source, target, ignore=ignore_func)
    except Exception:
        raise


def collect_files_recursive(directory: Path, source_dir: Path, git_tracked_files: Optional[set] = None) -> list[Path]:
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
    except (PermissionError, OSError):
        pass

    return files


def get_file_statistics(paths: list[Path], source_dir: Path, git_tracked_files: Optional[set] = None) -> dict[str, int]:
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


def get_default_source() -> Optional[Path]:
    """Get the default source directory by looking for arboribus.toml."""
    current = Path.cwd()
    while current != current.parent:
        if (current / "arboribus.toml").exists():
            return current
        current = current.parent
    return None


def get_file_checksum(file_path: Path) -> Optional[str]:
    """Get MD5 checksum of a file."""
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None


def is_same_file_content(source_path: Path, target_path: Path) -> bool:
    """Check if two files have the same content using checksums."""
    if not source_path.exists() or not target_path.exists():
        return False

    source_checksum = get_file_checksum(source_path)
    target_checksum = get_file_checksum(target_path)

    return source_checksum is not None and target_checksum is not None and source_checksum == target_checksum


def process_file_sync(
    source_path: Path,
    target_path: Path,
    source_dir: Path,
    git_tracked_files: Optional[set],
    dry: bool = False,
    replace_existing: bool = False,
) -> tuple[bool, str]:
    """
    Process a single file for syncing.

    Returns:
        (was_processed: bool, message: str)
    """
    relative_path = source_path.relative_to(source_dir)
    relative_target = (
        target_path.relative_to(target_path.parent.parent) if target_path.parent.parent.exists() else target_path.name
    )

    # Check if file is git-tracked
    if git_tracked_files is not None:
        if str(relative_path) not in git_tracked_files:
            return False, f"{relative_path} -> {relative_target} (filtered out - not git-tracked)"

    # Check if target already exists
    if target_path.exists():
        if not replace_existing:
            # Check if they have the same checksum
            if is_same_file_content(source_path, target_path):
                return False, f"{relative_path} -> {relative_target} (same - skipped)"

            return False, f"{relative_path} -> {relative_target} (exists - skipped, use --replace-existing)"
        else:
            # replace_existing is True
            if dry:
                return True, f"{relative_path} -> {relative_target} (would replace existing)"

    # Process the file
    if dry:
        return True, f"{relative_path} -> {relative_target} (would copy)"
    else:
        # Ensure target directory exists
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, f"{relative_path} -> {relative_target} (mkdir error: {e})"

        # Copy the file
        try:
            shutil.copy2(source_path, target_path)
            if target_path.exists() and replace_existing:
                return True, f"{relative_path} -> {relative_target} (replaced)"
            else:
                return True, f"{relative_path} -> {relative_target} (copied)"
        except Exception as e:
            return False, f"{relative_path} -> {relative_target} (error: {e})"


def process_directory_sync(
    source_path: Path,
    target_path: Path,
    source_dir: Path,
    git_tracked_files: Optional[set],
    dry: bool = False,
    replace_existing: bool = False,
) -> tuple[bool, str]:
    """
    Process a single directory for syncing.

    Returns:
        (was_processed: bool, message: str)
    """
    relative_path = source_path.relative_to(source_dir)
    relative_target = (
        target_path.relative_to(target_path.parent.parent) if target_path.parent.parent.exists() else target_path.name
    )

    # Check if directory contains any git-tracked files
    if git_tracked_files is not None:
        has_tracked_files = any(
            tracked_file.startswith(str(relative_path) + "/") or tracked_file == str(relative_path)
            for tracked_file in git_tracked_files
        )
        if not has_tracked_files:
            return False, f"{relative_path} -> {relative_target} (filtered out - no git-tracked files)"

    if dry:
        return True, f"{relative_path} -> {relative_target} (would sync directory)"
    else:
        # Remove target if it exists and we're replacing
        if target_path.exists() and replace_existing:
            try:
                shutil.rmtree(target_path)
            except Exception as e:
                return False, f"{relative_path} -> {relative_target} (rmtree error: {e})"

        def ignore_func(directory: str, files: list[str]) -> list[str]:
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
            return True, f"{relative_path} -> {relative_target} (synced directory)"
        except Exception as e:
            return False, f"{relative_path} -> {relative_target} (error: {e})"


def process_path(
    source_path: Path,
    target_path: Path,
    source_dir: Path,
    git_tracked_files: Optional[set],
    dry: bool = False,
    replace_existing: bool = False,
) -> tuple[bool, str]:
    """
    Process a single path (file or directory) for syncing.

    Returns:
        (was_processed: bool, message: str)
    """
    if source_path.is_file():
        return process_file_sync(source_path, target_path, source_dir, git_tracked_files, dry, replace_existing)
    elif source_path.is_dir():
        return process_directory_sync(source_path, target_path, source_dir, git_tracked_files, dry, replace_existing)
    else:
        relative_path = source_path.relative_to(source_dir)
        return False, f"{relative_path} (not a file or directory)"
