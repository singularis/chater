#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/chater-vision-dev:0.1 --push .
kubectl rollout restart -n chater-vision-dev deployment chater-vision-dev
