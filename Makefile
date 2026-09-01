.PHONY: api web test up

api:
	cd services/api && uvicorn app.main:app --reload

web:
	cd apps/web && npm run dev

test:
	cd services/api && ruff check . && pytest
	cd apps/web && npm run typecheck && npm run build

up:
	docker compose up --build
