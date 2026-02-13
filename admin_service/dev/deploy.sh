#! /bin/bash

set -e

echo "Building admin service DEV Docker image..."
docker buildx build --platform linux/amd64 -t docker.io/singularis314/admin-service-dev:0.1 --push .
kubectl rollout restart -n eater-dev deployment admin-service-dev
