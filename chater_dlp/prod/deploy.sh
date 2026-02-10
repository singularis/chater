#! /bin/bash

docker build -t singularis314/chater-dlp:0.3 .
docker push singularis314/chater-dlp:0.3
kubectl rollout restart -n chater-dlp deployment chater-dlp