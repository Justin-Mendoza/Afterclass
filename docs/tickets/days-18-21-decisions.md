# Days 18–21 — Usable document Q&A milestone

Status: all five main design decisions and the complete plan approved by the owner;
implementation and local verification completed on 2026-10-19. See the
[combined runbook](days-18-21.md) for acceptance results and limitations.

## Outcome and scope

Complete and integrate grounded answers, streaming and cancellation, collection
and upload management, private history, and interactive citation inspection.
The local demo must support upload → processing → question → cited answer.
Use the existing simulated demo identities and enforced backend permissions.
Student branding and study-guide generation are deferred.

## Agreed decisions

1. **Live draft:** show generated text progressively with an explicit unverified
   state. Finalize after citation validation. Clear rejected draft text on failure;
   text already delivered to a client cannot be withdrawn from that client.
2. **Answer API:** POST to
   `/v1/workspaces/{workspace_id}/answers/stream`, with a question and optional
   collection ID. Send typed progress, content, citations, and completion events,
   or a terminal error. Completion supplies the authoritative final result.
3. **Cancellation and history:** stop active work where supported on Stop or
   disconnect and release resources. Discard unfinished drafts without a history
   entry. Save validated completed results, including partial and insufficient
   evidence outcomes, and safe failure records without rejected text. A result
   committed immediately before a disconnect remains in history. Retry starts a
   fresh request; provider charges for work already performed may still apply.
4. **Layout:** a sidebar for demo identity, workspace, collections, and recent
   questions; a main question/answer area with Stop/Retry and citations; a source
   panel with the supporting passage and file/page/heading information where
   available; a documents view with upload and processing status; and permission
   controls for authorized managers. Default questions to the selected collection,
   with an explicit option for all accessible collections.
5. **Connection behavior:** no automatic reconnect, replay, or paid retry. An
   interrupted connection shows a clear interrupted state with manual Retry.
   Apply a 90-second overall request deadline while retaining the configured
   provider timeouts. Requests are independent and cannot resume after disconnect.

## Owner's visual and interaction requirements

- Light mode with a pencil-drawn, paper-like visual character.
- A polished, smooth, interactive frontend using relevant available frontend and
  design skills.
- Smooth animations for transitions and interactions, including hover feedback
  wherever applicable (buttons, links, cards, tabs, and citation references).

Implementation direction to include in the proposed plan:

- Warm paper surfaces, graphite text, restrained sketch-like borders and marks,
  and legible typography. Keep long answers and source passages easy to read.
- Define shared color, spacing, typography, border, and motion values so the
  style stays consistent across every view and state.
- Use subtle motion for panels, navigation, uploads, feedback, and controls.
  Keep streamed text stable and avoid unnecessary movement while reading.
- Pair hover feedback with visible keyboard focus; avoid hover-only actions and
  maintain usable touch controls.
- Provide responsive layouts, keyboard access, visible focus, and reduced-motion
  support. Make loading, empty, success, cancellation, and error states clear.
- Apply the available design-system-management skill; use other relevant design
  skills when their workflows help the approved implementation.

## Open decisions

None.

## Complete implementation plan

1. **Prepare the integration branch.** Confirm the renamed GitHub repository
   (`Justin-Mendoza/Afterclass`), update the local remote URL, and work on a new
   branch containing the existing Day 18 work and current pipeline fixes.
   Preserve the owner's staged changes; merge repository state without rewriting
   shared history. The repository rename does not require renaming Python packages,
   local directories, Docker volumes, or the product interface in this increment.
2. **Complete the Day 18 foundation.** Keep evidence budgets, stable chunk IDs,
   source spans, answer outcomes, and citation validation. Refactor only what the
   streaming path needs so complete and streamed generation share validation and
   history behavior. Preserve the existing multi-source/conflict fixtures and
   author-private access checks.
3. **Implement actual provider streaming.** Extend the current generation contract
   and Cohere adapter to yield text increments and assemble native citations,
   completion status, usage, and latency. Hide the internal status prefix from
   the draft, including when it arrives across multiple chunks. Provider abstention
   uses fixed safe text rather than arbitrary generated abstention prose. Validate
   the accumulated response using the shared Day 18 rules before final delivery.
   Close provider resources on cancellation and do not retry automatically.
