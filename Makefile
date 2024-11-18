
MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_DIR := $(patsubst %/,%,$(dir $(MAKEFILE_PATH)))

.DEFAULT_GOAL = help

# ---- Docker delegation -----------------------------------------------------
# Hors devcontainer (DEVCONTAINER != true), on réexécute la cible demandée
# dans la stack docker Python 3.11 définie dans .docker/. À l'intérieur du
# conteneur, DEVCONTAINER vaut "true" (cf. .docker/Dockerfile) donc cette
# branche est ignorée et le Makefile s'exécute normalement.
ifneq ($(DEVCONTAINER),true)

DOCKER_COMPOSE ?= docker compose -f .docker/docker-compose.yml
DOCKER_SERVICE ?= dev
DOCKER_ENV     := UID=$$(id -u) GID=$$(id -g)
DOCKER_RUN     := $(DOCKER_ENV) $(DOCKER_COMPOSE) run --rm $(DOCKER_SERVICE)

# Cibles déléguées à la stack docker (exécution dans le conteneur dev)
DELEGATED_TARGETS := all setup pkgs tox syntax black isort mypy flake8 pylint \
                     cover doc test test-unit test-cli

.PHONY: $(DELEGATED_TARGETS) test-functional \
        docker-build docker-shell docker-clean \
        stack-up stack-down stack-reset stack-logs stack-ps

## -- Docker (host) -----------------------------------------------------------

$(DELEGATED_TARGETS):
	@$(DOCKER_RUN) make $@ $(MAKEOVERRIDES)

docker-build: ## Build the Python 3.11 docker dev image
	$(DOCKER_ENV) $(DOCKER_COMPOSE) build

docker-shell: ## Open an interactive shell in the docker dev container
	$(DOCKER_ENV) $(DOCKER_COMPOSE) run --rm $(DOCKER_SERVICE) bash

docker-clean: ## Remove the docker dev image and associated resources
	-$(DOCKER_COMPOSE) down --rmi local --volumes --remove-orphans

## -- Functional stack (mssql/oracle/postgres) --------------------------------

# `functional` profile = mssql + postgres (fast). Oracle lives in its own
# `oracle` profile because the image is ~10 GB and takes 3-5 min to boot.
# `stack-up` keeps the historical "everything" behaviour for local dev.

stack-up: ## Start the full functional DB stack (mssql, postgres, oracle) and wait until healthy
	$(DOCKER_ENV) $(DOCKER_COMPOSE) --profile functional --profile oracle up -d --wait

stack-up-light: ## Start only the lightweight functional DB stack (mssql, postgres) — no Oracle
	$(DOCKER_ENV) $(DOCKER_COMPOSE) --profile functional up -d --wait

stack-up-oracle: ## Start only the Oracle container (heavy, ~3-5 min boot) — no mssql/postgres
	$(DOCKER_ENV) $(DOCKER_COMPOSE) --profile oracle up -d --wait

stack-down: ## Stop the functional DB stack (keep volumes)
	$(DOCKER_COMPOSE) --profile functional --profile oracle down

stack-reset: ## Stop the functional DB stack and wipe its volumes (re-runs init scripts)
	$(DOCKER_COMPOSE) --profile functional --profile oracle down -v

stack-logs: ## Follow logs of the functional DB stack
	$(DOCKER_COMPOSE) --profile functional --profile oracle logs -f

stack-ps: ## Show status of the functional DB stack
	$(DOCKER_COMPOSE) --profile functional --profile oracle ps

test-functional: stack-up ## Run functional tests against the running docker stack
	@$(DOCKER_RUN) make test-functional $(MAKEOVERRIDES)

test-functional-light: stack-up-light ## Run functional tests excluding Oracle (mssql + postgres only)
	@$(DOCKER_RUN) make test-functional-light $(MAKEOVERRIDES)

test-oracle: stack-up-oracle ## Run Oracle functional tests only (on-demand, heavy)
	@$(DOCKER_RUN) make test-oracle $(MAKEOVERRIDES)

include .make/help.mk

else
# ---- Devcontainer / in-docker path : exécution locale -----------------------

PIPUSER ?= 1

