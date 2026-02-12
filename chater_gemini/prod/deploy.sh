#! /bin/bash

set -e

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-gemini:0.3 --push .
kubectl rollout restart -n chater-gemini deployment chater-gemini