#! /bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t docker.io/singularis314/chater-gpt-operator:0.1 --push .
kubectl rollout restart -n chater-gpt deployment chater-gpt-operator