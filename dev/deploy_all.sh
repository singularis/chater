#!/bin/bash

# Exit on error
set -e

# Get the project root directory (one level up from dev/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting DEV deployment process..."

# Initialize an array to store deployed folders
deployed_folders=()

# Find all subdirectories with a dev/deploy.sh and run it.
# Use process substitution to avoid subshell (so deployed_folders persists).
while IFS= read -r -d '' dir; do
    deploy_script="$dir/dev/deploy.sh"
    if [ -f "$deploy_script" ]; then
        folder_name="$(basename "$dir")"
        echo "Deploying DEV in $folder_name..."
        cd "$dir" && bash -e ./dev/deploy.sh
        cd "$PROJECT_DIR"
        deployed_folders+=("$folder_name")
    fi
done < <(find "$PROJECT_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

echo -e "\nDEV Deployment Summary:"
echo "------------------------"
if [ ${#deployed_folders[@]} -eq 0 ]; then
    echo "No folders were deployed."
else
    echo "Successfully deployed DEV folders:"
    for folder in "${deployed_folders[@]}"; do
        echo "- $folder"
    done
fi
