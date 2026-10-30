#!/usr/bin/env sh
# Run natively on Linux/macOS. Exit status 75 means "restart me" (Settings saved).
cd "$(dirname "$0")"
while :; do
  python3 -m elitelab "$@"
  status=$?
  [ "$status" -eq 75 ] || exit "$status"
done
