#! /bin/bash

docker build -t singularis314/chater-auth-dev:0.1 .
docker push singularis314/chater-auth-dev:0.1
kubectl rollout restart -n chater-auth-dev deployment chater-auth-dev
