#!/bin/bash

# Exit on error
set -e

# Get the project root directory (one level up from dev/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Starting DEV deployment process..."

# Initialize an array to store deployed folders
deployed_folders=()

# Find all subdirectories with a dev/deploy.sh and run it
find "$PROJECT_DIR" -mindepth 1 -maxdepth 1 -type d | while read -r dir; do
    deploy_script="$dir/dev/deploy.sh"
    if [ -f "$deploy_script" ]; then
        folder_name="$(basename "$dir")"
        echo "Deploying DEV in $folder_name..."
        cd "$dir" && ./dev/deploy.sh
        cd "$PROJECT_DIR"
        deployed_folders+=("$folder_name")
    fi
done

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
