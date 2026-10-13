cmake_minimum_required(VERSION 3.20)
project(
  qarray-charge-tuning-demo
  VERSION 1.0.0
  DESCRIPTION "FAlCon charge-tuning demo driven by the qarray quantum-dot simulator"
  HOMEPAGE_URL "https://github.com/falcon-autotuning/qarray-charge-tuning-demo"
  LANGUAGES CXX C
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(BUILD_TESTS "Build tests" OFF)
option(USE_CCACHE "Enable ccache or sccache if available" ON)
option(ENABLE_PCH "Enable target_precompile_headers to speed up builds" ON)

if(WIN32)
  add_compile_definitions(NOMINMAX)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
endif()

# Try to auto-detect a compiler launcher (prefer sccache if present)
if(USE_CCACHE)
  find_program(SCCACHE_PROGRAM sccache)
  if(SCCACHE_PROGRAM)
    message(STATUS "Using sccache: ${SCCACHE_PROGRAM}")
    set(CMAKE_C_COMPILER_LAUNCHER ${SCCACHE_PROGRAM})
    set(CMAKE_CXX_COMPILER_LAUNCHER ${SCCACHE_PROGRAM})
  else()
    find_program(CCACHE_PROGRAM ccache)
    if(CCACHE_PROGRAM)
      message(STATUS "Using ccache: ${CCACHE_PROGRAM}")
      set(CMAKE_C_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
      set(CMAKE_CXX_COMPILER_LAUNCHER ${CCACHE_PROGRAM})
    else()
      message(STATUS "No ccache/sccache found (fine, builds will just be normal).")
    endif()
  endif()
endif()

# ── Python: pin CPython to the venv, headers and library included ────────────
# Passing only -DPython3_EXECUTABLE is NOT enough. vcpkg's toolchain puts its own
# python3 port on CMAKE_PREFIX_PATH, so FindPython3 will happily pair the venv
# interpreter with vcpkg's headers and libpython — the exact mismatch
# falcon-qarray-device's CMakeLists warns about, and one that only shows up as a
# confusing import failure at runtime.
#
# So ask the pinned interpreter where its own headers and libpython live, and
# seed the FindPython3 cache entries directly. This must run BEFORE any
# find_package that pulls Python in transitively — falcon-qarray-device's config
# file calls find_dependency(Python3) itself.
if(DEFINED Python3_EXECUTABLE)
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
            "import sysconfig; print(sysconfig.get_paths()['include'])"
    OUTPUT_VARIABLE FALCON_PY_INCLUDE
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE FALCON_PY_INCLUDE_RC
  )
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
            "import os, sysconfig; print(os.path.join(sysconfig.get_config_var('LIBDIR'), sysconfig.get_config_var('LDLIBRARY')))"
    OUTPUT_VARIABLE FALCON_PY_LIBRARY
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE FALCON_PY_LIBRARY_RC
  )
  if(FALCON_PY_INCLUDE_RC EQUAL 0 AND FALCON_PY_LIBRARY_RC EQUAL 0
     AND EXISTS "${FALCON_PY_INCLUDE}/Python.h" AND EXISTS "${FALCON_PY_LIBRARY}")
    set(Python3_INCLUDE_DIR "${FALCON_PY_INCLUDE}"
        CACHE PATH "Python headers, pinned to the venv" FORCE)
    set(Python3_LIBRARY "${FALCON_PY_LIBRARY}"
        CACHE FILEPATH "libpython, pinned to the venv" FORCE)
    message(STATUS "Pinned Python headers: ${FALCON_PY_INCLUDE}")
    message(STATUS "Pinned libpython     : ${FALCON_PY_LIBRARY}")
  else()
    message(WARNING
      "Could not resolve headers/libpython from ${Python3_EXECUTABLE}; FindPython3 "
      "may pair it with vcpkg's python3 instead. Expect runtime import failures.")
  endif()
  set(Python3_FIND_STRATEGY LOCATION)
  set(Python3_FIND_REGISTRY NEVER)
  set(Python3_FIND_FRAMEWORK NEVER)
endif()

find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
message(STATUS "Python3 interpreter : ${Python3_EXECUTABLE}")
message(STATUS "Python3 include dirs: ${Python3_INCLUDE_DIRS}")
message(STATUS "Python3 libraries   : ${Python3_LIBRARIES}")

