#! /bin/bash

set -euo pipefail

IMAGE="singularis314/locust-chater:0.1"

docker build -t ${IMAGE} .
docker push ${IMAGE}

kubectl rollout restart -n load-test deployment locust