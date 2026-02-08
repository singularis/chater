#! /bin/bash

docker build --platform linux/amd64 -t singularis314/chater-ui-dev:0.5 .
docker push singularis314/chater-ui-dev:0.5
kubectl rollout restart -n chater-ui-dev deployment chater-ui-dev
kubectl rollout status -n chater-ui-dev deployment chater-ui-dev --watch
for i in {1..10}; do
    sleep 5
    if kubectl get pods -n chater-ui-dev | grep chater-ui-dev | grep Running; then
        echo "Pod is running"
        break
    else
        kubectl get pods -n chater-ui-dev | grep chater-ui-dev
    fi
done
