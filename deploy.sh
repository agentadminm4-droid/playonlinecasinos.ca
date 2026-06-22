#!/bin/bash
# Sync source -> deploy dir (additive, idempotent), then commit + push.
# Use after running the generate_*.py scripts in ~/Desktop/playonlinecasinos/.

set -e

SOURCE="$HOME/Desktop/playonlinecasinos"
DEPLOY="$HOME/Desktop/playonlinecasinos-deploy"
TOKEN=$(cat /tmp/hermes_gh_token 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "ERROR: /tmp/hermes_gh_token not found. Run: python3 ~/.hermes/skills/github/github-auth/scripts/extract_gh_token.py" >&2
  exit 1
fi

# Pre-flight
[ ! -d "$SOURCE" ] && { echo "ERROR: source dir missing: $SOURCE" >&2; exit 1; }
[ ! -d "$DEPLOY/.git" ] && { echo "ERROR: deploy dir not a git repo: $DEPLOY" >&2; exit 1; }

# Sync (additive only, no --delete)
# Exclude the generator scripts and __pycache__
rsync -a \
  --exclude='generate_*.py' \
  --exclude='__pycache__' \
  --exclude='.DS_Store' \
  "$SOURCE/" "$DEPLOY/"

# Commit and push if anything changed
cd "$DEPLOY"
# Check both: untracked files (status) and modifications (diff)
if [ -z "$(git status --porcelain)" ]; then
  echo "No changes to deploy"
  exit 0
fi

git add -A
git commit -m "content: auto-deploy $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push "https://agentadminm4-droid:${TOKEN}@github.com/agentadminm4-droid/playonlinecasinos.ca.git" main

echo "Deployed successfully"