ifeq ($(OS),Windows_NT)
	PYTHON ?= python.exe
	VENV_BIN_DIR = Scripts
	EXE_EXT = .exe

	VENV_INIT = activate.bat
	VENV_CMD = call
	PATH_SEP = /
else
	PYTHON ?= python3
	VENV_BIN_DIR = bin
	EXE_EXT =

	VENV_INIT = activate
	VENV_CMD = .
	PATH_SEP = /
endif

VENV_BIN_DIR := .venv$(PATH_SEP)$(VENV_BIN_DIR)
VENV_ACTIVATE = $(VENV_CMD) $(VENV_BIN_DIR)$(PATH_SEP)$(VENV_INIT)
VENV_ACTIVATE_CMD := $(VENV_ACTIVATE) &&

TOX_EXE = $(VENV_BIN_DIR)$(PATH_SEP)tox$(EXE_EXT)
PRECOMMIT_EXE = $(VENV_BIN_DIR)$(PATH_SEP)pre-commit$(EXE_EXT)

ifeq ($(PIPUSER),1)
TOX_CMD = $(VENV_ACTIVATE_CMD) $(PYTHON) -m tox
else
TOX_CMD = tox
endif
ifeq ($(VERBOSE),1)
TOX_ARG := $(TOX_ARG) -v
endif

MNOPD = --no-print-directory

## -- Global makefile rules ---------------------------------------------------
all: | $(VENV_BIN_DIR) ## Setup local environment with pre-commit and tox
	$(NOISE)env PATH="$(PROJECT_DIR)/.venv/$(VENV_BIN_DIR):$(PATH)" hash tox$(EXE_EXT) pre-commit$(EXE_EXT) > /dev/null 2>&1  || $(MAKE) $(MFLAGS) $(MNOPD) setup

pkgs: ## Generate pythong packages
	$(NOISE)$(PYTHON) setup.py sdist
	$(NOISE)$(PYTHON) setup.py bdist_wheel --universal

include .make/help.mk

## -- Setup -------------------------------------------------------------------

setup: $(TOX_EXE) $(PRECOMMIT_EXE) ## Setup local environment with pre-commit and tox
	@$(call infomsg,"venv can be activate using $(VENV_ACTIVATE)")

$(TOX_EXE): | $(VENV_BIN_DIR)
	$(call actionmsg, installing $@ ...)
	$(NOISE)$(VENV_ACTIVATE_CMD) $(PYTHON) -m pip install $(basename $(@F))

$(PRECOMMIT_EXE): | $(VENV_BIN_DIR)
	$(call actionmsg, installing $@ ...)
	$(NOISE)$(VENV_ACTIVATE_CMD) $(PYTHON) -m pip install pre-commit

$(VENV_BIN_DIR):
	$(NOISE)$(PYTHON) -m venv .venv

## -- Tox ---------------------------------------------------------------------

tox: | $(TOX_EXE) ## Execute specific tox environment using e parameter (ex. make tox e=py311)
	$(NOISE)$(if $(e),,$(error e is required, e.g. 'make tox e=py311' — see tox.ini for env names))
	$(NOISE)$(ECHO_CMD)$(TOX_CMD) -e $(e) $(TOX_ARG)

syntax: e=syntax ## Perform all formatting, styling and coding checks
syntax: tox

black: e=black ## Run black as code formatter
black: tox

isort: e=isort ## Run isort to review import order
isort: tox

mypy: e=mypy ## Run mypy as static typing checker
mypy: tox

flake8: e=flake8 ## Run flake8 as style guide checker
flake8: tox

pylint: e=pylint ## Run pylint as static code analyser
pylint: tox

cover: e=cover ## Run tests with coverage report (term + html)
cover: tox

doc: e=docs ## Generate documentation
doc: tox

## -- Testing -----------------------------------------------------------------

test: e=unit,cli ## Run all tests
test: tox

test-unit: e=unit ## Run unit tests
test-unit: tox

test-cli: e=cli ## Run cli tests
test-cli: tox

test-functional: e=functional ## Run functional tests (requires running mssql/oracle/postgres stack)
test-functional: tox

test-functional-light: e=functional-light ## Run functional tests excluding Oracle (requires mssql + postgres stack)
test-functional-light: tox

test-oracle: e=functional-oracle ## Run Oracle-only functional tests (requires Oracle container)
test-oracle: tox

endif
