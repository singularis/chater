#! /bin/bash

# For mcpo-proxy, there's no custom build - it uses the upstream image
# Just restart the deployment
kubectl rollout restart -n eater-dev deployment mcpo-postgres-dev
