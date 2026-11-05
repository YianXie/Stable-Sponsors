.PHONY: ci-local sync lint test api web

# Mirror the GitHub Actions CI checks locally
ci-local: lint test

sync:
	uv sync --locked

lint: sync
	uv run ruff check .
	uv run ruff format --check .

test: sync
	uv run pytest -v

api:
	uv run uvicorn stable_sponsors.api:app --host 127.0.0.1 --port 8000

web:
	cd frontend && npm run dev
