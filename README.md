# QArray Charge Tuning Demo

## Overview

This demo demonstrates QArray charge tuning using FAlCon, leveraging a device characteristics database for robust global variable management.  
**Supported Platforms:** Linux (native); Windows Subsystem for Linux (WSL) may be compatible.

## Key Components

- **ChargeConfigurationTuner**: Manages high-level charge system autotuning.
- **BlipStateStepper**: Provides fine-grained control for crossing charge boundaries.

## Getting Started

### Prerequisites

- Linux or WSL
- A C++20 compiler. The clang presets pin **clang-18** (`clang-18`/`clang++-18`);
  plain `clang` on Ubuntu 22.04 is 14.0.0 and fails on libstdc++ 13's `<chrono>`.
  Use `PRESET=linux-gcc-release` for gcc.
- **`clang-scan-deps-18`** (`sudo apt install clang-tools-18`). CMake 4.x enables
  C++20 module dependency scanning for `falcon-typing`, `falcon-dsl` and
  `falcon-package-manager`; without it every `try_compile` exits 127 and the error
  you actually see is `Could NOT find Threads`, which points nowhere near the cause.
- CMake ≥ 3.20, Ninja, and Git
- [`uv`](https://docs.astral.sh/uv/) — used to provision the Python 3.12 interpreter the simulator runs on
- Docker (for the PostgreSQL global-variable store)
- Mono (`mono-complete`) — only if you want the NuGet binary cache, see below

> **If `/tmp` is mounted `noexec`** (check with `findmnt -no OPTIONS /tmp`), vcpkg
> cannot execute the helper tools it extracts there and fails with a bare
> `Permission denied`. The Makefile detects this and redirects `TMPDIR` to a
> project-local `.tmp/` for the vcpkg stage.

Everything else — falcon-core, falcon-typing, falcon-qarray-device, **falcon-dsl**
(the `falcon-run` / `falcon-test` CLIs), **falcon** (the `.fal` standard library),
falcon-package-manager, plplot, pybind11, xtensor, yaml-cpp, spdlog — is built into
this repo's own `vcpkg_installed/` tree by `make`. There is no dependency on a
system-wide `/opt/falcon` install, and none on any sibling repository being checked
out or built.

`/opt/falcon` exists upstream only because the `falcon` repo's CMakeLists is a CPack
aggregate that copies `vcpkg_installed/{bin,lib,include,share}` into that prefix and
tars it up. Building the same components as ports puts them in `vcpkg_installed/`
directly, so that staging step is simply not needed here.

### Installing Docker

Only the `make docker-*` targets need Docker; `make build` and `make test` do not.

Install Docker Engine **and** Compose. Compose v2 is a `docker` subcommand
(`docker compose`); the old standalone `docker-compose` binary reached end-of-life
in 2023 and is no longer packaged by current distributions — installing it by that
name is what produces `make: docker-compose: No such file or directory`. The
Makefile accepts either, preferring v2.

**Ubuntu/Debian:**

```sh
sudo apt update
sudo apt install docker.io docker-compose-v2
```

**Fedora:**

```sh
sudo dnf install docker docker-compose-plugin
```

**Arch Linux:**

```sh
sudo pacman -S docker docker-compose
```

For other distributions see the official [Docker documentation](https://docs.docker.com/engine/install/). Verify with:

```sh
docker compose version
```

Depending on your system you may need to log out and log back in for your Docker group membership to take effect.

### Building

The demo follows the same build layout as `instrument-controller`: a vcpkg
manifest (`vcpkg.json`), overlay ports (`ports/`), overlay triplets, and CMake
presets, all driven from the `Makefile`.

```bash
git submodule update --init --recursive   # pulls cmake/bootstrap
make build                                # venv -> vcpkg -> cmake -> compile
```

`make build` runs three stages, each usable on its own:

| Target | What it does |
|---|---|
| `make venv-setup` | Creates `./venv` (Python 3.12 via `uv`) and installs `qarray` into it |
| `make vcpkg-bootstrap` | Clones vcpkg + triplets, wires up the NuGet binary cache, installs every port from `vcpkg.json` into `./vcpkg_installed` |
| `make configure` / `make build` | Configures and compiles `qarray-wrapper.cpp` into `libqarray-wrapper.so` |

Other targets: `make test`, `make install`, `make clean`, `make venv-reset`,
and `make help`. Override the toolchain with `PRESET=`, e.g.
`make build PRESET=linux-gcc-release`.

#### Why the venv comes first

`falcon-qarray-device` embeds CPython through `pybind11::embed` and imports the
`qarray` package at runtime. It therefore has to be *built* against the same
interpreter that has `qarray` installed. The `Makefile` exports
`FALCON_QARRAY_PYTHON` pointing at `./venv/bin/python`; the
`ports/falcon-qarray-device` portfile reads it and pins cmake's `FindPython3` to
that interpreter. Building the port without it will produce a library whose
embedded interpreter cannot find `qarray`.

#### NuGet binary cache (optional)

`make vcpkg-bootstrap` reads `.nuget-credentials` (gitignored) and, if present,
configures the shared Azure DevOps `cpp-cache` feed as a vcpkg binary source, so
ports come down prebuilt instead of compiling from source. The file is four
`KEY=VALUE` lines — `FEED_URL`, `NUGET_API_KEY`, `FEED_NAME`, `USERNAME` — the
same format `instrument-controller` uses; copy it from there. Without it the
build still works, it just compiles everything locally.

### Generated files

`make configure` generates two files from checked-in templates. Do not edit the
generated copies — they are overwritten on every configure:

- **`hub.fal`** (from `hub.fal.in`) — its `ffimport` block is the demo's entire
  native build configuration, since the DSL toolchain compiles
  `qarray-wrapper.cpp` itself from those literal `-I`/`-L`/`-l` flags. CMake
  fills in the absolute paths to `vcpkg_installed/` and to the venv's Python, so
  they cannot drift from what was actually built.
- **`build/<preset>/env.sh`** — exports `LD_LIBRARY_PATH`, `PLPLOT_LIB`,
  `FALCON_QARRAY_PYTHON_PATH` (where the port installed `device.py`) and
  `QARRAY_CONFIG_PATH`.

### Database Setup

Ensure PostgreSQL is running and configure the Falcon test database:

```bash
make docker-up
```

The `falcon-database` stdlib package reads the connection string from
`FALCON_DATABASE_URL`, and `database::InitializeSchema()` fails if it is unset.
`env.sh` already defaults it to the credentials in `docker-compose.test.yml`, so
nothing more is needed for the local container. To target a different server,
export your own value before sourcing `env.sh`:

```bash
export FALCON_DATABASE_URL="postgresql://user:password@host:5432/dbname"
```

### Running the Demo

Source the generated environment, then run the test suite with the `falcon-test`
CLI from [falcon-dsl](https://github.com/falcon-autotuning/falcon-dsl):

```bash
make build
make docker-up
. build/linux-clang-release/env.sh
falcon-test ./tests/run_tests.fal --log-level info
```

- Adjust `--log-level` for desired verbosity (`info`, `debug`, etc.).

The `.fal` layer needs the DSL toolchain and standard library, both of which are
now vcpkg ports in this repo — `falcon-dsl` (the `falcon-run` / `falcon-test` CLIs,
installed to `tools/falcon-dsl/`) and `falcon` (the `.fal` standard library,
installed to `share/falcon/libs/`). `make build` provides both, and
`build/<preset>/env.sh` puts the CLIs on `PATH` and exports
`FALCON_LIBRARY_PATH=<vcpkg-tree>/share/falcon`.

Imports are written **without** a leading `../`:

```
"libs/collections/map/map.fal"
```

This is required, not cosmetic. `PackageResolver::resolve()` short-circuits on `./`
and `../` prefixes and resolves those against the importing file only — a relative
import never reaches `FALCON_LIBRARY_PATH`. Bare paths fall through to the search
path, where falcon-package-manager discovers every directory containing a
`falcon.yml` (53 of them in the standard library).

Imports of the demo's *own* files stay relative (`"../hub.fal"`), since they are
not packages on the search path.

> The C++ half has no such dependency: `make build` and `make test` work standalone
> in this repo, and are what verify the wrapper against current FALCON.


## Expected Output

The Device Under Test (DUT) is a double quantum dot system. The autotuner is tasked with tuning to the (1,2) charge configuration. The device includes a charge sensor, and the differential signal is visualized.

![Charge Stability Diagram](images/stability_diagram.png)

The autotuner adjusts plunger gate voltages to locate the (1,2) charge configuration, using the BlipStateStepper to navigate the charge stability diagram and cross charge boundaries as needed.

- **P1 Sweep:** Initial search in the P1 direction.
  ![vP1 sweep](images/analyze_blips_signal_1.png)
- **P2 Sweep:** Subsequent searches in the P2 direction to reach the target configuration.
  ![vP2 sweep](images/analyze_blips_signal_2.png)
  ![vP3 sweep](images/analyze_blips_signal_3.png)

## Explaining the Organization

This section will detail explaining some of the code details, and how this demo is implemented.

### Variable Scoping

Variable scoping is critical for charge stability diagram measurements. Variables may be defined at different levels:

```fal
autotuner Blip -> (Error err) {
  int autotuner_scope_variable;
  start -> init;
  state init {
    int state_scope_variable;
    terminal;
  }
}
```

- Within the `init` state, both `autotuner_scope_variable` and `state_scope_variable` are accessible.
- The autotuner itself does not have access to `state_scope_variable`.

For advanced scenarios (e.g., sweep resolution), variables can be injected at higher scopes using the PostgreSQL database.  
While a CLI exists for real deployments, this demo constructs them directly in the test.

### The Test File Itself

This test file is written using the [testing framework](https://github.com/falcon-autotuning/falcon-lib/tree/main/libs/testing) where the details of how to use the framework are explained in the library.
We have included only a single test in this suite, feel free to add more or customize our directly.
The test is called test_Charge1AndCharge2 and it attempts to tune the DUT to the (1,2) charge configuration.

The test begins by first restarting the attached [QArray](https://github.com/b-vanstraaten/QArray) simulation.
This QArray simulation is bound into the FAlCon DSL through the FFI that we designed.
As a result we have bound the simulation into an "effective device" in our C++ [package](https://github.com/falcon-autotuning/falcon-lib/tree/main/qarrayDevice).
This effective device manages its own voltage settings like a standard QD device in a laboratory setting.
In addition it can be configured to be either electron or holes via its constructor, and the finer details of configuring the device can be specified in the configuration file for the simulation.

Here is the yaml file for convenience

```yaml
gate_names:
  - P1
  - P2
  - B1
  - S1
sensor_config:
  S1: true
capacitances:
  Cgd:
    - [5.0, 0.5, 0.0, 0.0]
    - [0.5, 5.0, 0.0, 0.0]
  Cgs:
    - [0.01, 0.01, 0.01, 1.0]
```

This file specifies specifically the gates that are in use in our simulation, as well as the capacitance model used for the simulation purposes, as well as some coupling between the quantum dot gates and the charge sensor.
These values are best described in the QArray simulation.

Then we initialize the database schema.
The purpose of initializing the schema is to restart the global variables that this autotuner runs on.
We must resupply them for each test since these global variables parameterize the expected behavior.
These variables in the database are the ones that developers should expect that end users will be setting via an external yaml configuration for the entire falcon autotuner.
As such, make sure that your external environmental variables are compliant with other externally used modules.
In this case the global variables that this simple demo depends on are:

- virtualization: the virtual gates matrix for the DUT
- resolution: the number of points to take in a single 1D sweep
- virtualizationName: the names of the indexes of the virtual gates matrix
- interdotSpacing: the expected spacing of peaks in the virtualized gate voltage space for each dimension

Next, we initialize the starting conditions for the simulation.
We assume that we are tuned into the (0,0) charge configuration at the beginning of this autotuning session.
In this case we can tune to P1=0.0V and P2=0.0V.
We also detune our sensing dot to improve our SNR to S1=-0.1V.

Finally, we run the test autotuner by defining the variable types and running the autotuner.
Then we print the info about the ending location using the log package.

### The Charge Configuration Tuner

This autotuner focuses on navigating the high level charge stability diagram in two dimensions.
The autotuner itself contains 2 state variables, 'n' and 'm', that describe the current tuned state.
It then initialized tuning in the upwards direction on the stability diagram, and each time through it re-runs the tuning state with a new initial condition from the run state.
Each state launches a BlipStateStepper, which is responsible for tuning the DUT into the next selected charge state.

### The Blip State Stepper

This autotuner manages moving the DUT in the direction of the next selected charge state.
It accomplishes this by first unpacking all the global variables that we injected from the test in the checkDatabaseEntries state.
Then it unpacks all the InterDot spacings loaded since it needs to for loop through them in the state unpackInterdotSpacing.
Finally it performs the step by first analyzing the blip state, and then calculating a difference between its current state and the midpoint of teh found blips and ramps the device there.

### The Hub

You might notice that there were hub module routines that were called in the Blip State Stepper autotuner.
These routines are strongly typed in the hub file in the demo.
However, what might be surprising is that there are no implementations of any code in that file.
This is since the hub file is using our FFI interface to call functions from outside of the FAlCon DSL to accomplish tasks outside the DSL.
This is expected since implementing direct memory access is not the task of the DSL but is regulated to lower level implementation details.
Where authors decide to place this division is up to them.
It is however advantageous to keep as much code in the DSL as possible since it is much more interpretable and reuse-able.
This FFI interface uses the FFI-helpers, and the implementation is in the qarray-wrapper.
To understand more about this interface return to our standard [documentation](https://github.com/falcon-autotuning/falcon-lib/tree/main/typing).
We won't be going into much detail about the implementation here, but the details are there for your viewing pleasure.

## Support

For questions or issues, please open an issue in the repository.
