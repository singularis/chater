#! /bin/bash

set -e

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/eater-init:0.1 --push .
kubectl rollout restart -n eater deployment eater