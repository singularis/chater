#! /bin/bash

set -euo pipefail

IMAGE="singularis314/locust-chater:0.1"

# Always run from the project root so Dockerfile is found
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/${IMAGE} --push .

kubectl rollout restart -n load-test deployment locust