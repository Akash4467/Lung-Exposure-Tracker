API := apps/api
UV  := uv --directory $(API)
API_PORT ?= 18000

.PHONY: help infra-check check-all up down api worker seed smoke prod-local prod-local-down migrate test test-int lint fmt typecheck check image

help:            ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

up:              ## Start Postgres, Valkey and ElasticMQ
	docker compose up -d --build postgres valkey elasticmq

down:            ## Stop the local stack (data volume is kept)
	docker compose down

api:             ## Run the API with reload against the local stack
	$(UV) run uvicorn lung.main:app --reload --port $(API_PORT)

worker:          ## Run the worker locally (ticks itself every 60 min)
	LOCAL_TICK_MINUTES=60 $(UV) run python -m lung.worker

smoke:           ## Check real providers with the keys in .env (EMAIL_TO=you@x.in sends a test email)
	$(UV) run python -m lung.devtools.smoke $(if $(EMAIL_TO),--email-to $(EMAIL_TO))

seed:            ## Create the demo user and queue its first jobs
	$(UV) run python -m lung.devtools.seed

PROD_LOCAL := cd deploy && IMAGE_REPO=local IMAGE_TAG=dev SITE_ADDRESS=localhost 	ACME_EMAIL=ops@example.com POSTGRES_PASSWORD=local-prod-pw ENV_FILE=../apps/api/.env 	docker compose -p lung-prodlocal -f compose.prod.yml -f compose.local-prod.yml

prod-local:      ## Run the PRODUCTION compose stack locally on https://localhost:8443
	$(PROD_LOCAL) up -d --build --wait --wait-timeout 300

prod-local-down: ## Stop it and delete its data
	$(PROD_LOCAL) down -v

TOFU := MSYS_NO_PATHCONV=1 docker run --rm -v tfcache:/cache -e TF_PLUGIN_CACHE_DIR=/cache \
	-v "$(CURDIR)/infra:/infra" --entrypoint sh ghcr.io/opentofu/opentofu:1.10 -c

infra-check:     ## tofu fmt/validate/test, shellcheck, Caddyfile, actionlint (all via Docker)
	$(TOFU) 'cd /infra && tofu fmt -check -recursive'
	$(TOFU) 'for d in bootstrap envs/demo envs/scale; do (cd /infra/$$d && tofu init -backend=false -input=false >/dev/null && tofu validate) || exit 1; done'
	$(TOFU) 'for m in network compute storage iam; do (cd /infra/modules/$$m && tofu init -input=false >/dev/null && tofu test) || exit 1; done'
	MSYS_NO_PATHCONV=1 docker run --rm -v "$(CURDIR)/deploy:/mnt" -w /mnt koalaman/shellcheck:stable -x $(patsubst deploy/%,%,$(wildcard deploy/scripts/*.sh))
	MSYS_NO_PATHCONV=1 docker run --rm -e SITE_ADDRESS=example.duckdns.org -e ACME_EMAIL=ops@example.com \
		-v "$(CURDIR)/deploy/caddy:/etc/caddy:ro" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
	MSYS_NO_PATHCONV=1 docker run --rm -v "$(CURDIR):/repo" -w /repo rhysd/actionlint:latest -no-color

migrate:         ## Apply database migrations
	$(UV) run alembic upgrade head

test:            ## Unit tests (no containers needed)
	$(UV) run pytest

test-int:        ## Integration tests (needs `make up`)
	$(UV) run pytest -m integration

lint:            ## Ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt:             ## Auto-fix lint and format
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck:       ## mypy (strict)
	$(UV) run mypy

check: lint typecheck test  ## Lint, types, unit tests (no containers)

check-all: check test-int   ## Everything, including integration tests (needs `make up`)

image:           ## Build the API/worker image
	docker build -t lung-api:dev $(API)
