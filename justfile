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

ts-install:
    cd ts && bun install

ts-test:
    cd ts && bun run test

ts-typecheck:
    cd ts && bun run typecheck

ts-lint:
    cd ts && bun run lint

ts-format:
    cd ts && bun run format

ts-build:
    cd ts && bun run build
