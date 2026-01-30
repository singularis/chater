#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-ui:0.5 --push .
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