# Repository map

Source revision: `f8493c1d264c525948d9d33ffaf2dd197be97e26`

Browse the Mermaid diagrams below on GitHub. PDFs and PNGs are linked for download.

[Overview PDF](overview/repository-map.pdf) | [Overview details](overview/README.md)

## answers: Architecture

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

## evaluation: Architecture

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

## foundation: Architecture

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

## frontend: Architecture

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

## ingestion: Architecture

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

## retrieval: Architecture

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

## Subsystem maps

| Map | Summary | Views | Last analyzed source |
| --- | --- | --- | --- |
| [answers](maps/answers/README.md) | The answers subsystem defines application-owned async provider contracts for generation, embeddings, and reranking, with validating dataclasses and a code-carrying ProviderError that sanitizes SDK failures. A Cohere generation adapter and a deterministic fake provider both implement the shared GenerationProvider protocol, returning GenerationResult with distinct reported and billed usage plus locally measured latency. No orchestration or caller wiring selecting between adapters is evidenced. | [PDF](maps/answers/repository-map.pdf) · [JSON](maps/answers/map.json) | `f8493c1d264c` |
| [evaluation](maps/evaluation/README.md) | The evaluation subsystem loads hash-verified versioned datasets, prepares isolated per-scope corpora in OpenSearch through the durable ingestion pipeline, runs four retrieval modes via a shared EvaluationSearch boundary, scores rankings with fixed metrics, and emits reproducible reports. It exposes a production-disabled debug search API and a SciFact builder CLI, and owns evaluation ORM tables. | [PDF](maps/evaluation/repository-map.pdf) · [JSON](maps/evaluation/map.json) | `f8493c1d264c` |
| [foundation](maps/foundation/README.md) | The foundation subsystem is the shared base layer of a multi-tenant hybrid RAG service: a create_app FastAPI entry point exposing health/readiness and an evaluation router, a cached typed Settings boundary, an async SQLAlchemy Base, a tenant-scoped DocumentService over replaceable file storage, and a linear Alembic chain defining identity, content, retrieval, evaluation/audit, and ingestion-job schema. Migrations push authorization, lifecycle, lease, and immutability invariants into PostgreSQL, while a Dockerfile, Makefile, Compose, and CI provide orchestration and verification. | [PDF](maps/foundation/repository-map.pdf) · [JSON](maps/foundation/map.json) | `f8493c1d264c` |
| [frontend](maps/frontend/README.md) | This subsystem is the hybrid-rag-search-web frontend: a private Next.js 16 / React 19 App Router project whose container runs the dev server on Node 22. It renders a root layout wrapping a purely static Home page with no state, inputs, or async data loading. No fetch, API route, or environment read is evidenced, so runtime linkage to the answers, foundation, or retrieval subsystems is untraced. | [PDF](maps/frontend/repository-map.pdf) · [JSON](maps/frontend/map.json) | `f8493c1d264c` |
| [ingestion](maps/ingestion/README.md) | The chunking subsystem deterministically converts a ParsedDocument into content-addressed Chunks. It groups parsed blocks by heading path so no chunk crosses a section boundary, greedily packs whole blocks within a token budget with trailing overlap, splits oversized blocks by binary prefix search, and enriches text with reconstructed Markdown headings for embedding while stamping config-version and document-derived identity digests. | [PDF](maps/ingestion/repository-map.pdf) · [JSON](maps/ingestion/map.json) | `f8493c1d264c` |
| [retrieval](maps/retrieval/README.md) | Dense-query retrieval for a multi-tenant hybrid RAG backend: a normalized query is embedded via an injected provider into a vector, then issued as an OpenSearch k-NN search against a read alias with tenant scoping applied at query level. Hits are renormalized into the shared RetrievalResult contract reused by lexical retrieval, with diagnostics kept in a separate trace. Configuration derives from Settings; the only local entry point is a debug CLI, with orchestration living elsewhere. | [PDF](maps/retrieval/repository-map.pdf) · [JSON](maps/retrieval/map.json) | `f8493c1d264c` |

JSON is the source of truth; Mermaid, PNGs, and PDFs are generated views.

Unchanged subsystem views are retained. Source existence checks do not prove model interpretation. See manifest.json and update.json for dependencies, coverage and updates.
