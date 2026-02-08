#! /bin/bash

docker build -t singularis314/eater_users-dev:0.1 .
docker push singularis314/eater_users-dev:0.1
kubectl rollout restart -n eater-dev deployment eater-users-dev