4. **Expose the answer stream.** Add typed request/event schemas and the agreed POST
   endpoint. Authenticate and authorize before streaming. Emit ordered progress
   and content events, then checked citations and exactly one successful terminal
   completion, or a terminal error. Completion includes the saved answer ID and
   authoritative final result. Apply the overall deadline, propagate cancellation,
   handle truncated connections, and reject unsupported resume requests before
   starting paid work. Track time to first generated content and total generation
   time separately from progress messages. Follow the agreed persistence rules;
   report storage failures without claiming an answer was saved.
5. **Connect the browser to FastAPI.** Add a typed API client and a thin same-origin
   forwarding route through the existing Next.js service using `API_INTERNAL_URL`.
   Forward the selected demo identity, files, and streams; propagate aborts and
   disable response buffering/caching for answers. Keep authorization, retrieval,
   and validation in FastAPI. Use browser streaming fetch and cancellation APIs;
   add no client state framework or streaming service.
6. **Build the shared interface and document workflows.** Implement the light
   pencil-on-paper design, reusable controls, responsive layout, hover/focus
   feedback, transitions, and reduced-motion support. Add demo user/workspace
   selection, collections, document uploads, upload progress, and job-status
   polling through a durable result. Reuse upload retry keys for the same upload
   attempt. Add collection creation/editing and permission controls that reflect
   backend-authorized capabilities. Cancel or ignore obsolete requests when the
   identity, workspace, or selection changes.
7. **Build questions, history, and source inspection.** Connect question input and
   collection scope to the stream. Show progress, provisional drafts, Stop/Retry,
   final outcomes, and interruption/error states without duplicating text. Load
   private history on demand. Render citation offsets against final answer text;
   open the exact supporting evidence snapshot in the source panel with filename,
   heading/page details when available, and an authorized original-file download.
   Resolve direct answer/source links through current permission-checked history
   and document APIs. Withhold revoked or deleted sources and clear stale content
   when identity changes. Render uploaded/provider text as untrusted text.
8. **Verify and document the whole milestone.** Add focused backend provider/API
   tests for ordering, split status prefixes, valid/invalid citations, abstention,
   provider failure, timeout, disconnect/cancellation cleanup, persistence, and
   source authorization. Add frontend behavioral tests for upload/job lifecycle,
   streaming parser boundaries, Stop/Retry, stale identity responses, terminal
   states, and citation inspection. Run repository formatting, lint, type checks,
   tests, and production build plus relevant database/integration checks. Inspect
   the app in a browser at desktop/mobile sizes and with reduced motion. Verify
   end-to-end wiring with deterministic fixtures without paid provider calls.
   Document commands, limitations, and acceptance results for all four tickets.

## Acceptance coverage

- Day 18 / #16: request-bound evidence/citations, safe rejection, abstention and
  partial outcomes, multi-source/conflict fixtures.
- Day 19 / #20: ordered typed SSE, cancellation/resource cleanup, explicit
  mid-stream terminal failure, measured timing, integration coverage.
- Day 20 / #19: usable upload/collection/admin screens, clear feedback, different
  permitted collections per identity, durable ingestion status, server-owned rules.
- Day 21 / #25: question-to-answer experience, stable streamed text, interactive
  authorized source context, safe direct links, Stop and manual Retry.
- Owner's visual requirement: light paper/graphite theme, pencil-like details,
  smooth interactions and hover animations, readable text, keyboard/touch support,
  and reduced-motion behavior.

## Scope check and deferred work

Every component above maps to the four ticket acceptance criteria or the owner's
agreed interface requirements. Reuse Next.js, React, FastAPI, Cohere, PostgreSQL,
the ingestion worker, and existing retrieval components. Do not add services,
frameworks, queues for answers, replay storage, automatic API retries, or public
hosting. Real account authentication, multi-turn conversations, student rebranding,
study guides, and Day 22 diagnostics remain deferred. Supported uploads remain
PDF, plain text, Markdown, and HTML as the existing backend allows; do not execute
or embed untrusted HTML. No claim of live Cohere validation without an explicitly
authorized paid run. Publishing/merging this milestone is a separate handoff.
