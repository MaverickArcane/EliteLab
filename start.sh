#!/usr/bin/env sh
# Run natively on Linux/macOS. Point --journals at your journal folder if it is not auto-detected.
cd "$(dirname "$0")"
exec python3 -m elitelab "$@"
