# Repository map

The overview brings together the analyzed architecture view from each subsystem. Open a subsystem map for its source evidence, detailed flows, and uncertainties.

Commit: `f8493c1d264c525948d9d33ffaf2dd197be97e26` | Generated: 2026-10-18T18:36:28.266995+00:00

[Open PDF](repository-map.pdf)

**AI-generated analysis. Source references are checked for existence and supplied scope; this does not prove semantic correctness.**

## Scope

Source-backed architecture views composed from each subsystem map. See linked subsystem pages for evidence.

0/0 eligible files analyzed; 0 tracked files excluded by policy.

0 API calls. See coverage.json for budgets, exclusions, and usage.

## answers: Architecture

Application-owned protocols define the boundary; the opt-in Cohere adapter and the deterministic fake both implement GenerationProvider. The configured factory gates live generation on credentials, but caller wiring is not evidenced. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Configured<br/>factory"]
  n1["Cohere adapter"]
  n2["Fake provider"]
  n3["Generation<br/>contract"]
  n4["ProviderError"]
  n5["Usage and cost"]
  n0 -->|"Constructs live<br/>provider"| n1
  n1 -->|"Returns result"| n3
  n2 -.->|"Inferred:<br/>Returns result"| n3
  n1 -->|"Raises mapped<br/>codes"| n4
  n1 -->|"Billed usage"| n5
  n3 -->|"Carries usage"| n5
  n0 -.->|"Inferred:<br/>Adapter<br/>selection"| n2
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-01.png)

</details>

### Source evidence


## evaluation: Architecture

Dataset loading, corpus preparation, search dispatch, scoring/reporting, and the HTTP surface are separate boundaries; the API and runner share one search boundary, while corpus state faults map to distinct errors. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Dataset loader"]
  n1["Corpus<br/>preparation"]
  n2["EvaluationSearch"]
  n3["Runner and<br/>reports"]
  n4["Debug search API"]
  n5["Evaluation ORM"]
  n0 -->|"Validated<br/>records"| n1
  n1 -->|"Prepared scope"| n2
  n3 -->|"Per query/mode"| n2
  n3 -->|"Loads dataset"| n0
  n4 -->|"Verify prepared"| n1
  n4 -->|"Debug search"| n2
  n1 -->|"Ingestion job<br/>rows"| n5
  n1 -->|"Corpus hash<br/>scope"| n0
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-02.png)

</details>

### Source evidence


## foundation: Architecture

The FastAPI app reads shared Settings and mounts health and evaluation routes; the same Settings feeds schema management and dependency probes. Makefile, Compose, and CI form the orchestration boundary around app, schema, and tests. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["FastAPI app"]
  n1["Settings"]
  n2["SQLAlchemy Base"]
  n3["DocumentService"]
  n4["Makefile and CI"]
  n5["Alembic<br/>migrations"]
  n0 -->|"reads settings"| n1
  n5 -->|"same db URL"| n1
  n5 -->|"target metadata"| n2
  n3 -->|"async sessions"| n2
  n4 -->|"upgrade and seed"| n5
  n4 -.->|"Inferred:<br/>uvicorn dev run"| n0
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-03.png)

</details>

### Source evidence


## frontend: Architecture

The container runs the Next.js App Router dev server. Layout renders a static index page. Toolchain config types, lints, and tests the sources but is not a runtime entry point; backend linkage is unevidenced. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Frontend<br/>container"]
  n1["Next.js App<br/>Router"]
  n2["Root layout"]
  n3["Static index<br/>page"]
  n4["Lint type test<br/>config"]
  n0 -->|"Runs dev server"| n1
  n1 -->|"Renders root"| n2
  n2 -->|"Renders children"| n3
  n4 -->|"Types and lints"| n1
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-04.png)

</details>

### Source evidence


## ingestion: Architecture

The chunking package groups parsed blocks per heading section, packs them under the token budget, enriches embedding text, and emits Chunk contracts whose identities are derived from config and document digests. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Chunking package"]
  n1["Chunker"]
  n2["Embedding text<br/>builder"]
  n3["Chunk contract"]
  n4["Chunking config"]
  n5["Identity digests"]
  n0 -.->|"Inferred: Public<br/>entry point"| n1
  n1 -->|"Heading path +<br/>body"| n2
  n2 -->|"Embedding text"| n1
  n4 -->|"Token limits"| n1
  n1 -->|"Emits Chunks"| n3
  n5 -->|"Chunk identity"| n3
  n4 -->|"Config version"| n5
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-05.png)

</details>

### Source evidence


## retrieval: Architecture

Settings derive a dense config and connection details; the retriever injects an embedding provider, queries the OpenSearch read alias with tenant-scoped filters, and emits shared results plus a separate trace. Open this subsystem map for source evidence.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Settings"]
  n1["DenseRetrievalConfig"]
  n2["Dense retriever"]
  n3["Embedding<br/>provider"]
  n4["OpenSearch alias"]
  n5["Retrieval<br/>results"]
  n0 -->|"Derives fields"| n1
  n0 -->|"URL and alias"| n2
  n1 -->|"Limits and model"| n2
  n3 -->|"Injected<br/>provider"| n2
  n2 -->|"Query embedding"| n3
  n2 -->|"k-NN search"| n4
  n4 -->|"Hit mapping"| n5
  n2 -->|"Response plus<br/>trace"| n5
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-06.png)

</details>

### Source evidence


## Uncertainties and untraced areas

- Subsystem boundaries and configured or import-inferred dependencies are recorded in manifest.json; they do not establish runtime calls.
