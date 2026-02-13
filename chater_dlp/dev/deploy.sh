#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/chater-dlp-dev:0.3 --push .
kubectl rollout restart -n chater-dlp-dev deployment chater-dlp-dev
