#! /bin/bash

docker build -t singularis314/chater-gpt:0.3 .
docker push singularis314/chater-gpt:0.3
kubectl rollout restart -n chater-gpt-operated deployment chater-gpt