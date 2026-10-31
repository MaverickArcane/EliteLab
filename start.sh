#!/usr/bin/env sh
# Run natively on Linux/macOS. Exit status 75 means "restart me" (Settings saved).
cd "$(dirname "$0")"
# Options with no command mean serve: the top-level parser has no --journals, --host or --port.
case "${1:-}" in -*) set -- serve "$@" ;; esac
while :; do
  python3 -m elitelab "$@"
  status=$?
  [ "$status" -eq 75 ] || exit "$status"
done
