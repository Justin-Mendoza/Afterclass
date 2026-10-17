# Incremental repository maps

JSON summaries are stored on a dedicated `repo-map` branch. Each subsystem has its own GitHub-readable Mermaid page, PNG diagrams and PDF. Default-branch merges update the affected subsystems; generated output does not go onto the application branch.

## Hybrid RAG Search configuration

The first activated workflow run bootstraps all six maps through Kyma; no local seed is prepared. Subsequent default-branch pushes update affected maps and their known dependents.

| Map | Owned behavior | Explicit dependencies |
| --- | --- | --- |
| `foundation` | API wiring, authorization, models, migrations, document management, storage and operations | ingestion, retrieval, answers |
| `ingestion` | Workers, jobs, parsing, chunking, embedding and indexing | foundation |
| `retrieval` | Lexical/dense retrieval, fusion, reranking and filters | foundation, ingestion |
| `answers` | Generation, citations, streaming and saved history | foundation, retrieval |
| `evaluation` | Dataset loading, metrics, evaluation runs and dataset schemas | foundation, ingestion, retrieval |
| `frontend` | Next.js interface and API interactions | foundation, retrieval, answers |

See `config.json` for exact file ownership. Shared provider adapters and contracts belong to multiple maps. Explicit dependencies describe consumed behavior, including API wiring and cross-service calls that basic import detection misses. The foundation map contains both shared infrastructure and API composition, so it has reciprocal dependencies with application maps. This is deliberate and conservative: many backend changes can refresh all six maps. A frontend-only change refreshes only the frontend map. Smaller refresh scopes would require separating API composition from shared infrastructure in a later map-boundary revision.

The source allowlist covers backend application code, migrations, tests, frontend code, dataset schemas and operational configuration. Corpus/query/judgment records, evaluation output, parser record fixtures, personal notes, ticket history, environment files, lockfiles, generated content and styling are excluded. Only `datasets/schemas/*.schema.json` is exempted from the template's blanket dataset-directory block; other dataset paths remain blocked. Tracked files are subject to the same policy as other source; `.gitignore` alone does not protect them.

Analysis remains bounded, not exhaustive. The existing limits are retained: 24 total API calls per update, at most six focused diagrams per subsystem, and a full refresh after 20 analysis updates. Actual charges depend on provider usage; the call limit is not a dollar cap. No application dependency or runtime service is added.

To inspect map ownership after committing the setup and other source changes:

```sh
python3 .repo-map/incremental.py --repo . --state /tmp/hybrid-rag-map-state --plan
```

Use an empty state directory outside the repository. Expect all six maps on the first plan, no unassigned eligible source, and no API calls. The planner requires a clean tracked working tree; do not stash unrelated work merely to run it. During installation, validation can use a separate temporary Git snapshot instead. Plans report eligible files without reproducing source excerpts.

## Activate

1. Under **Settings → Secrets and variables → Actions → New repository secret**, add `KYMA_API_KEY` with your Kyma key. Do not put the key in source code.
2. Defaults: API base `https://api.kymaapi.com/v1`, model `deepseek-v4.1-flash`. Optional Actions **Variables** `LLM_BASE_URL` and `LLM_MODEL` override these. The endpoint must support Chat Completions with JSON-object responses. Public Kyma docs also list `https://kymaapi.com/v1`; if the configured host redirects, use the canonical base URL explicitly. This client does not follow authenticated redirects.
3. Review source scopes and subsystem definitions in `config.json` before sending private source to the provider. Exclude confidential data explicitly. Secret-file exclusions and credential-line redaction are heuristics, not complete protection for arbitrary private records.
4. Commit/push setup to the default branch and enable Actions. The workflow needs `contents: write` to create/update **only `repo-map`** using GitHub's built-in token. Branch protection or organization policy can block that write; no personal access token is normally needed. Do not use `repo-map` as the application's default branch or for unrelated files.
5. Pushes/merges to the default branch run automatically; changes only to this guide are skipped. Feature-branch runs skip generation. You can also use **Actions → Update repository maps → Run workflow** on the default branch, with optional full refresh.

The first activated workflow run uses DeepSeek through Kyma to generate all initial subsystem maps and the overview automatically. No local seed is needed. Later runs compare with the last successful map revision and update affected maps. Each executed analysis uses Kyma credits. No schedules, untrusted PR execution, public website, or desktop popup is configured.

## Browse the results

Switch the GitHub branch selector to **repo-map**, open its README, and follow the subsystem links. Mermaid diagrams render directly in GitHub Markdown; PNG fallbacks and PDFs are available alongside them.

```text
repo-map branch
├── README.md                 overview and subsystem links
├── manifest.json             file hashes, map ownership, dependencies, revisions
├── update.json               last update scope, API calls and usage
├── overview/                 small dependency views + PDF
└── maps/
    ├── api/                  example subsystem, chosen for your actual repo
    │   ├── map.json          summary, graph, evidence and metadata
    │   ├── README.md         readable Mermaid views and source links
    │   ├── diagram-01.mmd
    │   ├── diagram-01.png
    │   ├── repository-map.pdf
    │   └── coverage.json
    └── …
```

Successful runs also upload `repo-map-<run number>` under **Actions → completed run → Artifacts**, with a summary link. Download requires repository access and sign-in. Artifact retention is 30 days, subject to policy. The `repo-map` branch remains until deleted; normal Git version history applies, so artifacts do not expire its committed history.

## Define maps

`maps: {}` uses a deterministic directory grouping as a fallback. For better boundaries, configure actual subsystems:

```json
"maps": {
  "api": {"include": ["backend/*", "shared/contracts/*"], "depends_on": ["storage"]},
  "frontend": {"include": ["frontend/*", "shared/contracts/*"], "depends_on": ["api"]},
  "storage": {"include": ["database/*"], "depends_on": []}
}
```

