#!/bin/bash

# Exit on error
set -e

# Get the project root directory (one level up from prod/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting deployment process..."

# Initialize an array to store deployed folders
deployed_folders=()

# Find all subdirectories with a prod/deploy.sh and run it.
# Use -print0 to safely handle spaces in folder names.
while IFS= read -r -d '' dir; do
    folder_name="$(basename "$dir")"
    deploy_script="$dir/prod/deploy.sh"
    if [ -f "$deploy_script" ]; then
        echo "Deploying in $folder_name..."
        # Enforce "exit on error" inside deploy scripts too (many don't set -e).
        cd "$dir" && bash -e ./prod/deploy.sh
        cd "$PROJECT_DIR"
        deployed_folders+=("$folder_name")
    fi
done < <(find "$PROJECT_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

echo -e "\nDeployment Summary:"
echo "------------------"
if [ ${#deployed_folders[@]} -eq 0 ]; then
    echo "No folders were deployed."
else
    echo "Successfully deployed folders:"
    for folder in "${deployed_folders[@]}"; do
        echo "- $folder"
    done
fi 