#!/usr/bin/env sh
# Run natively on Linux/macOS. Exit status 75 means "restart me" (Settings saved).
cd "$(dirname "$0")" || exit 1
lab_python=
for lab_candidate in "${ELITELAB_PYTHON:-python3}" python3 python; do
  if command -v "$lab_candidate" >/dev/null 2>&1 &&
     "$lab_candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    lab_python=$(command -v "$lab_candidate")
    break
  fi
done
if [ -z "$lab_python" ]; then
  printf '%s\n' 'Python 3.10 or newer was not found.' >&2
  printf '%s\n' 'Install or upgrade Python using your Linux package manager or python.org on macOS, then run setup.sh again.' >&2
  exit 1
fi
# Options with no command mean serve: the top-level parser has no --journals, --host or --port.
case "${1:-}" in -*) set -- serve "$@" ;; esac
first=1
while :; do
  "$lab_python" -m elitelab "$@"
  status=$?
  [ "$status" -eq 75 ] || exit "$status"
  if [ -n "$first" ]; then
    # a restart keeps the tab the setup page is waiting in: drop --open-browser, keep every other argument as given
    first=
    for arg do
      shift
      [ "$arg" = "--open-browser" ] || set -- "$@" "$arg"
    done
  fi
done
