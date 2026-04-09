default:
    @just --list

prd *ARGS:
    @uv run prd {{ARGS}}

test:
    uv run pytest

typecheck:
    uv run mypy src tests

format:
    uv run ruff format src tests

lint:
    uv run ruff check src tests

format-check:
    uv run ruff format --check src tests
