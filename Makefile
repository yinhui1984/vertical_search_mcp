.PHONY: help test test-unit test-integration test-benchmark test-load test-cov test-cov-unit check-venv install install-dev format lint type-check clean all

# Default target
help:
	@echo "Available targets:"
	@echo "  make test              - Run all tests"
	@echo "  make test-unit         - Run unit tests only"
	@echo "  make test-integration  - Run integration tests only"
	@echo "  make test-benchmark    - Run benchmark tests only"
	@echo "  make test-load         - Run load tests only"
	@echo "  make test-cov          - Run tests with coverage report"
	@echo "  make install           - Install production dependencies"
	@echo "  make install-dev      - Install development dependencies"
	@echo "  make format            - Format code with black"
	@echo "  make lint              - Run flake8 linter"
	@echo "  make type-check        - Run mypy type checker"
	@echo "  make clean             - Clean temporary files"
	@echo "  make all               - Run format, lint, type-check, and test"

# Variables
PYTHON := python
VENV := .venv
PYTEST := $(VENV)/bin/pytest
BLACK := $(VENV)/bin/black
FLAKE8 := $(VENV)/bin/flake8
MYPY := $(VENV)/bin/mypy
PIP := $(VENV)/bin/pip

# Activate virtual environment
ACTIVATE := . $(VENV)/bin/activate

# Check if virtual environment exists
check-venv:
	@if [ ! -d "$(VENV)" ]; then \
		echo "Error: Virtual environment not found. Run 'make install-dev' first."; \
		exit 1; \
	fi

# Test targets
test: check-venv
	@echo "Running all tests..."
	$(ACTIVATE) && $(PYTEST) tests/ -v

test-unit: check-venv
	@echo "Running unit tests..."
	$(ACTIVATE) && $(PYTEST) tests/unit/ -v

test-integration: check-venv
	@echo "Running integration tests..."
	$(ACTIVATE) && $(PYTEST) tests/integration/ -v

test-benchmark: check-venv
	@echo "Running benchmark tests..."
	$(ACTIVATE) && $(PYTEST) tests/benchmark/ -v

test-load: check-venv
	@echo "Running load tests..."
	$(ACTIVATE) && $(PYTEST) tests/load/ -v

test-cov: check-venv
	@echo "Running tests with coverage..."
	$(ACTIVATE) && $(PYTEST) tests/ --cov=core --cov=platforms --cov-report=term-missing --cov-report=html -v
	@echo "Coverage report generated in htmlcov/index.html"

test-cov-unit: check-venv
	@echo "Running unit tests with coverage..."
	$(ACTIVATE) && $(PYTEST) tests/unit/ --cov=core --cov-report=term-missing -v

# Installation targets
install:
	@echo "Installing production dependencies..."
	$(ACTIVATE) && $(PIP) install -q -r requirements.txt

install-dev:
	@echo "Installing development dependencies..."
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON) -m venv $(VENV); \
	fi
	$(ACTIVATE) && $(PIP) install -q -r requirements.txt
	$(ACTIVATE) && $(PIP) install -q -r requirements-dev.txt
	@echo "Installing Playwright browsers..."
	$(ACTIVATE) && playwright install chromium

# Code quality targets
format: check-venv
	@echo "Formatting code with black..."
	$(ACTIVATE) && $(BLACK) core/ platforms/ tests/ --line-length=100

lint: check-venv
	@echo "Running flake8 linter..."
	$(ACTIVATE) && $(FLAKE8) core/ platforms/ tests/ --max-line-length=100 --exclude=__pycache__,.venv

type-check: check-venv
	@echo "Running mypy type checker..."
	$(ACTIVATE) && $(MYPY) core/ platforms/ --strict

# Combined quality check
all: format lint type-check test
	@echo "All checks passed!"

# Cleanup target
clean:
	@echo "Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".coverage" -exec rm -f {} + 2>/dev/null || true
	@echo "Cleanup complete!"

