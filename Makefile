.PHONY: install api web check

install:
	uv sync
	cd web && npm install

api:
	uv run vectornote serve --reload

web:
	cd web && npm run dev

check:
	uv run flake8
	uv run mypy
	uv run pytest
	cd web && npm run build
