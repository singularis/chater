#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/eater-dev:0.1 --push .
kubectl rollout restart -n eater-dev deployment eater-dev
