# Verifies that libqarray-wrapper.so actually exports every routine hub.fal
# declares via `ffimport`. A missing symbol here means a `.fal` run would fail at
# dispatch time with nothing but a dlsym error to go on.
#
# Run via: cmake -D WRAPPER_LIB=<path> -P cmake/check-ffi-symbols.cmake

if(NOT DEFINED WRAPPER_LIB)
  message(FATAL_ERROR "WRAPPER_LIB not set")
endif()
if(NOT EXISTS "${WRAPPER_LIB}")
  message(FATAL_ERROR "Wrapper library not found: ${WRAPPER_LIB}")
endif()

set(EXPECTED_SYMBOLS
  CollectCurrentDeviceState
  CollectCurrentPlungerGates
  Ramp
  AnalyzeBlips
  EndState
  RestartDevice
  MakeStabilityDiagram
  BuildVirtualizationMatrix
)

find_program(NM_PROGRAM NAMES nm llvm-nm)
if(NOT NM_PROGRAM)
  message(WARNING "nm not found — skipping FFI symbol check")
  return()
endif()

execute_process(
  COMMAND "${NM_PROGRAM}" --dynamic --defined-only "${WRAPPER_LIB}"
  OUTPUT_VARIABLE NM_OUTPUT
  RESULT_VARIABLE NM_RESULT
  ERROR_VARIABLE NM_ERROR
)
if(NOT NM_RESULT EQUAL 0)
  message(FATAL_ERROR "nm failed on ${WRAPPER_LIB}: ${NM_ERROR}")
endif()

set(MISSING "")
foreach(SYM IN LISTS EXPECTED_SYMBOLS)
  # Match a whole-word symbol name in the nm listing. Unmangled (extern "C")
  # names appear verbatim; a C++-mangled hit would not match this pattern.
  if(NOT NM_OUTPUT MATCHES "[ \t]${SYM}(\n|$)")
    list(APPEND MISSING "${SYM}")
  endif()
endforeach()

if(MISSING)
  string(REPLACE ";" ", " MISSING_STR "${MISSING}")
  message(FATAL_ERROR
    "qarray-wrapper does not export the routines hub.fal declares: ${MISSING_STR}")
endif()

list(LENGTH EXPECTED_SYMBOLS N)
message(STATUS "✓ qarray-wrapper exports all ${N} ffimport routines")
