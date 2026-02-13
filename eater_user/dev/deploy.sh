#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/eater_users-dev:0.1 --push .
kubectl rollout restart -n eater-dev deployment eater-users-dev
