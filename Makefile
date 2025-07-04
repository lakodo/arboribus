
.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help

.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running mypy"
	@uv run mypy
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: coverage-report
coverage-report: ## Display coverage percentage from coverage.xml
	@if [ -f coverage.xml ]; then \
		line_rate=$$(grep -o 'line-rate="[^"]*"' coverage.xml | head -1 | cut -d'"' -f2); \
		branch_rate=$$(grep -o 'branch-rate="[^"]*"' coverage.xml | head -1 | cut -d'"' -f2); \
		line_percent=$$(echo "$$line_rate * 100" | bc -l | cut -d'.' -f1); \
		branch_percent=$$(echo "$$branch_rate * 100" | bc -l | cut -d'.' -f1); \
		echo "📊 Coverage Report:"; \
		echo "   Line Coverage:   $$line_percent%"; \
		echo "   Branch Coverage: $$branch_percent%"; \
	else \
		echo "❌ coverage.xml not found. Run 'make test' first."; \
	fi

.PHONY: build
build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run mkdocs serve

