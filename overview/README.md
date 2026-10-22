# Repository map

The overview brings together the analyzed architecture view from each subsystem. Open a subsystem map for its source evidence, detailed flows, and uncertainties.

Commit: `e4abb88a149b365c2838b0f2f0606dff0127b1ab` | Generated: 2026-10-22T15:21:02.384365+00:00

[Open PDF](repository-map.pdf)

**AI-generated analysis. Source references are checked for existence and supplied scope; this does not prove semantic correctness.**

## Scope

Source-backed architecture views composed from each subsystem map. See linked subsystem pages for evidence.

0/0 eligible files analyzed; 0 tracked files excluded by policy.

0 API calls. See coverage.json for budgets, exclusions, and usage.

## answers: How a question becomes a saved answer

Someone asks a question; the system finds their permitted passages, the model writes a checked answer streamed live, and the finished answer is saved for that person.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Question asked"]
  n1["Find permitted<br/>passages"]
  n2["Write grounded<br/>answer"]
  n3["Check answer and<br/>citations"]
  n4["Save private<br/>answer"]
  n0 -->|"Question text"| n1
  n1 -->|"Allowed passages"| n2
  n2 -->|"Draft text and<br/>sources"| n3
  n3 -->|"Verified answer"| n4
  n4 -->|"Live text and<br/>answer id"| n0
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-01.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## evaluation: How a dataset becomes a scored report

A hash-verified test bundle is prepared into its own search index, every test question is searched four ways, results are scored against human relevance labels, and repeatable report files are written.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Verified test<br/>bundle"]
  n1["Prepare search<br/>index"]
  n2["Confirm index<br/>ready"]
  n3["Try each search<br/>style"]
  n4["Score against<br/>labels"]
  n5["Report files<br/>written"]
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


## foundation: How a request becomes a result

An incoming web request is identified, checked for permission against the caller's tenant and collections, then handled so it either produces a result or a consistent error reply.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Incoming request"]
  n1["Identify caller"]
  n2["Check permission"]
  n3["Run request work"]
  n4["Result returned"]
  n5["Uniform error<br/>reply"]
  n0 -->|"who is calling"| n1
  n1 -->|"known caller"| n2
  n2 -->|"allowed, scoped"| n3
  n3 -->|"success"| n4
  n3 -->|"failure"| n5
  n2 -->|"denied"| n5
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-03.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## frontend: How a question becomes a cited answer

A person picks a collection and identity, asks a question, and watches the answer stream back live. Citations can be opened to view and download the original source document.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Person using the<br/>site"]
  n1["Document<br/>workspace page"]
  n2["Same-origin<br/>forwarder"]
  n3["Answer service"]
  n4["Opened source<br/>view"]
  n0 -->|"Picks scope and<br/>asks"| n1
  n1 -->|"Sends question"| n2
  n2 -->|"Forwards without<br/>cookies"| n3
  n3 -->|"Streams draft<br/>then final"| n1
  n0 -->|"Opens a citation"| n4
  n2 -->|"Fetches source<br/>file"| n4
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-04.png)

</details>

Read from top to bottom; arrows show what happens next or what is passed along.

### Source evidence


## ingestion: How a document becomes an ingestion job

A caller submits a tenant, document, and pipeline version. The service saves a job, marks the document as processing, and after the database commit signals that work is ready.

```mermaid
%%{init: {"themeVariables": {"fontSize": "22px"}}}%%
flowchart TD
  n0["Caller requests<br/>ingestion"]
  n1["Check<br/>identifiers and<br/>version"]
  n2["Save durable job<br/>record"]
  n3["Mark document<br/>processing"]
  n4["Publish work<br/>hint"]
  n0 -->|"Tenant, doc,<br/>version"| n1
  n1 -->|"Insert inside<br/>transaction"| n2
  n2 -->|"New job only"| n3
  n2 -->|"After commit"| n4
  n3 -.->|"Status is queued"| n4
```

<details>
<summary>PNG fallback</summary>

![Diagram](diagram-05.png)

</details>

Read from top to bottom. Dashed arrows show connections that need confirmation.

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
