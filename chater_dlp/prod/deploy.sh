#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-dlp:0.3 --push .
kubectl rollout restart -n chater-dlp deployment chater-dlp