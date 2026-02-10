#! /bin/bash

docker build -t docker.io/singularis314/chater-gpt-operator-dev:0.1 operator/
docker push docker.io/singularis314/chater-gpt-operator-dev:0.1
kubectl rollout restart -n chater-gpt-dev deployment chater-gpt-operator-dev
