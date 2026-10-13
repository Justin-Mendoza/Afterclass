# Day 17 — Management APIs

The API now connects the future frontend to collections, original documents,
permissions, and durable ingestion jobs. Uploading saves work; the existing
worker parses, chunks, embeds, and indexes it. Generation and citations belong
to Day 18.

```text
Browser or curl + demo identity
              |
        /v1 management API
              |
      current database permissions
              |
 upload -> original file + document + job + retry receipt
              |                 PostgreSQL commit
              v
          Redis dispatch -> existing ingestion worker -> OpenSearch
              |
       job-status polling
```

Identity selection remains simulated with `X-Demo-User-ID`; permissions are
checked against PostgreSQL on every request. The browser cannot choose a wider
scope than its selected identity allows.

## Permissions

| Access | Capability |
|---|---|
| `read` | Collection/document inspection, original download, job inspection |
| `write` | Read capabilities plus document upload and deletion |
| `manage` | Write capabilities plus collection editing and collection grants |
| Workspace owner/admin | All capabilities, including collection creation |

Grants target existing membership IDs in the same workspace. Owners/admins
retain access through their workspace role regardless of collection grants.
Membership creation and role changes are outside this ticket. A collection
manager can use `/members?collection_id=...` for the permission picker; an
owner/admin can list workspace members without selecting a collection.

## Routes and contracts

All management routes start with `/v1/workspaces/{workspace_id}`.

| Method | Suffix | Outcome |
|---|---|---|
| GET, POST | `/collections` | List authorized collections; create a collection |
| GET, PATCH | `/collections/{collection_id}` | Inspect; edit name and description |
| GET | `/members` | List existing members for the permission picker |
| GET | `/collections/{collection_id}/grants` | Inspect collection grants |
| PUT, DELETE | `/collections/{collection_id}/grants/{membership_id}` | Set or revoke a grant |
| GET, POST | `/collections/{collection_id}/documents` | List documents; upload one file |
| GET, DELETE | `/documents/{document_id}` | Inspect metadata; delete content |
| GET | `/documents/{document_id}/content` | Download an authorized original |
| GET | `/jobs/{job_id}` | Inspect durable status, stage, and safe failure details |

List endpoints return arrays, defaulting to `limit=50&offset=0`; limit must be
1–100. Ordering includes an ID tie-breaker. Request the next offset when a page
is full. Pagination is not a snapshot across concurrent changes.

Collection creation requires a name and lowercase hyphenated slug. Slugs are
unique within a workspace and remain fixed; PATCH requires the edited name and
accepts a description (omission clears it). Grant PUT accepts
`{"permission":"read"}`, `write`, or `manage`.

Inspect generated schemas and examples at `http://127.0.0.1:8000/docs`; the
machine-readable contract is `/openapi.json`. Public document/job responses omit
storage paths, checkpoint contents, raw provider exceptions, and lease tokens.
Job failures expose `error_code` and a safe stage-specific `failure_reason`.
Job state is one of `queued`, `running`, `succeeded`, `failed`, or `cancelled`.

Every response includes a server-generated `X-Request-ID`. `/v1` failures use:

```json
{
  "error": {
    "code": "document_processing",
    "message": "Wait for processing to finish before deleting this document.",
    "request_id": "server-generated UUID"
  }
}
```

Missing identity returns 401; denied actions return 403; inaccessible individual
documents/jobs return 404. Invalid request fields return 422. Uploads additionally
use 413 for excess size and 415 for unsupported media types. Conflicts return
409 and dependency failures return 503. Clients should branch on `error.code`,
not message text. This replaces the former `/v1` `detail` error shape.

## Upload retries and dispatch

POST a multipart request containing one `file`, a supported declared media type,
and an `Idempotency-Key` header. Keys contain 1–200 letters, digits, `.`, `_`,
`:`, or `-`. The file limit defaults to 20 MiB and is configurable through
`UPLOAD_MAX_BYTES`, including in Docker Compose.

Supported media types are `application/pdf`, `text/plain`, `text/markdown`,
`text/x-markdown`, `text/html`, and `application/xhtml+xml`. Parsing happens in
the worker: a supported but corrupt file is accepted and later reports a job
failure. Unknown types are rejected before durable work is created.

An accepted upload returns 202:

```json
{
  "document_id": "UUID",
  "job_id": "UUID",
  "duplicate": false,
  "dispatch": "sent"
}
```

- Retry keys are scoped to the user's workspace membership and collection.
- Same key, file contents, filename, and normalized media type returns the same
  document/job IDs and original duplicate flag. Keys persist without expiry in
  this local project; permission checks still run on every retry.
- Changing the file or metadata under that key returns `idempotency_conflict`.
- A concurrent upload/deletion conflict returns `document_unavailable`; retry
  the upload after deletion finishes.
- A new key with identical content reuses the existing document and ingestion
  recipe. `duplicate` describes content reuse, not HTTP request replay.
- A key referring to deleted/deleting content returns `upload_deleted`; use a new
  key to upload a replacement. A failed existing job is inspected, not restarted
  by upload retries. Job retry controls remain deferred.
- `dispatch=sent` means a broker publication succeeded, not that processing
  finished. `pending` means the file/job are committed but publication failed.
  `not_needed` means the reused job is no longer queued.

