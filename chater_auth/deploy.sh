#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-auth:0.1 --push .
kubectl rollout restart -n chater-auth deployment chater-auth