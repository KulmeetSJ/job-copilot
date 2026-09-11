.PHONY: help install dev test test-security run-api run-copilot run-mcp check init-db docker-build docker-run clean

PYTHON ?= python3
VENV ?= .venv

help:
	@echo "Job Copilot Development Commands:"
	@echo "  make install         Create venv and install dependencies"
	@echo "  make init-db         Initialize the local SQLite database"
	@echo "  make test            Run all tests with pytest"
	@echo "  make test-security   Run repository secret scanner"
	@echo "  make run-api         Start the FastAPI web server"
	@echo "  make run-copilot     Run Job Copilot CLI dashboard"
	@echo "  make run-mcp         Start the FastMCP stdio server"
	@echo "  make docker-build    Build the production Docker container"
	@echo "  make docker-run      Run the application container locally"
	@echo "  make check           Run health & status check CLI"
	@echo "  make clean           Remove temporary files and caches"

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[dev]"
	$(VENV)/bin/playwright install chromium

init-db:
	$(VENV)/bin/python -m job_copilot --init-db

test:
	$(VENV)/bin/pytest -v

test-security:
	$(VENV)/bin/python -c "from job_copilot.utils.security import scan_repository_for_secrets; f = scan_repository_for_secrets(); assert not f, f'Secrets found: {f}'; print('✅ Secret scan passed. No secrets detected.')"

run-api:
	$(VENV)/bin/uvicorn job_copilot.api.app:app --host 0.0.0.0 --port 8000 --reload

run-copilot:
	$(VENV)/bin/python -m job_copilot copilot

run-mcp:
	$(VENV)/bin/python -m job_copilot.mcp.server

docker-build:
	docker build -t job-copilot:latest .

docker-run:
	docker run -p 8000:8000 --rm --name job-copilot-app job-copilot:latest

check:
	$(VENV)/bin/python -m job_copilot

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov build dist *.egg-info
