#! /bin/bash

docker build -t singularis314/chater-gemini:0.3 .
docker push singularis314/chater-gemini:0.3
kubectl rollout restart -n chater-gemini deployment chater-gemini