Replace these examples with real paths. IDs are lowercase letters/digits/hyphens (start with a letter, at most 48 characters). Use at most 12 maps and ensure the total call budget can cover them. Shared files can belong to multiple maps. Relevant files not assigned to any explicit map are listed in `manifest.json`; resolve those omissions during setup.

`depends_on` means the map consumes another subsystem's interface or behavior. Resolvable relative JS imports and basic Python imports add dependency hints. Aliases, framework wiring, Go package paths, dynamic calls and cross-service contracts are not fully inferred; add dependencies explicitly. Globs use Python `fnmatch` against repo-relative paths (`*` also matches slashes). Global `include`/`exclude` apply before map scopes. Only tracked, eligible text is sent; `.gitignore` does not hide already tracked files.

## What updates

- File hashes detect changed, added, deleted and renamed eligible files against the last successful state.
- Changed maps and their transitive known dependents are rechecked conservatively, including removed dependency links. A body change can matter to a consumer even when the function signature stays the same.
- Only affected subsystem excerpts, changed-path context, and saved/neighbor summaries go to the API. This is not a diff-only prompt: current subsystem context is included to avoid stale relationships.
- Semantically unchanged presentation data reuses existing PNG/PDF bytes. Overview renders only when dependency topology changes. A styling-only change outside the source policy makes no model call.
- Removed maps are deleted from the saved state. The index shows each map's last analyzed revision, which can be older than the latest commit for unaffected maps.
- Config/model/renderer changes, divergent Git history, manual full refresh, and every 20 analysis updates refresh all maps. Full refresh still uses bounded excerpts, not every line.
- State is staged before replacing outputs. API/schema/layout failures publish nothing. Stale queued runs cannot regress a newer analyzed source revision. Publication is also skipped if the remote default branch has advanced while generation was running; a newer queued run catches up. Publication uses ordinary Git pushes, never force pushes.

The publisher writes only to `repo-map`; it does not update source branches, open PRs, or run application scripts. Branch filtering, a default-branch job guard and bot-token behavior prevent self-triggered map loops. Do not modify generated Mermaid/PNG/PDF files independently: JSON summaries/graphs are their source of truth.

## Readability and limits

Use focused top-down views: 2-6 nodes, at most 8 edges, short wrapped labels, and 1-2 sentence explanations (40 words maximum). Large graphs should become multiple small views. Each PDF page shows one diagram. Rendering uses Graphviz at 144 dpi; Mermaid comes from the same graph. Node text is 22pt at layout time and must stay at least 12pt after fitting a PDF page; oversized layouts fail instead of silently shrinking. The fallback is not a general Mermaid ER/sequence renderer.

Default per-map analysis: 160 files, 18,000 source characters per file, 180,000 total source characters, 24,000-character batch target, 12 API calls (including synthesis), 6,000 output tokens per call, and six diagrams. A shared limit of 24 calls covers the entire update. Calls are allocated so remaining affected maps retain at least an analysis and synthesis call. Increase budgets deliberately or group scopes more broadly if needed. Runtime timeout is 60 minutes. Provider and Actions billing apply; request limits are not an exact dollar cap.

Coverage and source IDs prove that evidence locations were supplied, not that the model's interpretation is true. Excerpt truncation and call-budget omissions are recorded. Credential-like lines are redacted and common credential/build/dependency files excluded. Raw source snippets and raw model responses are not persisted as artifacts, but generated summaries can reveal architecture. Review who can read the repo and the chosen API provider's handling of submitted source.

No automatic API retry is made; a timed-out request can still incur a charge. HTTP/model/JSON/reference errors fail the run rather than publishing plausible partial output. Requested/reported models and any Kyma substitution are recorded. If a request fails, inspect the non-secret error and fix endpoint/model/access/configuration before rerunning.

## Local planning / optional seed

With committed source and an empty temporary directory, inspect ownership and invalidation without a key:

```sh
python3 .repo-map/incremental.py --repo . --state /tmp/my-repo-map-state --plan
```

No analysis or rendering is performed. The setup skill can author initial `maps/<id>/map.json` seeds locally and validate/render them with `--seed <seed-directory>`; this works only for empty state and needs no API key. Source paths/line ranges, findings and graph structure are checked. Publication of prepared seed state is a separate operation, not a consequence of planning.

For local full generation, use an existing Python 3.12+ environment with ReportLab and Graphviz `dot`. Keep state outside the source repo. The workflow installs its own tools, never application dependencies.

References: [Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts), [Kyma Chat Completions](https://docs.kymaapi.com/api-reference/chat-completions).

## Installation verification

Offline installation checks passed against these installed scripts in an isolated copy of the skill's test workspace: 23 tests using mocked model responses and local Git remotes. They exercise incremental invalidation, unchanged-view reuse, failed-update staging, source-reference validation and map-branch publication. No authenticated Kyma calls or GitHub workflow run were performed.

A clean temporary Git snapshot was used for the repository `--plan` check because the working repository contained unrelated tracked edits. All six maps were selected for initial generation, with no unassigned or skipped eligible source. Additional assertions checked schema inclusion and record/credential exclusions. Ruby's YAML parser checked workflow syntax; structural checks covered triggers, the default-branch guard, serialized updates, permissions, step-scoped credentials and 30-day artifact retention. Action references retain the template's full commit hashes; their remote existence was not independently tested.

These checks verify offline mechanics and configuration, not the semantic accuracy or layout of future model-generated maps. After activation, inspect the first GitHub run and each subsystem's diagrams and coverage report. The configured endpoint/model, account access, Actions policy and map-branch push permissions remain live activation checks.
