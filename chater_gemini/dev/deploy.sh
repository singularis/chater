#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/chater-gemini-dev:0.3 --push .
kubectl rollout restart -n chater-gemini-dev deployment chater-gemini-dev
