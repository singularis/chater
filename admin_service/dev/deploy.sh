#! /bin/bash

docker build -t singularis314/admin-service-dev:0.1 .
docker push singularis314/admin-service-dev:0.1
kubectl rollout restart -n eater-dev deployment admin-service-dev
