# falcon-qarray-device wraps the `qarray` Python package via pybind11::embed, so
# it must be built against the SAME interpreter that has qarray installed — not
# vcpkg's headers-only Python and not the system Python.
#
# The demo's Makefile creates that interpreter (`make venv-setup`, uv + Python
# 3.12) and exports its path as FALCON_QARRAY_PYTHON before invoking vcpkg, so
# pick it up here and pin cmake's FindPython3 to it.
if(DEFINED ENV{FALCON_QARRAY_PYTHON} AND NOT "$ENV{FALCON_QARRAY_PYTHON}" STREQUAL "")
    set(QARRAY_PYTHON "$ENV{FALCON_QARRAY_PYTHON}")
    if(NOT EXISTS "${QARRAY_PYTHON}")
        message(FATAL_ERROR
            "FALCON_QARRAY_PYTHON points at '${QARRAY_PYTHON}', which does not exist. "
            "Run `make venv-setup` in the demo root first.")
    endif()
    get_filename_component(QARRAY_PYTHON_ROOT "${QARRAY_PYTHON}" DIRECTORY)
    get_filename_component(QARRAY_PYTHON_ROOT "${QARRAY_PYTHON_ROOT}" DIRECTORY)
    message(STATUS "falcon-qarray-device: using Python ${QARRAY_PYTHON}")

    # -DPython3_EXECUTABLE alone is not enough: vcpkg's own python3 port is on
    # CMAKE_PREFIX_PATH, so FindPython3 would pair this interpreter with vcpkg's
    # headers and libpython. Resolve the interpreter's OWN headers and libpython
    # and pass them explicitly, so the built library and its embedded runtime
    # agree on exactly one CPython.
    execute_process(
        COMMAND "${QARRAY_PYTHON}" -c
                "import sysconfig; print(sysconfig.get_paths()['include'])"
        OUTPUT_VARIABLE QARRAY_PYTHON_INCLUDE
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    execute_process(
        COMMAND "${QARRAY_PYTHON}" -c
                "import os, sysconfig; print(os.path.join(sysconfig.get_config_var('LIBDIR'), sysconfig.get_config_var('LDLIBRARY')))"
        OUTPUT_VARIABLE QARRAY_PYTHON_LIBRARY
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    set(QARRAY_PYTHON_OPTIONS
        "-DPython3_EXECUTABLE=${QARRAY_PYTHON}"
        "-DPython3_ROOT_DIR=${QARRAY_PYTHON_ROOT}"
        "-DPython3_FIND_STRATEGY=LOCATION"
    )
    if(EXISTS "${QARRAY_PYTHON_INCLUDE}/Python.h" AND EXISTS "${QARRAY_PYTHON_LIBRARY}")
        message(STATUS "falcon-qarray-device: headers ${QARRAY_PYTHON_INCLUDE}")
        message(STATUS "falcon-qarray-device: libpython ${QARRAY_PYTHON_LIBRARY}")
        list(APPEND QARRAY_PYTHON_OPTIONS
            "-DPython3_INCLUDE_DIR=${QARRAY_PYTHON_INCLUDE}"
            "-DPython3_LIBRARY=${QARRAY_PYTHON_LIBRARY}"
        )
    else()
        message(WARNING
            "Could not resolve headers/libpython from ${QARRAY_PYTHON}; the build may "
            "link vcpkg's python3 instead, causing runtime import failures.")
    endif()
else()
    message(WARNING
        "FALCON_QARRAY_PYTHON is not set — falling back to whatever Python cmake finds. "
        "The embedded interpreter will likely not see the `qarray` package at runtime. "
        "Build via the demo's Makefile (`make build`) to set this automatically.")
    unset(QARRAY_PYTHON_OPTIONS)
endif()

# CAVEAT: vcpkg derives this port's ABI hash from the portfile and manifest, not
# from FALCON_QARRAY_PYTHON. Repointing the venv at a different interpreter will
# NOT by itself trigger a rebuild — run `vcpkg remove falcon-qarray-device` (or
# `make clean`) after `make venv-reset` if you change Python versions.

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO falcon-autotuning/falcon-qarray-device
    REF v${VERSION}
    SHA512 db78dd628a4445a199d1fa0d0897c3ed1a4a72935c36c911a17547744888738c326fba761b502f2af1633e972206f7e4bacce6a0eef4bc9d2560c11258c0f393
    PATCHES
        fix-config-pybind11.patch
)

vcpkg_cmake_configure(
    SOURCE_PATH "${SOURCE_PATH}"
    OPTIONS
        -DBUILD_TESTS=OFF
        ${QARRAY_PYTHON_OPTIONS}
)

vcpkg_cmake_install()
vcpkg_cmake_config_fixup()

# Upstream generates PythonModulePath.hpp pointing FALCON_QARRAY_PYTHON_MODULE_DIR
# at share/falcon-qarray-device, but never installs device.py there. Do it here so
# the embedded interpreter can actually import the module. The baked path is
# relative to the install prefix, so consumers still export an absolute
# FALCON_QARRAY_PYTHON_PATH at runtime (the demo's build/<preset>/env.sh does this).
file(INSTALL "${SOURCE_PATH}/src/device.py"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")

file(INSTALL "${SOURCE_PATH}/LICENSE"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"
     RENAME copyright)

vcpkg_copy_pdbs()
