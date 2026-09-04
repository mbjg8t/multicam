#!/bin/bash

cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
exec python3 -m multicam.api.web.app
