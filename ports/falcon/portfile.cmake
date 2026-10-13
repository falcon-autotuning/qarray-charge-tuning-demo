# The `falcon` repo (formerly `falcon-lib`) is two things at once:
#
#   1. a CPack aggregate whose CMakeLists copies vcpkg_installed/{bin,lib,include,
#      share} into /opt/falcon and tars it up — that IS where /opt/falcon comes
#      from, and it is exactly what we do NOT want here; and
#   2. the `.fal` DSL standard library under libs/, which is the only part a
#      consumer actually needs.
#
# So this port deliberately does not configure or build anything. It installs
# libs/ as data, laid out so falcon-package-manager can discover it: every
# directory containing a falcon.yml is a package root, and PackageResolver
# recursively scans each FALCON_LIBRARY_PATH entry for them.
#
# Installing to share/falcon/libs (keeping the `libs/` prefix) means an import
# written as "libs/collections/map/map.fal" resolves against
# FALCON_LIBRARY_PATH=<vcpkg-tree>/share/falcon.
set(VCPKG_POLICY_EMPTY_PACKAGE enabled)

vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO falcon-autotuning/falcon
    REF v${VERSION}
    SHA512 e368e86271b97b8c05399b693a8558eda1c8869891bf22472c66de5debaef81a7fd287af9465396091e0a8e6d47089a903e144bc466743a7b1fdbe0461f2e802
)

file(COPY "${SOURCE_PATH}/libs"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}")

