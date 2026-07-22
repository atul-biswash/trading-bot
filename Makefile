# Convenience targets. Run `make help` for the list.
.DEFAULT_GOAL := help
PYTHON ?= python

.PHONY: help venv install install-dev run paper backtest test cov lint format type check clean docker-build docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## Create a local virtual environment in .venv
	$(PYTHON) -m venv .venv

install: ## Install runtime deps + package (editable)
	pip install -r requirements.txt && pip install -e .

install-dev: ## Install dev deps + package (editable)
	pip install -r requirements-dev.txt && pip install -e .

run: ## Run the bot using config.yaml (default mode = testnet)
	$(PYTHON) -m trading_bot run

paper: ## Run in paper-trading mode
	$(PYTHON) -m trading_bot run --mode paper

backtest: ## Run the backtesting engine
	$(PYTHON) -m trading_bot backtest

test: ## Run the test suite
	pytest

cov: ## Run tests with coverage
	pytest --cov --cov-report=term-missing

lint: ## Lint with ruff
	ruff check src tests

format: ## Auto-format with ruff
	ruff format src tests && ruff check --fix src tests

type: ## Type-check with mypy
	mypy

check: lint type test ## Lint + type-check + test

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-build: ## Build the Docker image
	docker compose build

docker-up: ## Start the bot via docker compose
	docker compose up -d

docker-down: ## Stop the bot
	docker compose down
