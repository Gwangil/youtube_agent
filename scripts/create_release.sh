#!/bin/bash

# YouTube Agent Release Script
# Usage: ./scripts/create_release.sh [major|minor|patch]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get release type
RELEASE_TYPE=${1:-patch}

# Check if we're on main branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo -e "${RED}Error: Must be on main branch to create release${NC}"
    echo "Current branch: $CURRENT_BRANCH"
    exit 1
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Error: Uncommitted changes detected${NC}"
    git status --short
    exit 1
fi

# Get current version
if [ -f VERSION ]; then
    CURRENT_VERSION=$(cat VERSION)
else
    CURRENT_VERSION="0.0.0"
fi

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Calculate new version
case $RELEASE_TYPE in
    major)
        NEW_VERSION="$((MAJOR + 1)).0.0"
        ;;
    minor)
        NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
        ;;
    patch)
        NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
        ;;
    *)
        echo -e "${RED}Error: Invalid release type. Use major, minor, or patch${NC}"
        exit 1
        ;;
esac

echo -e "${GREEN}Creating release: v$NEW_VERSION${NC}"
echo "Current version: $CURRENT_VERSION"
echo "New version: $NEW_VERSION"
echo ""

# Confirm release
read -p "Continue with release? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Release cancelled"
    exit 0
fi

# Pull latest changes
echo -e "${YELLOW}Pulling latest changes...${NC}"
git pull origin main

# Create release branch
RELEASE_BRANCH="release/v$NEW_VERSION"
echo -e "${YELLOW}Creating release branch: $RELEASE_BRANCH${NC}"
git checkout -b "$RELEASE_BRANCH"

# Update VERSION file
echo "$NEW_VERSION" > VERSION
echo -e "${GREEN}Updated VERSION file${NC}"

# Update CHANGELOG.md placeholder
echo -e "${YELLOW}Please update CHANGELOG.md with release notes${NC}"
echo "Opening CHANGELOG.md in default editor..."

# Stage changes
git add VERSION

# Commit
git commit -m "chore: bump version to $NEW_VERSION"

# Create tag
echo -e "${YELLOW}Creating tag v$NEW_VERSION${NC}"
read -p "Enter brief release description: " RELEASE_DESC

git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION

$RELEASE_DESC

See CHANGELOG.md for details."

# Show summary
echo ""
echo -e "${GREEN}Release created successfully!${NC}"
echo "Branch: $RELEASE_BRANCH"
echo "Tag: v$NEW_VERSION"
echo ""
echo "Next steps:"
echo "1. Review and update CHANGELOG.md if needed"
echo "2. Push branch: git push origin $RELEASE_BRANCH"
echo "3. Push tag: git push origin v$NEW_VERSION"
echo "4. Create GitHub release from tag"
echo "5. Merge release branch to main when ready"

# Optional: Auto-push
read -p "Push branch and tag now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git push origin "$RELEASE_BRANCH"
    git push origin "v$NEW_VERSION"
    echo -e "${GREEN}Pushed to remote!${NC}"
    echo "GitHub release URL: https://github.com/[your-repo]/releases/new?tag=v$NEW_VERSION"
fi