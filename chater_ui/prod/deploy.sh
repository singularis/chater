#! /bin/bash

set -e

# Always run from this folder so Dockerfile is found
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

IMAGE_TAG="0.5.4"
IMAGE="docker.io/singularis314/chater-ui:${IMAGE_TAG}"

docker buildx build --platform linux/amd64,linux/arm64 -t "${IMAGE}" --push ..

# Avoid DockerHub rate-limit loops: do not always pull if image is present on node
kubectl patch deployment chater-ui -n chater-ui --type='json' -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"}
]' || true

kubectl set image deployment/chater-ui -n chater-ui chater-ui="${IMAGE}"
kubectl rollout restart -n chater-ui deployment chater-ui
kubectl rollout status -n chater-ui deployment chater-ui --watch
for i in {1..10}; do
    sleep 5
    if kubectl get pods -n chater-ui | grep chater-ui | grep Running; then
        echo "Pod is running"
        break
    else
        kubectl get pods -n chater-ui | grep chater-ui
    fi
done