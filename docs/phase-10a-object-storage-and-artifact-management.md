# Phase 10A — Object Storage & Artifact Management

## 1. Objective & Architecture Overview

Phase 10A establishes a provider-independent Object Storage and Artifact Management subsystem for Job Copilot. Durable application artifacts (such as tailored resume PDFs, cover letters, application packages, question/answer sets, validation reports, Playwright browser screenshots, and session traces) are decoupled from the local filesystem.

Binary file contents are persisted in object storage (local filesystem in development, or S3-compatible cloud storage in deployment), while structured metadata, SHA-256 checksums, and application/job references are persisted in PostgreSQL.

```
+-------------------------------------------------------------------------+
|                               Job Copilot                               |
|                                                                         |
|   +-----------------------------------------------------------------+   |
|   |         Application Layer (Phase 6 / 7 / 8 / 9 Services)        |   |
|   +-----------------------------------------------------------------+   |
|                                    |                                    |
|                                    v                                    |
|   +-----------------------------------------------------------------+   |
|   |                        ArtifactService                          |   |
|   |   - SHA-256 Hashing & Size Enforcement                          |   |
|   |   - Collision-Resistant Key Builder                             |   |
|   |   - Idempotency & Tamper Detection                              |   |
|   |   - Soft & Hard Deletion Lifecycle                              |   |
|   +-----------------------------------------------------------------+   |
|                 /                                     \                 |
|    Metadata & References (SQL)               Binary Payloads (Bytes)    |
|               /                                         \               |
|              v                                           v              |
|   +---------------------+                     +---------------------+   |
|   |     PostgreSQL      |                     |    ArtifactStore    |   |
|   |  (`artifacts` table)|                     |     (Interface)     |   |
|   +---------------------+                     +---------------------+   |
|                                                      /           \      |
|                                                     v             v     |
|                                           +-------------+  +------------+
|                                           | Local Store |  |  S3 Store  |
|                                           | (data/art/) |  | (S3/R2/Min)|
|                                           +-------------+  +------------+
+-------------------------------------------------------------------------+
```

---

## 2. Storage Abstraction Layer

The application interacts strictly with `ArtifactService` and the `ArtifactStore` abstract base interface, never with provider-specific SDKs directly:

### Abstract Interface: `ArtifactStore`
- `put(storage_key: str, data: bytes, content_type: str) -> Tuple[int, str]`: Writes binary data and returns `(size_bytes, sha256)`.
- `get(storage_key: str) -> bytes`: Reads raw binary data.
- `delete(storage_key: str) -> bool`: Deletes binary object.
- `exists(storage_key: str) -> bool`: Checks object presence.
- `presigned_url(storage_key: str, expires_in_seconds: int) -> Optional[str]`: Generates a time-limited GET URL for downloads.
- `list_keys(prefix: str) -> List[str]`: Lists object keys matching prefix.

### Concrete Implementations
1. **`LocalArtifactStore`**: Stores objects under `data/artifacts/`. Enforces containment within `base_dir` to prevent directory traversal attacks (`../`, symlinks).
2. **`S3ArtifactStore`**: S3-compatible client supporting AWS S3, Cloudflare R2, MinIO, Wasabi, and Backblaze B2. Configurable with custom endpoints and regions.

---

## 3. Database Schema & Alembic Migration

Alembic migration revision `002_artifacts_storage` introduces the `artifacts` table:

