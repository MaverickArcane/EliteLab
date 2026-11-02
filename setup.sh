#!/usr/bin/env sh
# First-run setup from an extracted source archive; no packages are installed.
cd "$(dirname "$0")" || exit 1
for lab_candidate in "${ELITELAB_PYTHON:-python3}" python3 python; do
  if command -v "$lab_candidate" >/dev/null 2>&1 &&
     "$lab_candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    ELITELAB_PYTHON=$(command -v "$lab_candidate")
    export ELITELAB_PYTHON
    exec sh ./start.sh serve --open-browser --setup "$@"
  fi
done
printf '%s\n' 'Python 3.10 or newer was not found.' >&2
printf '%s\n' 'Install or upgrade Python using your Linux package manager or python.org on macOS, then run setup.sh again.' >&2
exit 1
