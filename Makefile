SHELL := /bin/bash

export COMPOSE_PROJECT_NAME := sound_schedule
COMPOSE := docker compose

ENV_FILE := .env

MANAGE := $(COMPOSE) run --rm web python manage.py

.DEFAULT_GOAL := help

.PHONY: help up down logs build migrate superuser shell lint fmt test seed gen-oct \
        trigger-monthly trigger-daily notify-month gen mm mm-check migrate showmigrations

help:
	@echo "Targets:"
	@echo "  make up                 - start all services (dev)"
	@echo "  make down               - stop services"
	@echo "  make build              - build images"
	@echo "  make logs               - tail logs"
	@echo "  make migrate            - run migrations"
	@echo "  make superuser          - create Django superuser"
	@echo "  make shell              - Django shell"
	@echo "  make lint               - ruff lint"
	@echo "  make fmt                - black format"
	@echo "  make test               - pytest"
	@echo "  make seed               - load demo data"
	@echo "  make gen-oct            - generate October schedule (example)"
	@echo "  make trigger-monthly    - trigger monthly draft task"
	@echo "  make trigger-daily      - trigger daily reminder task"
	@echo "  make notify-month year=YYYY month=MM - notify about a specific month"
	@echo "  make gen year=YYYY month=MM          - generate schedule for a specific month (commit)"

up:
	$(COMPOSE) --profile dev up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f --tail=200

migrate:
	$(MANAGE) migrate

mm:
	$(MANAGE) makemigrations

mm-app:
	@test -n "$(app)" || (echo "Usage: make mm-app app=scheduling" && exit 1)
	$(MANAGE) makemigrations $(app)

mm-check:
	$(MANAGE) makemigrations --check --dry-run

showmigrations:
	$(MANAGE) showmigrations

superuser:
	$(MANAGE) createsuperuser

shell:
	$(MANAGE) shell

lint:
	$(COMPOSE) run --rm web ruff check .

fmt:
	$(COMPOSE) run --rm web black .

test:
	$(COMPOSE) run --rm web pytest

seed:
	$(MANAGE) seed_demo

gen-oct:
	$(MANAGE) generate_schedule --year=2025 --month=10 --commit

# ==== Celery test triggers ====

trigger-monthly:
	$(MANAGE) trigger_task monthly_draft

trigger-daily:
	$(MANAGE) trigger_task daily_reminder

notify-month:
	@test -n "$(year)" -a -n "$(month)" || (echo "Usage: make notify-month year=2025 month=10" && exit 1)
	$(MANAGE) trigger_task notify_month --year=$(year) --month=$(month)

gen:
	@test -n "$(year)" -a -n "$(month)" || (echo "Usage: make gen year=2025 month=10" && exit 1)
	$(MANAGE) generate_schedule --year=$(year) --month=$(month) --commit
