.PHONY: help install dev test run-api run-mcp check init-db clean

PYTHON ?= python3
VENV ?= .venv

help:
	@echo "Job Copilot Development Commands:"
	@echo "  make install     Create venv and install dependencies"
	@echo "  make init-db     Initialize the local SQLite database"
	@echo "  make test        Run all tests with pytest"
	@echo "  make run-api     Start the FastAPI web server"
	@echo "  make run-mcp     Start the FastMCP stdio server"
	@echo "  make check       Run health & status check CLI"
	@echo "  make clean       Remove temporary files and caches"

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[dev]"

init-db:
	$(VENV)/bin/python -m job_copilot --init-db

test:
	$(VENV)/bin/pytest -v

run-api:
	$(VENV)/bin/uvicorn job_copilot.api.app:app --host 0.0.0.0 --port 8000 --reload

run-mcp:
	$(VENV)/bin/python -m job_copilot.mcp.server

check:
	$(VENV)/bin/python -m job_copilot

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov build dist *.egg-info
