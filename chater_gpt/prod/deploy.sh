#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-gpt:0.3 --push .
kubectl rollout restart -n chater-gpt-operated deployment chater-gpt