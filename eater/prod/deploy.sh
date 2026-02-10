#! /bin/bash

docker build -t singularis314/eater:0.1 .
docker push singularis314/eater:0.1
kubectl rollout restart -n eater deployment eater