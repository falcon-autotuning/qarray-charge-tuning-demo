.PHONY: help venv-setup venv-reset vcpkg-bootstrap configure build test install clean \
        check-compose docker-up docker-down docker-clean docker-logs

# Default to using standard system shell
SHELL ?= /bin/sh

# Build preset (user can override: make build PRESET=linux-gcc-release)
PRESET ?= linux-clang-release
CMAKE_BUILD_DIR := build/$(PRESET)
INSTALL_PREFIX ?= /opt/falcon

VENV_DIR ?= $(CURDIR)/venv
PYTHON_VERSION ?= 3.12
VENV_PYTHON := $(VENV_DIR)/bin/python

ifeq ($(OS),Windows_NT)
  SUDO :=
else
  SUDO := sudo
endif

# Compose v2 is a `docker` subcommand; v1 was a standalone `docker-compose` binary
# that reached end-of-life in 2023 and is absent from current distro packages.
# Detect whichever is present rather than hardcoding one and failing with a bare
# "docker-compose: No such file or directory".
# vcpkg extracts helper tools into the system temp dir and executes them there.
# A hardened /tmp mounted `noexec` makes that fail with a bare "Permission denied"
# (check with: findmnt -no OPTIONS /tmp). Fall back to a project-local temp dir.
BUILD_TMPDIR := $(shell \
  d=$${TMPDIR:-/tmp}; \
  if findmnt -no OPTIONS "$$d" 2>/dev/null | tr ',' '\n' | grep -qx noexec; then \
    echo "$(CURDIR)/.tmp"; \
  else \
    echo "$$d"; \
  fi)

# CMake 4.x enables C++20 module dependency scanning, which needs clang-scan-deps
# matching the compiler. Without it EVERY try_compile dies with exit 127, and the
# symptom is a baffling "Could NOT find Threads" rather than anything about modules.
# The clang presets pin clang-18, so CMake looks for the matching clang-scan-deps-18.
CXX_SCAN_DEPS := $(shell command -v clang-scan-deps-18 2>/dev/null || command -v clang-scan-deps 2>/dev/null)
# Only the clang presets need it.
NEEDS_SCAN_DEPS := $(findstring clang,$(PRESET))

DOCKER_COMPOSE_BIN = $(shell \
  if docker compose version >/dev/null 2>&1; then echo "docker compose"; \
  elif command -v docker-compose >/dev/null 2>&1; then echo "docker-compose"; \
  fi)
DOCKER_COMPOSE = $(DOCKER_COMPOSE_BIN) -f docker-compose.test.yml

all: build

help:
	@echo "QArray Charge Tuning Demo Build System"
	@echo "======================================"
	@echo ""
	@echo "Available targets:"
	@echo "  make venv-setup                 - Create ./venv (Python $(PYTHON_VERSION) via uv) with qarray"
	@echo "  make venv-reset                 - Recreate ./venv from scratch"
	@echo "  make vcpkg-bootstrap            - Clone/bootstrap vcpkg and install ports into ./vcpkg_installed"
	@echo "  make configure PRESET=<preset>  - Configure build (default: $(PRESET))"
	@echo "  make build PRESET=<preset>      - Build qarray-wrapper (default: $(PRESET))"
	@echo "  make test PRESET=<preset>       - Run tests (default: $(PRESET))"
	@echo "  make install PRESET=<preset>    - Install to $(INSTALL_PREFIX)"
	@echo "  make clean                      - Clean all build artifacts"
	@echo ""
	@echo "Docker (PostgreSQL used by the .fal demo):"
	@echo "  make docker-up / docker-down / docker-clean / docker-logs"
	@echo ""
	@echo "Available presets:"
	@cmake --list-presets=all 2>/dev/null || true

# ── Python ───────────────────────────────────────────────────────────────────
# falcon-qarray-device embeds CPython and imports the `qarray` package, so the
# interpreter it is BUILT against must be the one that has qarray installed.
# Everything downstream (the vcpkg port, cmake, the ffimport flags in hub.fal)
# is pinned to this venv.
# Idempotent: `make build` re-runs this every time, so only create the venv when
# it is missing. Use `make venv-reset` to rebuild it from scratch.
venv-setup:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "ERROR: 'uv' is not installed. See https://docs.astral.sh/uv/"; \
		exit 1; \
	fi
	@if [ ! -x "$(VENV_PYTHON)" ]; then \
		echo "Creating $(VENV_DIR) with Python $(PYTHON_VERSION) via uv..."; \
		uv venv --python $(PYTHON_VERSION) $(VENV_DIR); \
	fi
	@echo "Syncing Python dependencies into $(VENV_DIR)..."
	@uv pip install --quiet --python $(VENV_PYTHON) -r requirements.txt
	@echo "✓ Python dependencies installed ($$($(VENV_PYTHON) --version))"

