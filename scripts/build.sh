#!/usr/bin/env sh
set -eu
# Vercel runs this from the repository root. Dependencies remain outside static output.
build_dependencies=$(mktemp -d /tmp/mr-synapse-build.XXXXXX)
trap 'rm -rf "$build_dependencies"' EXIT
python3 -m pip install --disable-pip-version-check --target "$build_dependencies" -r automation/requirements.txt
PYTHONPATH="$build_dependencies${PYTHONPATH:+:$PYTHONPATH}" python3 -m automation.ingest
