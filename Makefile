.PHONY: ci-local sync lint test

# Mirror the GitHub Actions CI checks locally
ci-local: lint test

sync:
	uv sync --locked

lint: sync
	uv run ruff check .
	uv run ruff format --check .

test: sync
	uv run pytest -v
