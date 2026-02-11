#! /bin/bash

docker build -t docker.io/singularis314/eater-init-dev:0.1 .
docker push docker.io/singularis314/eater-init-dev:0.1
kubectl rollout restart -n eater-dev deployment eater-dev
