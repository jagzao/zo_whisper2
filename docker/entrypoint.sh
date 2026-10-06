#!/bin/sh
# PLAN-ZMI-DKR-001 — container entrypoint (file from WP-04; behavior contract
# from WP-05). Prepares writable data directories, seeds projects.json from
# the portable example ONLY when absent (never overwrites mounted state),
# then execs the final command so SIGTERM reaches Python directly.
set -eu

: "${ZMI_DATA_ROOT:=/data}"
: "${ZMI_PROJECTS_EXAMPLE:=/app/projects.json.example}"

for dir in audio Videos Video_compress CarpetaTranscripciones logs exports; do
    mkdir -p "$ZMI_DATA_ROOT/$dir"
done

# Seed only when the file does not exist yet: a mounted volume with previous
# state (or an owner-edited projects.json) is authoritative.
if [ ! -f "$ZMI_DATA_ROOT/projects.json" ] && [ -f "$ZMI_PROJECTS_EXAMPLE" ]; then
    cp "$ZMI_PROJECTS_EXAMPLE" "$ZMI_DATA_ROOT/projects.json"
fi

exec "$@"
