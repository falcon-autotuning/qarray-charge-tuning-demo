vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO falcon-autotuning/falcon-dsl
    REF v${VERSION}
    SHA512 8d01a95e8c9ecd4296d66ea52af8bb30670637ad82e96b45b87e12f8b7969e4e25c236cf7247b60af79893e9a1e2f5092b9241456d8d3b0a784d8e35e0ec23cf
)
vcpkg_cmake_configure(
    SOURCE_PATH "${SOURCE_PATH}"
    OPTIONS -DBUILD_TESTS=OFF
)
vcpkg_cmake_install()
vcpkg_cmake_config_fixup()

# falcon-dsl installs the falcon-run / falcon-test CLIs into bin/. vcpkg expects a
# library port to keep executables under tools/<port>/, so move them there; this is
# what puts the DSL toolchain inside vcpkg_installed instead of /opt/falcon.
vcpkg_copy_tools(TOOL_NAMES falcon-run falcon-test AUTO_CLEAN)

file(INSTALL "${SOURCE_PATH}/LICENSE"
     DESTINATION "${CURRENT_PACKAGES_DIR}/share/${PORT}"
     RENAME copyright)
vcpkg_copy_pdbs()
