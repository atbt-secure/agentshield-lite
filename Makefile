.PHONY: dev docker-up docker-down test install seed seed-large lint \
        db-upgrade db-downgrade db-migrate db-history

# ── Development ───────────────────────────────────────────────────────────────

dev:
	cd backend && uvicorn main:app --reload --port 8000

install:
	cd backend && pip install -r requirements.txt
	cd sdk/python && pip install -e .

# ── Testing ───────────────────────────────────────────────────────────────────

test:
	cd backend && pytest tests/ -v

lint:
	cd backend && python -m ruff check . --ignore E501,F401

# ── Demo data ─────────────────────────────────────────────────────────────────

seed:
	python3 scripts/seed_demo_data.py --count 80

seed-large:
	python3 scripts/seed_demo_data.py --count 300

# ── Database migrations (Alembic) ─────────────────────────────────────────────

# Apply all pending migrations
db-upgrade:
	cd backend && alembic upgrade head

# Roll back one migration
db-downgrade:
	cd backend && alembic downgrade -1

# Auto-generate a new migration from model changes
# Usage: make db-migrate MSG="add new column"
db-migrate:
	cd backend && alembic revision --autogenerate -m "$(MSG)"

# Show migration history
db-history:
	cd backend && alembic history --verbose

# Show current DB revision
db-current:
	cd backend && alembic current

# ── Docker ────────────────────────────────────────────────────────────────────

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f backend
