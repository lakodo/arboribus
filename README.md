# arboribus

[![Release](https://img.shields.io/github/v/release/lakodo/arboribus)](https://github.com/lakodo/arboribus/releases)
[![codecov](https://codecov.io/gh/lakodo/arboribus/branch/main/graph/badge.svg)](https://codecov.io/gh/lakodo/arboribus)
[![Commit activity](https://img.shields.io/github/commit-activity/m/lakodo/arboribus)](https://github.com/lakodo/arboribus/graphs/commit-activity)
[![License](https://img.shields.io/github/license/lakodo/arboribus)](https://github.com/lakodo/arboribus/blob/main/LICENSE)

Sync folders to split/merge/partially share monorepos

- **Github repository**: <https://github.com/lakodo/arboribus/>
- **Documentation** <https://lakodo.github.io/arboribus/>

## Usage

Arboribus helps you sync specific folders and files from a monorepo to external target repositories. This is useful for sharing common libraries, tools, or configurations between repositories while keeping them synchronized.

### Basic Workflow

1. **Initialize** a configuration in your monorepo
2. **Add rules** to specify which files/folders to sync
3. **Apply** the sync to copy files to target repositories

### Quick Start Example

```bash
# Initialize arboribus in your monorepo
arboribus init --target /path/to/target-repo --name shared-libs

# Add sync rules for specific folders
arboribus add-rule --pattern "libs/auth" --target shared-libs
arboribus add-rule --pattern "libs/admin" --target shared-libs

# Preview what will be synced
arboribus apply --dry

# Apply the sync
arboribus apply
```

## Commands

### `arboribus init`

Initialize arboribus configuration in your monorepo.

```bash
# Initialize with a target repository
arboribus init --target /path/to/target-repo --name my-target

# Initialize without a target (add targets later)
arboribus init --source /path/to/monorepo
```

**Options:**
- `--source, -s`: Source root directory (default: current directory)
- `--target, -t`: Target directory path
- `--name, -n`: Name for the target

### `arboribus add-rule`

Add sync rules to specify which files/folders to include.

```bash
# Add a folder to sync
arboribus add-rule --pattern "libs/auth" --target shared-libs

# Add files with glob patterns
arboribus add-rule --pattern "src/**/*.py" --target shared-libs

# Add with exclude patterns
arboribus add-rule --pattern "docs/*" --target shared-libs --exclude "docs/internal/*"
```

**Options:**
- `--pattern, -p`: Glob pattern to include (required)
- `--target, -t`: Target name (required)
- `--exclude, -e`: Exclude pattern
- `--source, -s`: Source root directory

### `arboribus remove-rule`

Remove sync rules from a target.

```bash
arboribus remove-rule --pattern "libs/auth" --target shared-libs
```

**Options:**
- `--pattern, -p`: Pattern to remove (required)
- `--target, -t`: Target name (required)
- `--source, -s`: Source root directory

### `arboribus list-rules`

List all configured sync rules and their matched paths.

```bash
arboribus list-rules
```

**Options:**
- `--source, -s`: Source root directory

### `arboribus apply`

Apply the sync rules to copy files to target repositories.

```bash
# Dry run (preview without making changes)
arboribus apply --dry

# Apply all rules
arboribus apply

# Apply with filters
arboribus apply --filter "libs/*"

# Reverse sync (from target back to source)
arboribus apply --reverse
```

**Options:**
- `--dry, -d`: Dry run - show what would be done
- `--reverse, -r`: Sync from target to source
- `--filter, -f`: Filter to specific pattern
- `--stats-only`: Only show statistics, don't sync
- `--replace-existing`: Replace existing files/directories in target
- `--source, -s`: Source root directory

### `arboribus print-config`

Print the current configuration.

```bash
# Print as table
arboribus print-config

# Print as JSON
arboribus print-config --format json
```

**Options:**
- `--format, -f`: Output format (table or json)
- `--source, -s`: Source root directory

## Examples

### Sharing Common Libraries

```bash
# Set up sync for shared libraries
arboribus init --target ../shared-libs-repo --name shared-libs

# Add authentication library
arboribus add-rule --pattern "libs/auth" --target shared-libs

# Add utility functions
arboribus add-rule --pattern "libs/utils" --target shared-libs

# Exclude test files
arboribus add-rule --pattern "libs/core" --target shared-libs --exclude "libs/core/tests/*"

# Apply the sync
arboribus apply
```

### Syncing Documentation

```bash
# Set up documentation sync
arboribus init --target ../docs-repo --name docs

# Add all markdown files
arboribus add-rule --pattern "docs/**/*.md" --target docs

# Add images but exclude large files
arboribus add-rule --pattern "docs/**/*.png" --target docs
arboribus add-rule --pattern "docs/**/*.jpg" --target docs --exclude "docs/archive/*"

# Preview and apply
arboribus apply --dry
arboribus apply
```

### Multiple Targets

```bash
# Initialize multiple targets
arboribus init --target ../frontend-shared --name frontend
arboribus init --target ../backend-shared --name backend

# Add frontend-specific rules
arboribus add-rule --pattern "packages/ui-components" --target frontend
arboribus add-rule --pattern "packages/utils" --target frontend

# Add backend-specific rules
arboribus add-rule --pattern "libs/auth" --target backend
arboribus add-rule --pattern "libs/database" --target backend

# Apply to specific targets
arboribus apply --filter "packages/*"  # Only frontend patterns
arboribus apply
```

## Installation

### Using pip

```bash
pip install arboribus
```

### Using uv

```bash
uv add arboribus
```

### From source

```bash
git clone https://github.com/lakodo/arboribus.git
cd arboribus
uv sync
uv run arboribus --help
```

## Development

For development setup and contributing guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