```sql
CREATE TABLE artifacts (
    id SERIAL PRIMARY KEY,
    artifact_id VARCHAR(255) NOT NULL UNIQUE,
    application_id VARCHAR(255),
    job_id VARCHAR(255),
    artifact_type VARCHAR(50) NOT NULL,
    storage_provider VARCHAR(50) NOT NULL DEFAULT 'local',
    storage_key VARCHAR(1024) NOT NULL,
    content_type VARCHAR(100) NOT NULL DEFAULT 'application/octet-stream',
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    original_filename VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    metadata_json JSON NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Controlled Artifact Types
- `TAILORED_RESUME_PDF`
- `TAILORED_RESUME_TEX`
- `COVER_LETTER`
- `APPLICATION_PACKAGE`
- `QUESTIONS`
- `ANSWERS`
- `VALIDATION_REPORT`
- `SCREENSHOT`
- `PLAYWRIGHT_TRACE`
- `BROWSER_DIAGNOSTIC`
- `OTHER`

---

## 4. Key Structure & Traversal Defense

Storage keys are generated deterministically using [key_builder.py](file:///Users/Hp/Apply-Agent/src/job_copilot/storage/key_builder.py):

```
applications/{application_id or job_id}/{artifact_type}/{artifact_id}/{sanitized_filename}
```

### Security Defenses
- Rejects absolute paths (`/etc/passwd`, `C:\...`).
- Rejects null bytes (`\x00`).
- Replaces path traversal tokens (`../`, `..\\`) and illegal characters with safe underscores.
- Prevents collisions by incorporating unique `artifact_id` and controlled `artifact_type`.

---

## 5. Local Development vs. Cloud Deployment

### Local Development (Default)
In `.env` or development environments:
```bash
ARTIFACT_STORAGE_PROVIDER=local
ARTIFACT_STORAGE_DIR=./data/artifacts
```
Requires zero cloud credentials. All files are organized and inspected in `./data/artifacts/`.

### Cloud Deployment (S3 / Cloudflare R2 / MinIO)
In Render or cloud runtime settings:
```bash
ARTIFACT_STORAGE_PROVIDER=s3
ARTIFACT_STORAGE_BUCKET=job-copilot-artifacts-prod
ARTIFACT_STORAGE_REGION=us-east-1
ARTIFACT_STORAGE_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com  # Optional (for R2/MinIO)
ARTIFACT_STORAGE_ACCESS_KEY=<configured-in-render-secrets>
ARTIFACT_STORAGE_SECRET_KEY=<configured-in-render-secrets>
ARTIFACT_MAX_SIZE_BYTES=52428800  # 50MB limit
```

---

## 6. Integrity & Tamper Detection

1. **Upload Verification**: Every `store_artifact()` computes SHA-256 before writing and verifies that the store returns matching size and checksum.
2. **Read Verification**: `get_artifact()` verifies that retrieved bytes match the recorded `sha256` hash in PostgreSQL. If corrupted, an `IOError` is raised.
3. **Idempotent Re-upload**: If the same artifact is stored again with identical contents, the existing record is returned without duplicating storage or modifying IDs.

---

## 7. Artifact Lifecycle & Cleanup Semantics

Artifacts are categorized into three states:
- `ACTIVE`: Available for download, review, and application packages.
- `ARCHIVED`: Retained for historical auditing and outcome analytics (e.g. past job applications).
- `DELETED`: Soft-deleted (metadata marked `DELETED`, preserved for audit unless hard deletion is explicitly triggered).

Hard deletion (`delete_artifact(artifact_id, hard_delete=True)`) permanently purges the object from the storage backend and removes the database metadata record.

---

## 8. Non-Destructive Filesystem Migration

The utility [migrator.py](file:///Users/Hp/Apply-Agent/src/job_copilot/storage/migrator.py) scans legacy application directories:
```python
from job_copilot.storage.migrator import migrate_existing_filesystem_artifacts
counts = migrate_existing_filesystem_artifacts()
```
- Discovers existing `package.json`, `cover_letter.md`, `validation.json`, `resume.pdf`, and screenshots.
- Calculates SHA-256 and registers them into object storage and PostgreSQL.
- Leaves original filesystem files untouched.

---

## 9. Future Compatibility with Phase 10B (Cloud Browser Worker)

When Phase 10B introduces remote headless browser runners:
1. Remote Playwright instances upload screenshots and traces directly via `ArtifactService.store_artifact()`.
2. The core API references browser artifacts via `artifact_id` without needing shared filesystem mounts.
3. Time-limited presigned URLs provide secure preview links in API responses.
