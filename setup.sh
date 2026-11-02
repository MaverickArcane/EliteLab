#!/usr/bin/env sh
# First-run setup from an extracted source archive; no packages are installed.
cd "$(dirname "$0")" || exit 1
exec /bin/sh ./start.sh serve --open-browser --setup "$@"
