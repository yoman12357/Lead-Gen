# Lead pipeline audit — 22 October 2026

## Scope and existing architecture

The working tree already contained extensive changes before this audit. Those changes are preserved. No AGENTS.md was found in the repository.

- FastAPI (`api/main.py`) serves standalone HTML and REST routes. Startup initializes Gemini, optional Qdrant, Firestore configuration, optional Google Sheets, tools, workflow agents, the Velit scheduler, and generic search jobs.
- Generic discovery: `ui/leadgen.html` + `ui/assets/lead-search.js` → `/api/lead-searches` → `LeadSearchJobs` (SQLite, two running searches, ten active/queued) → `ProductionLeadPipeline.run` → `LeadSearchEngine`.
- The engine expands category/location queries, searches Tavily with DuckDuckGo HTML fallback, deduplicates website hosts, fetches official home/contact/about pages, rejects listing sites, checks business/location evidence, extracts sourced contacts, checks email MX and phone numbering, scores leads, and emits progress snapshots. It bounds queries, concurrency, pages and elapsed time.
- Legacy `/api/workflow/run` dispatches generic directory workflow IDs to the same production facade. YAML split workflows use the agent orchestration engine and registered tools.
- Velit has a separate `VelitLeadPipeline` subclass for van/RV discovery, enrichment, shortfall searches and partial recovery. Its batch scheduler persists local JSON and exports workbooks.
- Vento has separate influencer ingestion/discovery, Apify/social enrichment, follower verification, deduplication, qualification and workbook exports.
- Results remain in SQLite for generic searches. Browser JSON/CSV/XLSX export is local; explicit `/api/leads/export` uses `LeadService`, quality gates, deduplication and Google Sheets. Automatic Sheets saving is disabled in the existing UI.
- Gemini is used by legacy/specialized enrichment and agents; the current generic engine uses deterministic extraction/scoring. Firestore holds definitions, not generic search jobs. Qdrant is optional research retrieval.

## Prioritized findings before implementation

| Priority | Status | Root cause and impact |
|---|---|---|
| P1 | Confirmed by reproduction | Geography checks discard everything after the first comma. London, Ontario passes London, UK; Paris, Texas passes Paris, France. |
| P1 | Confirmed by reproduction | `ProductionLeadPipeline` eagerly constructs Tavily. Missing credentials throw before the independent HTML fallback can run. |
| P1 | Confirmed by inspection; regression pending | Batch `gather` only accepts results after every company finishes. A deadline/cancellation can discard already finished company results from that batch. |
| P1 | Confirmed by inspection | The added browser click handler routes both generic and Velit into the generic API. Keyboard Enter calls the old workflow handler, so the same form behaves differently by input method. |
| P2 | Confirmed by inspection | SQLite connection context managers commit/rollback but do not close connections. Restart changes the status column without updating the saved result's terminal metadata. Exceptions are swallowed without diagnostic logging. |
| P2 | Confirmed by inspection | Generic page fetches and provider calls have no bounded transient retry. A single temporary 429/503/transport failure can discard a valid company. |
| P2 | Confirmed by inspection; regression pending | An email with a null MX record is treated as having a mail server, and only the first extracted email is checked. A dead first inbox can hide a usable second inbox. |
| P2 | Investigated; not reproduced | Contact-form-only leads remain usable through both the quality gate and export ranking. Regression coverage confirms compatibility; no gate rewrite was needed. |
| Deployment | Known limitation | SQLite jobs and the JSON scheduler are single-process local workers; multiple ASGI workers or ephemeral hosting need shared durable queue/storage. Do not deploy multiple workers against these stores. |
| Quality | Known limitation | Generic target_role is recorded but does not establish a named decision maker. MX and phone-format checks do not prove mailbox delivery, phone ownership or reachability. |
| Integration | Unverified | Sheets is not configured locally. Live Sheets persistence cannot be certified without a sheet. Production browser API-key provisioning also requires a deployment-specific auth flow. |

Baseline: all 166 collected test cases reached completion, but pytest exited with a Windows temp-directory cleanup PermissionError. Rerun with a unique workspace-local basetemp before reporting a pass.

## Implementation checklist

- [x] Inspect architecture, dependencies, entry points and existing tests before modifying source.
- [x] Record confirmed findings, uncertainties and a bounded implementation plan.
- [x] Add regressions for missing credentials, qualified geography, partial batches, job recovery and retries.
- [x] Preserve missing-key fallback and enforce all requested geographic qualifiers.
- [x] Checkpoint individual completed companies, add bounded transient retries and diagnostic logs.
- [x] Close SQLite connections and keep recovery/cancellation status and metadata consistent.
- [x] Keep generic and specialized browser routing consistent for click and Enter; preserve Vento's 200-lead input cap.
- [x] Validate email selection/null MX and contact-form export compatibility.
- [x] Run full automated suite, API-to-export integration and browser checks.
- [x] Run small live cases for different businesses and places; save measured outcomes, shortfalls and limitations.

## Verification criteria

Existing working tests must remain green. Regressions must fail against the original behavior and pass after fixes. Deterministic API tests must exercise real extraction/scoring/deduplication with controlled provider and DNS responses. Live tests must save provider/stage counts, observed leads and evidence. A shortfall must remain explicit; no fabricated contacts or geographic broadening to fill a target. External quota/network/configuration failures are reported as limitations, not success.

