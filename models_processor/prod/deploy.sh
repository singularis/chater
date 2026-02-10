#! /bin/bash

docker build -t singularis314/models_processor:0.1 .
docker push singularis314/models_processor:0.1
kubectl rollout restart -n models-processor deployment models-processor