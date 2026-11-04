.PHONY: install api web check bench docker-up docker-down docker-logs

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
	cd web && npm run build && npm run check:demo

bench:
	scripts/bench_chunks.sh

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
