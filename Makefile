.PHONY: up down logs migrate test heartbeat seed

up:            ## start db, redis, api, worker, metabase
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:       ## apply any new SQL migrations
	docker compose exec api python -c "from app.db import migrate; print(migrate())"

test:          ## run the test suite against the compose db
	docker compose exec -e APP_ENV=test api pytest -q /src/tests

heartbeat:     ## Component 0 done-when: a job goes pending -> executed through the queue
	python3 scripts/heartbeat.py

seed:          ## create company #1 (Simplicity) as a design partner
	python3 scripts/seed.py