## Implemented root-cause fixes

1. Geography preserves comma-separated country/state qualifiers and their aliases in the local address context. Grouped international phone numbers no longer count as postal codes. Wrong-country and adjacent-office examples have regressions.
2. Tavily permits deferred missing-key errors for the production pipeline, allowing the independent HTML fallback. Existing strict clients retain their default behavior. Failed providers are distinguished from successful searches with no matches.
3. Companies are accepted and persisted individually. Reaching the target cancels and awaits outstanding enrichment tasks; deadlines retain completed peers. Checked-target counts now represent completed checks rather than scheduled tasks.
4. Transient safe reads retry once for transport failures, 408/429 and selected 5xx responses, within the overall time budget. Page retries honor a bounded numeric Retry-After. Permanent failures do not retry. Logs include safe error types, company domains and job IDs.
5. SQLite connections close deterministically. Restart status and snapshot stage/completion/stop reason are updated together; saved leads remain available. Job failures are logged.
6. Browser click and Enter use the persisted API for generic searches and the existing specialized workflow for Velit. Vento remains on its original handler and retains its input cap. Specialized rendering/export behavior is preserved.
7. Published fallback inboxes are considered when the first email is definitively invalid. Discovery and explicit email verification reject null MX records. DNS outages remain unconfirmed instead of becoming false invalid results. DNS resolution is bounded.
8. Live Hawaii output reproduced `%20hisurfcampers@gmail.com` from an encoded mailto URI. Mailto payloads now decode before extraction; percent-encoded whitespace and subject parameters cannot become part of the mailbox. Regressions cover public inboxes on homepages as well as contact pages.
9. Live Mumbai output reproduced a directory (Joonsquare) contributing its own admin email for another listed company. Listing detection now recognizes an external official-website relationship and claim/add-business markers anywhere in the page, rather than adding only another blocked hostname. Cross-domain redirects on secondary contact pages are excluded from company evidence.
10. Sheets duplicate identity normalizes protocol-less, www and bare website hosts, independently of company branding or inbox changes. Legacy workflow search fields are validated before providers initialize, returning 422 for missing/oversized fields.

## Automated verification

- Initial regression run before fixes: **9 failed, 4 passed**, confirming the discovered geography, construction, batch-loss, recovery, retry and null-MX bugs.
- Final full suite: `python -X utf8 -m pytest -q --basetemp tmp_audit_complete_suite` → **202 passed in 35.82 seconds**, clean exit.
- The new reliability suite adds 36 cases. Controlled integration tests use the actual HTTP fetch, extraction, scoring, SQLite jobs, API polling and export service for Mumbai marketing, London accounting, Delhi SaaS development and Hawaii van/RV builders. They also verify duplicate export suppression, source evidence and no invented people/SMTP verification. Geographic qualifiers distinguish uppercase `US` from the pronoun in “contact us.”
- Browser contract: `python -X utf8 -m scripts.verify_lead_platform_ui` → jobs, refresh recovery, cancellation, responsive widths, click/Enter routing, preserved Velit workflow and a reopened 15-row XLSX export passed; zero page errors. Browser responses are synthetic and consume no search credits. Vento services retain their existing passing automated coverage; no live social/Apify or outreach test was performed.
- Contact-form-only compatibility was investigated and passes; no speculative export-gate change was made.

## Live verification and limits

The live audit calls the running FastAPI search API with configured providers, polls persisted jobs, checks result invariants, writes raw JSON and exports/reopens an XLSX workbook. It sends no outreach. Final evidence is recorded under `exports/pipeline-audit/verified/`; earlier `pipeline-audit/` and `pipeline-audit/final/` runs are intermediate diagnostic evidence and include the issues found during review.

| Business / place | Requested | Returned | Run seconds | Outcome |
|---|---:|---:|---:|---|
| Digital Marketing / Mumbai | 2 | 2 | 18.8 | Completed; target reached |
| Accountants / London, UK | 2 | 2 | 21.8 | Completed; target reached |
| SaaS Development / Delhi | 2 | 2 | 11.5 | Completed; target reached |
| Van Upfitters / RV Builders / Hawaii | 2 | 1 | 110.4 | Partial; search exhausted; shortfall 1 |

All four runs used Tavily and passed saved-result/source/contact/deduplication checks. Seven lead rows were exported and the workbook reopened with the expected eight rows including the header. The Hawaii contact is `hisurfcampers@gmail.com`, with the URI-encoded whitespace removed. The intermediate directory record is rejected by the final listing policy. No SMTP verification is asserted. Times describe individual job runtime, excluding queue wait; they are observations, not performance guarantees.

Google Sheets is not configured (`TODO_SHEET_ID` absent), so its actual remote write cannot be certified. Storage/export integration and deduplication are tested with controlled storage. MX is not delivery confirmation, phone numbering is not reachability, and a site's own presence statement is not independent physical-address verification. Search results vary over time and sparse markets can produce explicit shortfalls.

Deployment limitations remain architectural choices requiring a separate deployment scope: a shared durable queue/database for multiple workers or serverless hosting, and an authenticated browser session flow for public production use. The current local single-worker configuration is the environment verified here. The UI does not silently invent a named decision maker from a company inbox; target-role/person enrichment is not certified by these company-discovery tests.
