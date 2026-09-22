.PHONY: \
infra-up \
up \
down \
ps \
logs \
api-build \
migrate \
db-shell \
redis-cli \
restart-api

infra-up:
	docker compose up -d postgres redis minio minio-init odoo-db odoo n8n-db n8n

api-build:
	docker compose build api

migrate:
	docker compose run --rm api alembic upgrade head

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100

restart-api:
	docker compose restart api

db-shell:
	docker compose exec postgres psql -U ordernexa -d ordernexa

redis-cli:
	docker compose exec redis sh