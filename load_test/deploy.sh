#! /bin/bash

set -euo pipefail

IMAGE="singularis314/locust-chater:0.1"

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/${IMAGE} --push .

kubectl rollout restart -n load-test deployment locust