#! /bin/bash

docker build -t singularis314/chater-auth:0.1 .
docker push singularis314/chater-auth:0.1
kubectl rollout restart -n chater-auth deployment chater-auth