#!/bin/bash

SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$SCRIPT_PATH")" || exit 1

source .venv/bin/activate || exit 1
exec python3 -m multicam.api.web.app
