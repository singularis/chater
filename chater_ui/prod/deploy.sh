#! /bin/bash

set -e

# Always run from this folder so Dockerfile is found
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

IMAGE_TAG="0.5.10"

# Auto-increment the image tag
SCRIPT_FILE=$(readlink -f "$0")
if [[ "$IMAGE_TAG" =~ ^([0-9]+\.[0-9]+)\.([0-9]+)$ ]]; then
    PREFIX="${BASH_REMATCH[1]}"
    PATCH="${BASH_REMATCH[2]}"
    NEW_PATCH=$((PATCH + 1))
    NEW_TAG="${PREFIX}.${NEW_PATCH}"
    
    # Update the script file itself with the new tag
    sed -i "s/^IMAGE_TAG=\"$IMAGE_TAG\"/IMAGE_TAG=\"$NEW_TAG\"/" "$SCRIPT_FILE"
    IMAGE_TAG="$NEW_TAG"
    echo "Auto-incremented image tag to $IMAGE_TAG"
fi

IMAGE="docker.io/singularis314/chater-ui:${IMAGE_TAG}"

docker buildx build --platform linux/amd64,linux/arm64 -t "${IMAGE}" --push ..

# Always pull image rather than re-using local cached versions
kubectl patch deployment chater-ui -n chater-ui --type='json' -p='[
  {"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Always"}
]' || true

kubectl set image deployment/chater-ui -n chater-ui chater-ui="${IMAGE}"
kubectl rollout restart -n chater-ui deployment chater-ui
kubectl rollout status -n chater-ui deployment chater-ui --watch
for i in {1..10}; do
    sleep 5
    if kubectl get pods -n chater-ui | grep chater-ui | grep Running; then
        echo "Pod is running"
        break
    fi
done

# Clean up older image tags on Docker Hub (N-2)
echo "Cleaning up older image tags on Docker Hub..."
if [[ "$IMAGE_TAG" =~ ^([0-9]+\.[0-9]+)\.([0-9]+)$ ]]; then
    PREFIX="${BASH_REMATCH[1]}"
    PATCH="${BASH_REMATCH[2]}"
    if [ "$PATCH" -ge 2 ]; then
        OLD_TAG="${PREFIX}.$((PATCH - 2))"
        echo "Attempting to delete tag $OLD_TAG..."
        
        AUTH_BASE64=$(cat ~/.docker/config.json 2>/dev/null | grep -A1 '"https://index.docker.io/v1/"' | grep '"auth"' | cut -d'"' -f4)
        if [ -z "$AUTH_BASE64" ]; then
            AUTH_BASE64=$(cat ~/.docker/config.json 2>/dev/null | grep '"auth":' | head -n1 | cut -d'"' -f4)
        fi
        
        if [ ! -z "$AUTH_BASE64" ]; then
            AUTH_DECODED=$(echo "$AUTH_BASE64" | base64 -d)
            UNAME=$(echo "$AUTH_DECODED" | cut -d: -f1)
            UPASS=$(echo "$AUTH_DECODED" | cut -d: -f2)
            REPO=$(echo "$IMAGE" | awk -F'/' '{print $3}' | awk -F':' '{print $1}')
            
            TOKEN=$(curl -s -H "Content-Type: application/json" \
              -X POST -d "{\"username\": \"$UNAME\", \"password\": \"$UPASS\"}" \
              https://hub.docker.com/v2/users/login/ | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
              
            if [ ! -z "$TOKEN" ]; then
                curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" -X DELETE \
                     -H "Authorization: JWT ${TOKEN}" \
                     https://hub.docker.com/v2/repositories/${UNAME}/${REPO}/tags/${OLD_TAG}/
                echo "Successfully requested deletion of ${REPO}:${OLD_TAG}"
            fi
        fi
    fi
fi