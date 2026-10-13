#!/usr/bin/env bash
# Compiles and links qarray-wrapper.cpp using EXACTLY the flags from hub.fal's
# `ffimport` block — nothing from CMake.
#
# The falcon DSL toolchain builds the wrapper from those literal flags, so a
# successful `make build` alone does not prove the demo will work: CMake links
# the full transitive dependency closure, while ffimport gets only the hand-listed
# -l flags. This script closes that gap.
#
# Usage: cmake/verify-ffimport-flags.sh [hub.fal]
set -euo pipefail

HUB="${1:-hub.fal}"
cd "$(dirname "$0")/.."

if [ ! -f "$HUB" ]; then
  echo "ERROR: $HUB not found — run 'make configure' first." >&2
  exit 1
fi

# Pull the two parenthesised flag lists out of the ffimport block.
mapfile -t FLAGS < <(
  awk '
    # skip the ffimport line itself: its quoted string is the source file, not a flag
    /^ffimport/       { in_block = 1; next }
    in_block && /^\)/ { closed++; if (closed == 2) exit; next }
    in_block          { if (match($0, /"([^"]+)"/)) print substr($0, RSTART+1, RLENGTH-2) }
  ' "$HUB"
)

if [ "${#FLAGS[@]}" -eq 0 ]; then
  echo "ERROR: no ffimport flags parsed out of $HUB" >&2
  exit 1
fi

CXX="${CXX:-clang++}"
OUT="$(mktemp -d)/libqarray-wrapper-ffimport.so"
trap 'rm -rf "$(dirname "$OUT")"' EXIT

echo "Compiler: $CXX"
echo "Flags parsed from $HUB (${#FLAGS[@]}):"
printf '  %s\n' "${FLAGS[@]}"
echo

set -x
"$CXX" -fPIC -shared -o "$OUT" qarray-wrapper.cpp "${FLAGS[@]}"
set +x

echo
echo "✓ qarray-wrapper.cpp compiles and links with hub.fal's ffimport flags alone"

# The DSL resolves each routine with dlsym, so every declared routine must be an
# exported, unmangled symbol.
# Read the symbol table ONCE. Do not pipe nm into `grep -q`: grep exits on the first
# match, nm takes SIGPIPE, and `set -o pipefail` then reports the whole pipeline as
# failed — turning a successful match into a bogus "missing symbol".
NM_OUTPUT="$(nm --dynamic --defined-only "$OUT")"

MISSING=()
for sym in CollectCurrentDeviceState CollectCurrentPlungerGates Ramp AnalyzeBlips \
           EndState RestartDevice MakeStabilityDiagram BuildVirtualizationMatrix; do
  grep -qE "[[:space:]]${sym}\$" <<<"$NM_OUTPUT" || MISSING+=("$sym")
done

if [ "${#MISSING[@]}" -ne 0 ]; then
  echo "✗ missing exported routines: ${MISSING[*]}" >&2
  exit 1
fi
echo "✓ all 8 ffimport routines exported"
