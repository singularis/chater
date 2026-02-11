#! /bin/bash

docker build -t singularis314/chater-vision:0.1 .
docker push singularis314/chater-vision:0.1
kubectl rollout restart -n chater-vision deployment chater-vision