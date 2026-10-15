#!/usr/bin/env sh
set -eu

# Removes private candidate truth from Git's index without deleting local files.
# Run this once from the repository root after updating .gitignore.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "Run this script from inside the job-copilot Git repository." >&2
  exit 1
fi

git rm --cached --ignore-unmatch \
  data/candidate/master_profile.yaml \
  data/candidate/evidence.yaml \
  data/candidate/preferences.yaml \
  data/candidate/review_required.yaml
printf '%s\n' "Private candidate truth has been removed from Git's index (local files were preserved)."
printf '%s\n' "Review git status and commit this change to remove private candidate data from future repository revisions."
