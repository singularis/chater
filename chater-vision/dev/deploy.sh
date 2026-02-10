#! /bin/bash

docker build -t docker.io/singularis314/chater-vision-dev:0.1 .
docker push docker.io/singularis314/chater-vision-dev:0.1
kubectl rollout restart -n chater-vision-dev deployment chater-vision-dev
