#! /bin/bash

set -e

docker buildx build --platform linux/amd64 -t docker.io/singularis314/locust-chater-dev:0.1 --push .
kubectl rollout restart -n load-test-dev deployment locust-dev
