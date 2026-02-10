#!/bin/bash

echo "Building admin service Docker image..."
docker build -t docker.io/singularis314/admin-service:0.1 .
docker push singularis314/admin-service:0.1
kubectl rollout restart -n eater deployment admin-service 