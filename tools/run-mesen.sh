#!/usr/bin/env bash
# Host launch only. Python validates complete RESULT protocol.
set -uo pipefail
ROM="$1"
LUA="$2"
OUT="$3"
TIMEOUT="${4:-60}"
: "${MESEN:=Mesen}"
: "${XVFB:=xvfb-run}"
export SDL_AUDIODRIVER=dummy
if ! command -v "$MESEN" >/dev/null 2>&1 || [ ! -f "$ROM" ] || [ ! -f "$LUA" ]; then
    printf 'run-mesen: missing executable, ROM or driver\n' >&2
    exit 90
fi
if ! command -v "$XVFB" >/dev/null 2>&1; then
    printf 'run-mesen: xvfb-run required\n' >&2
    exit 93
fi
args=()
if [ "${RGQA_PORTABLE:-0}" = 1 ]; then args+=(--portable); fi
"$XVFB" -a -s '-screen 0 1280x720x24 -nolisten tcp' timeout "$TIMEOUT" "$MESEN" "${args[@]}" --testRunner --enableStdout "$ROM" "$LUA" >"$OUT" 2>&1
code=$?
if [ "$code" -ne 0 ] && [ "$code" -ne 1 ]; then exit "$code"; fi
# Both Mesen success and stop exit codes may be 1; never use them as verdict.
if ! grep -q '^RESULT:' "$OUT"; then exit 94; fi
if grep -q '^RESULT:.*"status":"pass"' "$OUT"; then exit 0; fi
if grep -q '^RESULT:.*"status":"fail"' "$OUT"; then exit 1; fi
exit 2
