#!/bin/bash
# Sourced by the shared profile and its native status alias.
printf '\n'
if [[ ${1:-} == --summary ]]; then
    /opt/sai/bin/sai resources local --format table
else
    printf '\033[36mGPU NODE STATUS:\033[0m\n'
    gpu
    printf '\n\033[36mCPU NODE STATUS:\033[0m\n'
    cpu
fi
printf '\n\033[36mSTORAGE STATUS:\033[0m\n'
quota
