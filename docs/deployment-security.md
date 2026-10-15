# Candidate Data and Deployment Security

## Local development

Candidate truth files (`master_profile.yaml`, `evidence.yaml`, `preferences.yaml`, and `review_required.yaml`) contain private personal information. They are ignored by Git and are not copied into the Docker image. Keep your real files in `data/candidate/` for local development. The tracked `master_profile.example.yaml` is synthetic and is not a substitute for your verified candidate profile.

If these files were already tracked in Git, `.gitignore` alone will not untrack them. From the repository root, run:

```sh
./scripts/untrack_private_candidate_data.sh
```

Then inspect `git status` and commit the removal. If private candidate data was previously pushed to a remote, removing it from the latest commit does not erase older Git history; rotate any credentials accidentally committed and consider repository-history cleanup.

## Docker Compose

Copy `.env.example` to `.env`, replace all placeholder values with unique secrets, and ensure the `DATABASE_URL` password matches `POSTGRES_PASSWORD`. Never commit `.env`. Candidate files remain in the local `data/candidate/` directory and are mounted into the container through `./data:/app/data`. The dashboard requires `DASHBOARD_API_KEY`; enter that key in the dashboard's API-key control.

## Render deployment

The Docker image deliberately does not contain candidate truth. In the Render service dashboard, add these four **Secret Files** with their exact filenames and contents from your private local candidate directory:

- `master_profile.yaml`
- `evidence.yaml`
- `preferences.yaml`
- `review_required.yaml`

Render mounts Secret Files under `/etc/secrets`, which is configured as `CANDIDATE_DATA_DIR`. Set `CANDIDATE_PROFILE_PATH` to `/etc/secrets/master_profile.yaml` (the Blueprint already declares this path). The Blueprint generates a `DASHBOARD_API_KEY`; retrieve it from the Render environment settings and enter it in the dashboard UI. Never put the key or candidate YAML contents in `render.yaml`, source code, or a public build artifact.

If a required file is not present, candidate-specific operations will be unable to load it; do not replace missing candidate truth with fabricated data.
