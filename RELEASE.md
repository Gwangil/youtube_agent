# Release Process Guide

## Version Numbering

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR.MINOR.PATCH** (e.g., 1.0.0)
- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

## Release Branches

### Branch Strategy
- `main`: Development branch (latest changes)
- `release/vX.Y.Z`: Release preparation branches
- `stable`: Production-ready code (optional)
- Tags: `vX.Y.Z` for specific releases

## Release Checklist

### Pre-release
- [ ] All tests passing
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] VERSION file updated
- [ ] No critical issues in monitoring

### Release Steps

#### 1. Create Release Branch
```bash
# Create release branch from main
git checkout main
git pull origin main
git checkout -b release/v1.0.0

# Update version files
echo "1.0.0" > VERSION

# Commit version bump
git add VERSION CHANGELOG.md
git commit -m "chore: bump version to 1.0.0"
```

#### 2. Final Testing
```bash
# Run all tests
./scripts/test_all.sh

# Test deployment
./start.sh

# Verify services
docker-compose ps
```

#### 3. Create Release Tag
```bash
# Create annotated tag
git tag -a v1.0.0 -m "Release version 1.0.0

Major Features:
- YouTube content processing pipeline
- GPU/CPU dual mode support
- RAG-based Q&A system
- Admin dashboard
- Data integrity management

See CHANGELOG.md for full details."

# Push branch and tag
git push origin release/v1.0.0
git push origin v1.0.0
```

#### 4. GitHub Release
1. Go to GitHub repository
2. Click "Releases" → "Create a new release"
3. Choose tag: `v1.0.0`
4. Release title: `v1.0.0 - Initial Major Release`
5. Copy release notes from CHANGELOG.md
6. Attach any binary artifacts if needed
7. Publish release

#### 5. Merge to Stable (Optional)
```bash
# If using stable branch
git checkout stable
git merge release/v1.0.0
git push origin stable
```

#### 6. Update Main Branch
```bash
# Merge release changes back to main
git checkout main
git merge release/v1.0.0
git push origin main
```

## Hotfix Process

For critical fixes on released versions:

```bash
# Create hotfix from tag
git checkout -b hotfix/v1.0.1 v1.0.0

# Make fixes
# Update VERSION to 1.0.1
# Update CHANGELOG.md

git commit -m "fix: critical bug description"

# Tag hotfix
git tag -a v1.0.1 -m "Hotfix version 1.0.1"

# Push hotfix
git push origin hotfix/v1.0.1
git push origin v1.0.1

# Merge back to main
git checkout main
git merge hotfix/v1.0.1
```

## Docker Image Tagging

### Build and Tag Images
```bash
# Build with version tag
docker build -t youtube-agent:1.0.0 .
docker tag youtube-agent:1.0.0 youtube-agent:latest

# If using registry
docker tag youtube-agent:1.0.0 your-registry/youtube-agent:1.0.0
docker push your-registry/youtube-agent:1.0.0
docker push your-registry/youtube-agent:latest
```

## Rollback Process

If issues are found after release:

```bash
# Rollback to previous version
git checkout v0.9.0  # Previous stable version

# Deploy previous version
./start.sh

# Or using Docker
docker-compose down
docker run youtube-agent:0.9.0
```

## Post-release

### Tasks
- [ ] Update documentation site
- [ ] Notify team/users
- [ ] Monitor for issues
- [ ] Plan next release

### Communication Template
```
Subject: YouTube Agent v1.0.0 Released

We're excited to announce the release of YouTube Agent v1.0.0!

Key Features:
- GPU-accelerated STT processing
- Intelligent content chunking
- Real-time vector synchronization
- Comprehensive admin dashboard

Full changelog: [link]
Documentation: [link]
```

## Version File Locations

Files to update when releasing:
- `/VERSION` - Version number
- `/CHANGELOG.md` - Release notes
- `/package.json` (if applicable)
- `/services/*/requirements.txt` - Python dependencies
- Docker image tags in docker-compose files

## Automated Release (Future)

Consider implementing CI/CD:
```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags:
      - 'v*'
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build and push Docker images
      - name: Create GitHub Release
```