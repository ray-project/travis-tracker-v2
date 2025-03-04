#!/bin/bash

uv pip compile --generate-hashes \
    --strip-extras requirements.txt -o requirements_compiled.txt
