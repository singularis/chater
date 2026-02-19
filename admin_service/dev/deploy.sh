#! /bin/bash

set -e

echo "Building admin service DEV Docker image..."
# Always run from the project root so Dockerfile is found
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

docker buildx build --platform linux/amd64 -t docker.io/singularis314/admin-service-dev:0.1 --push .
kubectl rollout restart -n eater-dev deployment admin-service-dev
