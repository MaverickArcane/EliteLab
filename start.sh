#!/usr/bin/env sh
# Run natively on Linux/macOS. Point --journals at your journal folder if it is not auto-detected.
cd "$(dirname "$0")"
while :; do
  python3 -m elitelab "$@"
  status=$?
  [ "$status" -eq 75 ] || exit "$status"
done
