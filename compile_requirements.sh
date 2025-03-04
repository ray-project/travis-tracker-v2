#!/bin/bash

set -euo pipefail

uv pip compile --generate-hashes \
    --strip-extras requirements.txt -o requirements_compiled.txt