The collection row serializes concurrent uploads. Document metadata, ingestion
job, retry receipt, and upload audit event commit in one PostgreSQL transaction;
only then is the job ID published to Redis. Duplicate delivery is handled by the
existing worker claim mechanism. Disk and PostgreSQL cannot commit atomically:
a crash after file save but before database commit can leave an orphan file;
it cannot leave a committed receipt without its document/job.

For `pending`, restore Redis and retry the same upload, restart the worker
(which performs its existing recovery pass), or run `make ingestion-recover`.
No new scheduler was added. Poll `/jobs/{job_id}` for completion.

## Deletion and recovery

DELETE rejects a running job with `document_processing` (409). Wait for it to
finish; for a crashed worker, restore dependencies and use the existing
`make ingestion-recover` command to recover expired ownership.

Otherwise deletion locks the document's job rows, cancels queued jobs, commits
`deleting` and an audit event, removes OpenSearch chunks, removes the original
and all per-job artifacts, then commits `deleted` and a completion audit event.
The locks coordinate with worker claims: either processing starts and deletion
is rejected, or queued work is cancelled and cannot start. Ingestion cannot
enqueue new work for deleting/deleted documents.

If cleanup fails, DELETE returns `deletion_pending` (503); retry the same DELETE
once the dependency is available. Application retrieval excludes deleting/deleted
document IDs before reranking and debug traces, even when stale chunks remain
in OpenSearch. Downloads also deny these documents. Successful repeated deletes
return 204, and the completion audit event is recorded once.

Document metadata, job history, retry receipts, and audit events remain in
PostgreSQL. Authorized metadata/job inspection still works after deletion;
deleted documents disappear from collection lists. No background deletion worker,
collection deletion, job cancellation endpoint, or recovery scheduler was added.

## Try locally

With a working Python 3.13 environment and the existing stack:

```bash
make stack-up
make db-upgrade
make db-seed
```

`make stack-up` rebuilds the Docker API/worker with the multipart dependency;
they share the same original/artifact volume. The host migration and seed
commands connect to PostgreSQL's exposed port, which is the same database used
by those containers. Open `http://127.0.0.1:8000/docs` to inspect the contract.

If you prefer host development, start only PostgreSQL, Redis, and OpenSearch
with `docker compose up -d --wait postgres redis opensearch`, then run
`make backend-dev` and `.venv/bin/dramatiq hybrid_rag_search.worker` in separate
terminals. Keep both on the same host configuration. Do not pair host originals
with a worker that reads only Docker's volume.

```bash
API_BASE=http://127.0.0.1:8000
DEMO_ADMIN=00000000-0000-4000-8000-000000000102
DEMO_WORKSPACE=00000000-0000-4000-8000-000000000101
DEMO_COLLECTION=00000000-0000-4000-8000-000000000104

curl -sS "$API_BASE/v1/workspaces/$DEMO_WORKSPACE/collections" \
  -H "X-Demo-User-ID: $DEMO_ADMIN"

printf 'Day 17 upload example.\n' > /tmp/day17-example.txt
curl -sS -X POST \
  "$API_BASE/v1/workspaces/$DEMO_WORKSPACE/collections/$DEMO_COLLECTION/documents" \
  -H "X-Demo-User-ID: $DEMO_ADMIN" \
  -H 'Idempotency-Key: day17-example-1' \
  -F 'file=@/tmp/day17-example.txt;type=text/plain'
```

Repeat the upload with the same key: both IDs should match. Copy the returned
IDs into the following commands:

```bash
DOCUMENT_ID=replace-with-document-id
JOB_ID=replace-with-job-id
curl -sS "$API_BASE/v1/workspaces/$DEMO_WORKSPACE/jobs/$JOB_ID" \
  -H "X-Demo-User-ID: $DEMO_ADMIN"
curl -i -X DELETE "$API_BASE/v1/workspaces/$DEMO_WORKSPACE/documents/$DOCUMENT_ID" \
  -H "X-Demo-User-ID: $DEMO_ADMIN"
```

Expected deletion: 204 when cleanup succeeds, 409 while running, or a retryable
503 during cleanup failure. The worker's normal embedding path uses configured
Cohere credentials; the automated verification below uses fakes and makes no
live model calls.

## Verification

```bash
make management-test
make check
make db-test
```

The integration suite requires the existing local PostgreSQL and OpenSearch
services. The management test creates, migrates, rolls back/reapplies the newest
migration, and drops a uniquely named disposable database; its database user
needs local `CREATEDB` permission. This preserves append-only audit semantics
and avoids polluting the working workspace. It also owns an isolated OpenSearch
index and removes that index afterward.

Verified cases include owner/member permissions, read/write/manage grants,
cross-workspace member IDs, concurrent upload retries, changed-key payloads,
size/type validation, disk-save rollback, Redis publication failure, job failure
redaction, deletion versus worker claims, index cleanup failure/retry, suppression
of stale indexed content, repeated deletion, and removal of job artifacts.

Validation on Python 3.13.16 passed: 824 default backend tests with 100% line
coverage, all 11 integration tests, Ruff formatting/lint, strict mypy, and the
unchanged frontend's formatting/lint/type checks, test, and production build.
The workspace's Python 3.13 interpreter was an empty file, so backend validation
used a supported interpreter and environment under `/private/tmp`; no system
interpreter or existing virtual environment was modified. Two existing typing
issues found with freshly installed tooling were resolved: an explicitly typed
floating-point gain calculation and an annotation for Dramatiq's untyped broker
constructor.

All Day 17 acceptance criteria are verified. Day 18 adds grounded generation and
request-bound citations on this authorization and document lifecycle foundation.
