#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/models_processor:0.1 --push .
kubectl rollout restart -n models-processor deployment models-processor