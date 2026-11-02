COMPOSE = docker compose
GEN = $(COMPOSE) exec airflow python -m marketplace_gen
DBT = $(COMPOSE) exec airflow dbt

.PHONY: init up down reset logs backfill dbt-build dbt-test ch dashboards screenshots

.env:
	cp .env.example .env

# Full setup from scratch: services, four months of history, dashboards.
init: up backfill dashboards

up: .env
	$(COMPOSE) up -d --build --wait clickhouse metadata-db airflow superset

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f airflow

backfill:
	$(GEN) backfill
	$(DBT) build --full-refresh

dbt-build:
	$(DBT) build

dbt-test:
	$(DBT) test

ch:
	$(COMPOSE) exec clickhouse clickhouse-client --user $$(grep CLICKHOUSE_USER .env | cut -d= -f2) --password $$(grep CLICKHOUSE_PASSWORD .env | cut -d= -f2)

dashboards:
	$(COMPOSE) run --rm --build superset-bootstrap

screenshots:
	docker run --rm --network marketplace-bi_default \
		-v $(CURDIR)/scripts:/scripts:ro -v $(CURDIR)/docs/screenshots:/docs/screenshots \
		--user $$(id -u):$$(id -g) -e HOME=/tmp --env-file .env mcr.microsoft.com/playwright/python:v1.64.1-noble \
		bash -c "pip install -q --user --break-system-packages playwright==1.64.1 && python /scripts/screenshots.py"
