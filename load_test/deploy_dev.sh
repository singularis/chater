#! /bin/bash

docker build -t singularis314/locust-chater-dev:0.1 .
docker push singularis314/locust-chater-dev:0.1
kubectl rollout restart -n load-test-dev deployment locust-dev