# ── Dependencies (all from vcpkg_installed/${VCPKG_TARGET_TRIPLET}) ───────────
find_package(pybind11             CONFIG REQUIRED)
find_package(falcon-core          CONFIG REQUIRED)
find_package(falcon-typing        CONFIG REQUIRED)
find_package(falcon-qarray-device CONFIG REQUIRED)
find_package(spdlog               CONFIG REQUIRED)
find_package(yaml-cpp             CONFIG REQUIRED)
find_package(xtensor              CONFIG REQUIRED)

# plplot ships no CMake config package in vcpkg — locate it by hand.
find_path(PLPLOT_INCLUDE_DIR
  NAMES plplot/plplot.h
  PATHS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/include"
  REQUIRED
)
find_library(PLPLOT_LIBRARY
  NAMES plplot
  PATHS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/lib"
  REQUIRED
)
find_library(PLPLOT_CXX_LIBRARY
  NAMES plplotcxx
  PATHS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/lib"
  REQUIRED
)
message(STATUS "plplot: ${PLPLOT_LIBRARY} / ${PLPLOT_CXX_LIBRARY}")

# ── Paths derived from the vcpkg tree and the pinned interpreter ─────────────
set(VCPKG_TREE "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}")

list(GET Python3_INCLUDE_DIRS 0 PYTHON_INCLUDE_DIR)

# Absolute libpython for the RTLD_GLOBAL dlopen in ensure_python_interpreter().
# Python3_LIBRARIES can be a config-keyword list ("optimized;<rel>;debug;<dbg>"),
# which cannot be embedded in a -D flag — resolve a single release path.
if(DEFINED Python3_LIBRARY_RELEASE AND EXISTS "${Python3_LIBRARY_RELEASE}")
  set(FALCON_LIBPYTHON_PATH "${Python3_LIBRARY_RELEASE}")
else()
  set(FALCON_LIBPYTHON_CANDIDATES ${Python3_LIBRARIES})
  list(FILTER FALCON_LIBPYTHON_CANDIDATES EXCLUDE REGEX "^(optimized|debug|general)$")
  list(GET FALCON_LIBPYTHON_CANDIDATES 0 FALCON_LIBPYTHON_PATH)
endif()

get_filename_component(PYTHON_LIBRARY_DIR "${FALCON_LIBPYTHON_PATH}" DIRECTORY)
# -l name for the interpreter's shared libpython (libpython3.12.so -> python3.12).
# NAME_WLE, not NAME_WE: the latter strips from the FIRST dot, giving "libpython3",
# whose -lpython3 resolves to the stable-ABI stub in whichever -L dir comes first.
get_filename_component(PYTHON_LINK_NAME "${FALCON_LIBPYTHON_PATH}" NAME_WLE)
string(REGEX REPLACE "^lib" "" PYTHON_LINK_NAME "${PYTHON_LINK_NAME}")

# device.py, installed by the falcon-qarray-device port. Device.cpp bakes only a
# prefix-relative path, so the absolute one has to be handed over at runtime.
set(FALCON_QARRAY_PYTHON_PATH "${VCPKG_TREE}/share/falcon-qarray-device")
# plplot resolves its font/colour-map data through PLPLOT_LIB.
set(PLPLOT_DATA_DIR "${VCPKG_TREE}/share/plplot/data")

# ── The ffimport shim hub.fal binds to ───────────────────────────────────────
# The falcon DSL toolchain compiles qarray-wrapper.cpp itself from the flag lists
# in hub.fal. Building it here as a shared library is what keeps those flags
# honest: it is the same translation unit against the same headers, so any drift
# in falcon-core / falcon-typing / falcon-qarray-device surfaces at `make build`
# instead of halfway through a DSL run.
add_library(qarray-wrapper SHARED qarray-wrapper.cpp)

target_include_directories(qarray-wrapper PRIVATE ${PLPLOT_INCLUDE_DIR})

target_compile_definitions(qarray-wrapper
  PRIVATE FALCON_LIBPYTHON_PATH="${FALCON_LIBPYTHON_PATH}")

target_link_libraries(qarray-wrapper
  PRIVATE
    falcon-core::falcon-core
    falcon::falcon-typing
    falcon::falcon-qarray-device
    spdlog::spdlog
    yaml-cpp::yaml-cpp
    xtensor
    pybind11::embed
    ${PLPLOT_CXX_LIBRARY}
    ${PLPLOT_LIBRARY}
    ${CMAKE_DL_LIBS}
)

