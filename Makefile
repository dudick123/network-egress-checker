.PHONY: lint format typecheck test test-unit test-int check build

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

format-check:
	uv run ruff format --check src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest --cov --cov-report=term-missing

test-unit:
	uv run pytest tests/unit/

test-int:
	uv run pytest tests/integration/

check: lint format-check typecheck test

build:
	docker build -t egress-checker:latest .
