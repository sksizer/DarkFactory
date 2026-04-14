default:
    @just --list

prd *ARGS:
    @uv run prd {{ARGS}}

test:
    uv run pytest

typecheck:
    uv run mypy python tests

format:
    uv run ruff format python tests

lint:
    uv run ruff check python tests

format-check:
    uv run ruff format --check python tests
