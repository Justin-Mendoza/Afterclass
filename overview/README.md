# Repository map

Separate subsystem maps with an overview of their dependency hints.

Commit: `05fb919153379762ce04a644ff9f6ef3e3413ff1` | Generated: 2026-10-17T22:43:02.770331+00:00

[Open PDF](repository-map.pdf)

**AI-generated analysis. Source references are checked for existence and supplied scope; this does not prove semantic correctness.**

## Scope

Subsystem boundaries; dependency edges are hints, not verified runtime calls.

0/0 eligible files analyzed; 0 tracked files excluded by policy.

0 API calls. See coverage.json for budgets, exclusions, and usage.

## answers: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["answers"]
  n1["foundation"]
  n2["retrieval"]
  n0 -.->|"Inferred: Uses"| n1
  n0 -.->|"Inferred: Uses"| n2
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-01.png)

</details>

### Source evidence


## evaluation: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["evaluation"]
  n1["foundation"]
  n2["ingestion"]
  n3["retrieval"]
  n0 -.->|"Inferred: Uses"| n1
  n0 -.->|"Inferred: Uses"| n2
  n0 -.->|"Inferred: Uses"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-02.png)

</details>

### Source evidence


## foundation: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["foundation"]
  n1["answers"]
  n2["ingestion"]
  n3["retrieval"]
  n0 -.->|"Inferred: Uses"| n1
  n0 -.->|"Inferred: Uses"| n2
  n0 -.->|"Inferred: Uses"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-03.png)

</details>

### Source evidence


## frontend: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["frontend"]
  n1["answers"]
  n2["foundation"]
  n3["retrieval"]
  n0 -.->|"Inferred: Uses"| n1
  n0 -.->|"Inferred: Uses"| n2
  n0 -.->|"Inferred: Uses"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-04.png)

</details>

### Source evidence


## ingestion: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["ingestion"]
  n1["foundation"]
  n0 -.->|"Inferred: Uses"| n1
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-05.png)

</details>

### Source evidence


## retrieval: connections

Dependency hints are configured or inferred from resolvable imports. See subsystem maps for source-backed behavior.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["retrieval"]
  n1["foundation"]
  n2["ingestion"]
  n0 -.->|"Inferred: Uses"| n1
  n0 -.->|"Inferred: Uses"| n2
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-06.png)

</details>

### Source evidence


## Uncertainties and untraced areas

- Import inference is incomplete; configure aliases and cross-service dependencies explicitly.
