#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/chater-auth-dev:0.1 --push .
kubectl rollout restart -n chater-auth-dev deployment chater-auth-dev
