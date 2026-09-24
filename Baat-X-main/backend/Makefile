.PHONY: install dev worker test lint fmt migrate revision

install:
	pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --port 8000

worker:
	arq app.workers.main.WorkerSettings

test:
	ENVIRONMENT=test pytest -q --cov=app --cov-report=term-missing

lint:
	ruff check app tests
	mypy app

fmt:
	ruff format app tests
	ruff check --fix app tests

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"
