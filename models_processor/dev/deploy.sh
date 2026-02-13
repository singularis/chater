#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/models_processor-dev:0.1 --push .
kubectl rollout restart -n models-processor-dev deployment models-processor-dev
