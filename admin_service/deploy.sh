#!/bin/bash

echo "Building admin service Docker image..."
docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/admin-service:0.1 --push .
kubectl rollout restart -n eater deployment admin-service 