# ── Retarget the stdlib off /opt/falcon and onto current falcon-core ──────────
# The .fal standard library in v1.1.4 has never been updated for falcon-core 1.2.x.
# It ships no prebuilt .so, so every FFI wrapper is compiled on first use and all
# three of these must be right or the import fails at run time:
#
#   1. paths hardcoded to /opt/falcon — which is only a CPack copy of an installed
#      vcpkg tree, and does not exist in a ports-based setup;
#   2. #include "falcon_core/..." — the install directory is hyphenated
#      (falcon-core/) and has been for some time; there is no compat alias;
#   3. -lfalcon_core_cpp — that library no longer exists under any name; the
#      current artifact is libfalcon-core.so.
#
# (2) and (3) are the same drift GOAL1 §A.1 found in the demo's own
# qarray-wrapper.cpp, just spread across ~50 files here.
#
# TEMPORARY: delete this block once a `falcon` tag ships a stdlib built against
# current falcon-core. Report upstream rather than carrying this indefinitely.
file(GLOB_RECURSE FALCON_LIB_SOURCES
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.fal"
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.cpp"
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.hpp"
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.yml")

set(FALCON_RETARGET_COUNT 0)
foreach(FALCON_LIB_SOURCE IN LISTS FALCON_LIB_SOURCES)
    file(READ "${FALCON_LIB_SOURCE}" FALCON_LIB_TEXT)
    set(FALCON_LIB_ORIGINAL "${FALCON_LIB_TEXT}")

    # Order matters: /opt/falcon/libs must be rewritten before /opt/falcon/lib,
    # otherwise the shorter prefix eats it and leaves a bogus "<tree>/libs" path.
    string(REPLACE "/opt/falcon/libs" "${CURRENT_INSTALLED_DIR}/share/${PORT}/libs" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    string(REPLACE "/opt/falcon/lib"  "${CURRENT_INSTALLED_DIR}/lib"                FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    string(REPLACE "/opt/falcon/include" "${CURRENT_INSTALLED_DIR}/include"         FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")

    # Old falcon-core artifact names. Rewrite the full filename before the -l form
    # so the bare-path ffimport variants are covered too.
    string(REPLACE "libfalcon_core_cpp.so" "libfalcon-core.so" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    string(REPLACE "-lfalcon_core_cpp"     "-lfalcon-core"     FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")

    # The `database` package's wrapper calls falcon_core::...::Connection::name(),
    # but its ffimport block links only -lfalcon-database -lpqxx, and
    # libfalcon-database.so has no DT_NEEDED on libfalcon-core either. The wrapper
    # therefore compiles and then fails at dlopen with an undefined symbol. It is
    # the only package in the stdlib with this defect (the rest already link what
    # they include). Add the missing flag.
    string(REPLACE "\"-lfalcon-database\"" "\"-lfalcon-database\" \"-lfalcon-core\"" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")

    # Some stdlib files import via the github.com/ form, e.g.
    #   import "github.com/falcon-autotuning/falcon-lib/libs/collections/array";
    # PackageResolver::resolve() short-circuits on that prefix straight to
    # resolve_github_package() — skipping the local search path and trying to
    # download. It names falcon-lib (the repo's former name) with no version, so
    # the URL comes out as ".../archive/refs/tags/.tar.gz" and 404s. Rewriting to
    # a bare path resolves locally instead: resolve_local() treats a directory
    # holding a falcon.yml as a package, so the trailing ".fal" is not needed.
    #
    # .fal only: the identical string also appears as a `github:` metadata field
    # in falcon.yml, where rewriting it would corrupt the manifest.
    if(FALCON_LIB_SOURCE MATCHES "[.]fal$")
        string(REPLACE "github.com/falcon-autotuning/falcon-lib/libs/" "libs/" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    endif()

    # Two manifests (strings, collections/array) list the wrapper SOURCE under
    # `ffi:` rather than the built object. The DSL treats that entry as a prebuilt
    # library and dlopen()s it, failing with "invalid ELF header". The other 47
    # wrapper packages omit `ffi:` altogether and let the DSL add the .so itself,
    # which is why only these two break.
    if(FALCON_LIB_SOURCE MATCHES "falcon[.]yml$")
        string(REPLACE "-wrapper.cpp\"" "-wrapper.so\"" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    endif()

    # strings-wrapper.cpp was written against an older fmt. Two independent
    # breakages against the fmt 12.2 in this tree, which must be fixed together —
    # correcting only the first yields a consteval error instead:
    #
    #   a) <fmt/core.h> no longer pulls in fmt::format. Since fmt 11 that header
    #      is a shim over base.h and only includes format.h under
    #      FMT_DEPRECATED_HEAVY_CORE, hence "'format' is not a member of 'fmt'".
    #   b) the format string here is a runtime std::string (read out of the
    #      parameter map), and since fmt 10 format strings are consteval-checked;
    #      a runtime one must be wrapped in fmt::runtime().
    #
    # The replacement is written so the original closing paren balances the added
    # fmt::runtime( — covering the 0-arg call and the variadic ones alike.
    string(REPLACE "#include <fmt/core.h>" "#include <fmt/format.h>" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")
    string(REPLACE "fmt::format(fmt_str" "fmt::format(fmt::runtime(fmt_str)" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")

    # Include directory: falcon_core/ -> falcon-core/. The trailing slash keeps
    # this from touching the falcon_core_cpp names handled above, and the C++
    # namespace (falcon_core::) is correctly left underscored.
    string(REPLACE "falcon_core/" "falcon-core/" FALCON_LIB_TEXT "${FALCON_LIB_TEXT}")

    if(NOT FALCON_LIB_TEXT STREQUAL FALCON_LIB_ORIGINAL)
        file(WRITE "${FALCON_LIB_SOURCE}" "${FALCON_LIB_TEXT}")
        math(EXPR FALCON_RETARGET_COUNT "${FALCON_RETARGET_COUNT} + 1")
    endif()
endforeach()

message(STATUS "falcon: retargeted ${FALCON_RETARGET_COUNT} stdlib file(s) off /opt/falcon and onto falcon-core")

# Fail loudly rather than shipping a stdlib that cannot compile its wrappers.
file(GLOB_RECURSE FALCON_STALE_REFS
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.fal"
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*.cpp")

# A manifest still naming a .cpp under ffi: would dlopen the source at run time.
file(GLOB_RECURSE FALCON_MANIFESTS "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/falcon.yml")
foreach(FALCON_MANIFEST IN LISTS FALCON_MANIFESTS)
    file(READ "${FALCON_MANIFEST}" FALCON_MANIFEST_TEXT)
    if(FALCON_MANIFEST_TEXT MATCHES "-wrapper[.]cpp")
        message(FATAL_ERROR "falcon: ${FALCON_MANIFEST} still lists a wrapper source under ffi:")
    endif()
endforeach()
foreach(FALCON_STALE_REF IN LISTS FALCON_STALE_REFS)
    file(READ "${FALCON_STALE_REF}" FALCON_STALE_TEXT)
    if(FALCON_STALE_TEXT MATCHES "/opt/falcon|falcon_core/|falcon_core_cpp|github[.]com/falcon-autotuning/falcon-lib/libs/")
        message(FATAL_ERROR "falcon: stale reference survived retargeting in ${FALCON_STALE_REF}")
    endif()
endforeach()

# Sanity-check that the payload is actually discoverable: a silently empty
# install would only surface much later as an unresolvable DSL import.
file(GLOB_RECURSE FALCON_LIB_MANIFESTS
     "${CURRENT_PACKAGES_DIR}/share/${PORT}/libs/*/falcon.yml")
list(LENGTH FALCON_LIB_MANIFESTS FALCON_LIB_COUNT)
if(FALCON_LIB_COUNT EQUAL 0)
    message(FATAL_ERROR "falcon: no falcon.yml package manifests found under libs/")
endif()
message(STATUS "falcon: installed ${FALCON_LIB_COUNT} DSL packages under share/${PORT}/libs")

file(INSTALL "${SOURCE_PATH}/LICENSE"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"
     RENAME copyright)