set_target_properties(qarray-wrapper PROPERTIES
  PREFIX "lib"
  POSITION_INDEPENDENT_CODE ON
)

if(ENABLE_PCH)
  target_precompile_headers(qarray-wrapper
    PRIVATE
      <string> <vector> <map> <memory> <stdexcept>
  )
endif()

# ── Generated build configuration ────────────────────────────────────────────
# hub.fal's `ffimport` block takes literal -I/-L/-l flags — there is no CMake
# integration step for it — so generate it from the template rather than asking
# anyone to keep hand-written paths in sync with vcpkg_installed.
configure_file(
  "${CMAKE_SOURCE_DIR}/hub.fal.in"
  "${CMAKE_SOURCE_DIR}/hub.fal"
  @ONLY
)
message(STATUS "Generated hub.fal with ffimport flags for ${VCPKG_TREE}")

configure_file(
  "${CMAKE_SOURCE_DIR}/cmake/env.sh.in"
  "${CMAKE_BINARY_DIR}/env.sh"
  @ONLY
)
file(CHMOD "${CMAKE_BINARY_DIR}/env.sh"
  PERMISSIONS
    OWNER_READ OWNER_WRITE OWNER_EXECUTE
    GROUP_READ GROUP_EXECUTE
    WORLD_READ WORLD_EXECUTE
)

file(WRITE "${CMAKE_BINARY_DIR}/build-info.json"
  "{
  \"VCPKG_INSTALLED_DIR\": \"${VCPKG_INSTALLED_DIR}\",
  \"VCPKG_TRIPLET\": \"${VCPKG_TARGET_TRIPLET}\",
  \"CMAKE_BUILD_TYPE\": \"${CMAKE_BUILD_TYPE}\",
  \"PYTHON_EXECUTABLE\": \"${Python3_EXECUTABLE}\",
  \"FALCON_QARRAY_PYTHON_PATH\": \"${FALCON_QARRAY_PYTHON_PATH}\"
}")
message(STATUS "Generated env.sh and build-info.json in ${CMAKE_BINARY_DIR}")

# ── Tests ────────────────────────────────────────────────────────────────────
if(BUILD_TESTS)
  enable_testing()
  add_test(
    NAME qarray-wrapper-symbols
    COMMAND "${CMAKE_COMMAND}"
            -D "WRAPPER_LIB=$<TARGET_FILE:qarray-wrapper>"
            -P "${CMAKE_SOURCE_DIR}/cmake/check-ffi-symbols.cmake"
  )
  set_tests_properties(qarray-wrapper-symbols PROPERTIES
    ENVIRONMENT "LD_LIBRARY_PATH=${VCPKG_TREE}/lib:${PYTHON_LIBRARY_DIR}"
  )

  # A green CMake build is not sufficient evidence the demo will run: CMake links
  # the full transitive closure of every dependency, whereas the DSL toolchain
  # gets only the hand-listed -l flags in hub.fal's ffimport block. Rebuild the
  # wrapper from those flags alone to prove the list is complete.
  find_program(BASH_PROGRAM bash)
  if(BASH_PROGRAM)
    add_test(
      NAME ffimport-flags
      COMMAND "${BASH_PROGRAM}" "${CMAKE_SOURCE_DIR}/cmake/verify-ffimport-flags.sh"
      WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    )
    set_tests_properties(ffimport-flags PROPERTIES
      ENVIRONMENT "CXX=${CMAKE_CXX_COMPILER}"
    )
  endif()
endif()

# ── Install ──────────────────────────────────────────────────────────────────
include(GNUInstallDirs)

if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
  set(CMAKE_INSTALL_PREFIX "/opt/falcon" CACHE PATH "Installation prefix" FORCE)
endif()

install(TARGETS qarray-wrapper
  LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)

install(FILES
  "${CMAKE_SOURCE_DIR}/hub.fal"
  "${CMAKE_SOURCE_DIR}/chargeConfigurationTuner.fal"
  "${CMAKE_SOURCE_DIR}/stateStepper.fal"
  "${CMAKE_SOURCE_DIR}/falcon.yml"
  "${CMAKE_SOURCE_DIR}/2_dot.yml"
  DESTINATION ${CMAKE_INSTALL_DATADIR}/qarray-charge-tuning-demo
)
