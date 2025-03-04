#!/bin/bash

set -euo pipefail

uv pip compile --generate-hashes -p 3.9 \
    --strip-extras requirements.txt -o requirements_compiled.txt
