.PHONY: dev docker-up docker-down test install seed

dev:
	cd backend && uvicorn main:app --reload --port 8000

install:
	cd backend && pip install -r requirements.txt
	cd sdk/python && pip install -e .

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

test:
	cd backend && pytest tests/ -v

seed:
	python scripts/seed_demo_data.py --count 80

seed-large:
	python scripts/seed_demo_data.py --count 300

lint:
	cd backend && python -m ruff check . && python -m mypy .
