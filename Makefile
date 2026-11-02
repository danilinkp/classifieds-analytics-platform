COMPOSE = docker compose
GEN = $(COMPOSE) exec airflow python -m marketplace_gen
DBT = $(COMPOSE) exec airflow dbt

.PHONY: up down reset logs backfill dbt-build dbt-test ch

.env:
	cp .env.example .env

up: .env
	$(COMPOSE) up -d --build

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
