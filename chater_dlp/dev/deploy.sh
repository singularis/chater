#! /bin/bash

docker build -t singularis314/chater-dlp-dev:0.3 .
docker push singularis314/chater-dlp-dev:0.3
kubectl rollout restart -n chater-dlp-dev deployment chater-dlp-dev
