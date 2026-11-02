#!/usr/bin/env sh
# Run natively on Linux/macOS. Exit status 75 means "restart me" (Settings saved).
cd "$(dirname "$0")"
# Options with no command mean serve: the top-level parser has no --journals, --host or --port.
case "${1:-}" in -*) set -- serve "$@" ;; esac
first=1
while :; do
  python3 -m elitelab "$@"
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
