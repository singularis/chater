#! /bin/bash

docker build -t singularis314/chater-gemini-dev:0.3 .
docker push singularis314/chater-gemini-dev:0.3
kubectl rollout restart -n chater-gemini-dev deployment chater-gemini-dev
