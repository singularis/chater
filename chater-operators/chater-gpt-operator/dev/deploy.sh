#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/chater-gpt-operator-dev:0.1 --push operator/
kubectl rollout restart -n chater-gpt-dev deployment chater-gpt-operator-dev