venv-reset:
	@echo "Recreating $(VENV_DIR) from scratch..."
	@uv venv --python $(PYTHON_VERSION) --clear $(VENV_DIR)
	@uv pip install --python $(VENV_PYTHON) -r requirements.txt
	@echo "✓ venv reset"

# ── vcpkg ────────────────────────────────────────────────────────────────────
# Clones vcpkg + my-vcpkg-triplets, wires up the NuGet binary cache from
# .nuget-credentials, then installs every dependency in vcpkg.json using the
# overlay ports in ./ports.
vcpkg-bootstrap: venv-setup
	@echo "Bootstrapping vcpkg..."
	@if [ "$(BUILD_TMPDIR)" != "$${TMPDIR:-/tmp}" ]; then \
		mkdir -p "$(BUILD_TMPDIR)"; \
		echo "NOTE: $${TMPDIR:-/tmp} is mounted noexec; using $(BUILD_TMPDIR) for vcpkg temp files."; \
	fi
	@if [ -n "$(NEEDS_SCAN_DEPS)" ] && [ -z "$(CXX_SCAN_DEPS)" ]; then \
		echo "WARNING: clang-scan-deps not found."; \
		echo "  CMake enables C++20 module scanning for falcon-typing / falcon-dsl /"; \
		echo "  falcon-package-manager, and without it every try_compile fails with exit"; \
		echo "  127 — surfacing as 'Could NOT find Threads', not as a modules error."; \
		echo "  Install it:  sudo apt install clang-tools-18"; \
		echo ""; \
	fi
	TMPDIR=$(BUILD_TMPDIR) FALCON_QARRAY_PYTHON=$(VENV_PYTHON) \
	MAKELEVEL=0 cmake -D PRESET=$(PRESET) -P cmake/bootstrap/bootstrap-vcpkg.cmake

configure: vcpkg-bootstrap
	@echo "Configuring $(PRESET)..."
	MAKELEVEL=0 cmake --preset $(PRESET) \
		-DPython3_EXECUTABLE=$(VENV_PYTHON) \
		-DPython3_ROOT_DIR=$(VENV_DIR)

build: configure
	@echo "Building $(PRESET)..."
	cmake --build --preset $(PRESET)

# use POSIX . instead of source to ensure compatibility with /bin/sh on all platforms
test: build
	@echo "Running tests for $(PRESET)..."
	@if [ ! -f "$(CMAKE_BUILD_DIR)/env.sh" ]; then \
		echo "ERROR: $(CMAKE_BUILD_DIR)/env.sh not found."; \
		exit 1; \
	fi
	. $(CMAKE_BUILD_DIR)/env.sh && ctest --preset $(PRESET) --output-on-failure

install: build
	@echo "Installing $(PRESET) to $(INSTALL_PREFIX)..."
	$(SUDO) cmake --install $(CMAKE_BUILD_DIR) --prefix $(INSTALL_PREFIX)

clean:
	@echo "Cleaning all build artifacts..."
	rm -rf build vcpkg_installed venv
	@echo "✓ Clean complete"

# ── Docker (PostgreSQL backing the demo's global-variable store) ─────────────
check-compose:
	@if [ -z "$(DOCKER_COMPOSE_BIN)" ]; then \
		echo "ERROR: no Docker Compose found (looked for 'docker compose' and 'docker-compose')."; \
		echo ""; \
		echo "  Install Docker Engine plus the Compose plugin:"; \
		echo "    Ubuntu/Debian: sudo apt install docker.io docker-compose-v2"; \
		echo "    Fedora:        sudo dnf install docker docker-compose-plugin"; \
		echo "    Arch:          sudo pacman -S docker docker-compose"; \
		echo "    Other:         https://docs.docker.com/engine/install/"; \
		echo ""; \
		echo "  Verify with: docker compose version"; \
		echo "  You may need to log out and back in for group membership to apply."; \
		exit 1; \
	fi

docker-up: check-compose
	@echo "Starting PostgreSQL test database..."
	@$(DOCKER_COMPOSE) up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@for i in 1 2 3 4 5; do \
		if $(DOCKER_COMPOSE) exec -T postgres pg_isready -U falcon_test >/dev/null 2>&1; then \
			echo "✓ PostgreSQL is ready"; \
			exit 0; \
		fi; \
		echo "  Waiting... ($$i/5)"; \
		sleep 2; \
	done; \
	echo "✗ PostgreSQL failed to start"; \
	exit 1

docker-down: check-compose
	@echo "Stopping PostgreSQL test database..."
	@$(DOCKER_COMPOSE) down
	@echo "✓ PostgreSQL stopped"

docker-clean: check-compose
	@echo "Cleaning PostgreSQL test data..."
	@$(DOCKER_COMPOSE) down -v
	@echo "✓ PostgreSQL data cleaned"

docker-logs: check-compose
	@$(DOCKER_COMPOSE) logs -f postgres
