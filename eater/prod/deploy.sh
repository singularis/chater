#! /bin/bash

set -e

# Always run from the project root so Dockerfile is found
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/eater:0.1 --push .
kubectl rollout restart -n eater deployment eater