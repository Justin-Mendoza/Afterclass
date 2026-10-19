# Repository map

The overview brings together the analyzed architecture view from each subsystem. Open a subsystem map for its source evidence, detailed flows, and uncertainties.

Commit: `3537e913c1eeec5b5f34d6cbdbf4dc3f8bc74b25` | Generated: 2026-10-19T00:25:53.475115+00:00

[Open PDF](repository-map.pdf)

**AI-generated analysis. Source references are checked for existence and supplied scope; this does not prove semantic correctness.**

## Scope

Source-backed architecture views composed from each subsystem map. See linked subsystem pages for evidence.

0/0 eligible files analyzed; 0 tracked files excluded by policy.

0 API calls. See coverage.json for budgets, exclusions, and usage.

## answers: How a prompt becomes an answer

A caller supplies validated chat messages; the answer provider forwards one non-streaming request to the model service, re-checks the reply, and returns answer text with finish reason and usage.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Validated prompt"]
  n1["Answer provider"]
  n2["Model service"]
  n3["Reply checked"]
  n4["Answer and usage"]
  n0 -->|"Messages and<br/>limit"| n1
  n1 -->|"One chat request"| n2
  n2 -->|"Raw reply text"| n3
  n3 -->|"Accepts answer"| n4
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-01.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## evaluation: How a dataset becomes a scored report

A verified dataset bundle is prepared into its own search index, every test question is searched in four ways, results are scored against human relevance labels, and a repeatable report is written.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Verified dataset<br/>bundle"]
  n1["Prepare search<br/>index"]
  n2["Confirm index<br/>ready"]
  n3["Try each search<br/>style"]
  n4["Score against<br/>labels"]
  n5["Reproducible<br/>report files"]
  n0 -->|"Corpus and<br/>questions"| n1
  n1 -->|"Check job<br/>receipts"| n2
  n2 -->|"Index confirmed"| n3
  n3 -->|"Ranked results"| n4
  n4 -->|"Metrics per<br/>question"| n5
  n0 -->|"Questions and<br/>labels"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-02.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## foundation: How an uploaded file becomes a stored document

A caller supplies an authorized tenant and collection scope with file bytes. The service fingerprint-checks for duplicates, saves the file, and records its status.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["File upload"]
  n1["Fingerprint and<br/>duplicate check"]
  n2["Save original<br/>file"]
  n3["Document record"]
  n4["Existing<br/>document<br/>returned"]
  n0 -->|"same file<br/>before?"| n1
  n1 -->|"already stored"| n4
  n1 -->|"new content"| n2
  n2 -->|"bytes written"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-03.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## frontend: How a visitor gets the landing page

A visitor opens the site, the page shell supplies styling and page title, and the static landing content appears. Nothing is looked up or saved, and no search runs.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Site visitor"]
  n1["Web server"]
  n2["Page shell and<br/>styling"]
  n3["Landing page<br/>content"]
  n0 -->|"Opens the site"| n1
  n1 -->|"Builds the page"| n2
  n2 -->|"Shows headings"| n3
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-04.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## ingestion: How a parsed document becomes searchable pieces

A parsed document is split by heading section, packed into token-budgeted pieces with overlap, enriched with reconstructed headings, and given stable identifiers.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Parsed document"]
  n1["Split by heading"]
  n2["Pack within<br/>token budget"]
  n3["Rebuild heading<br/>text"]
  n4["Identified<br/>pieces"]
  n0 -->|"Group blocks by<br/>heading"| n1
  n1 -->|"One section at a<br/>time"| n2
  n2 -->|"Text and heading<br/>path"| n3
  n3 -->|"Final text and<br/>spans"| n4
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-05.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## retrieval: How a search becomes matching passages

A search phrase is cleaned, sent out to be turned into numbers, used to find the closest stored passages in the search index, and returned as passages with optional diagnostic detail.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Search phrase"]
  n1["Clean up text"]
  n2["Turn words into<br/>numbers"]
  n3["Find closest<br/>passages"]
  n4["Matching<br/>passages"]
  n0 -->|"Text to tidy"| n1
  n1 -->|"Cleaned text"| n2
  n2 -->|"Numeric<br/>fingerprint"| n3
  n3 -->|"Closest passages"| n4
  n3 -->|"Diagnostic<br/>details"| n4
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-06.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## Uncertainties and untraced areas

- Subsystem boundaries and configured or import-inferred dependencies are recorded in manifest.json; they do not establish runtime calls.
