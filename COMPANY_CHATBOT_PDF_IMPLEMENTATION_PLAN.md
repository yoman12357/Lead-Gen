# Company Chatbot + Hunter Leads + PDF Export Implementation Plan

## Goal

Build a new ChatGPT-style dashboard where a user asks about a company and gets:

1. Structured company intelligence from your existing web scraping capabilities.
2. 7-8 company-relevant leads from your existing Hunter pipeline.
3. A downloadable PDF report for that specific run using a top action button.

This plan is additive only and does not modify existing working pipelines (Hunter search, normal lead verification, existing dashboards).

## Scope (Additive)

- Add a new page (chat-style UI).
- Add a new API route group for company-intel chat runs.
- Reuse existing scraping + contact extraction logic.
- Reuse existing Hunter pipeline for lead retrieval.
- Add PDF report generation and a top button to download for current run.

## Non-Goals

- No replacement of current /hunter-search flow.
- No breaking changes to /api/hunter/search.
- No changes to existing lead verification flow behavior.
- No deletion of existing code paths; only additive wiring for this feature.

## Add-Only + Safe Removal Strategy (Important)

To ensure you can remove this feature in the future without breaking original pipelines:

- Keep all existing routes, services, and UI files unchanged.
- Add only new files/modules for company-chat and PDF reporting.
- Use isolated route prefixes and isolated UI page:
  - /company-chat
  - /api/company-intel/\*
- Gate all new registrations behind one feature flag:
  - ENABLE_COMPANY_CHAT_INTEL=true/false
- Never reuse existing route paths for this feature.
- Never delete existing handlers when introducing this feature.

Removal plan (future):

1. Set ENABLE_COMPANY_CHAT_INTEL=false (instant disable, no code removal required).
2. Remove new route registration block only for company-intel routes.
3. Remove new UI route/page link entries only for company-chat.
4. Optionally archive/delete only newly added company-intel files.

Because this is route-isolated and flag-gated, original Hunter and normal pipelines continue working unchanged.

## High-Level Architecture

- UI page: /company-chat
- API endpoint: POST /api/company-intel/chat
- API endpoint: GET /api/company-intel/run/{run_id}/pdf
- Service layer:
  - Company intel aggregation service (scrape + normalize)
  - Hunter lead fetch adapter (company-focused)
  - PDF report builder

## Isolation Rules

- New code lives under dedicated modules only (company-intel namespace).
- Existing Hunter route/module stays untouched; called as a dependency only.
- Existing scraping logic stays untouched; wrapped by a new orchestrator service.
- No refactor of original pipeline internals in this phase.

## Backend Plan

### 1) New Route Module

Create a new route file under API routes (example name: company_intel.py) with:

- POST /chat
  - Input: prompt, lead_count (default 8), optional session_id.
  - Output: run_id, assistant_message, company_profile, leads, steps, warnings.
- GET /run/{run_id}/pdf
  - Returns a PDF file for that run.

### 2) Request Parsing

From prompt, extract:

- company_name (required)
- optional location hint
- optional industry hint

If company_name cannot be confidently extracted:

- Return assistant message asking follow-up clarification.

### 3) Company Intelligence Collection (Reuse Existing Logic)

Use existing website/contact extraction capabilities to gather:

- company_name
- website
- short summary
- services/products
- emails
- phones
- social handles/links (LinkedIn, Instagram, Facebook, X, YouTube where found)
- source URLs

Normalize into a stable schema:

- company_profile.summary
- company_profile.services[]
- company_profile.contacts (emails, phones)
- company_profile.social_links[]
- company_profile.source_urls[]

### 4) Hunter Leads Integration (Reuse Existing Pipeline)

Run Hunter lookup targeted for the same company/domain and cap results to 7-8 by default.
Lead shape should include:

- person name
- title/role
- email
- phone
- verification status
- quality score
- source URL

Behavior rules:

- If fewer leads exist, return available leads + warning.
- Do not fail entire run if Hunter returns partial results.

### 5) Run Persistence for PDF

Store each run payload in lightweight run storage (existing data store pattern or JSON persistence) keyed by run_id:

- user prompt
- timestamp
- company_profile
- leads
- metadata
- warnings/errors

This enables deterministic PDF download per run.

### 6) PDF Generation Endpoint

GET /api/company-intel/run/{run_id}/pdf

- Build PDF with sections:
  - Run header (date/time, company, prompt)
  - Company overview
  - Services
  - Contact details
  - Social links
  - Leads table (7-8 contacts)
  - Source URLs
- Filename pattern:
  - company*intel*<company*slug>*<yyyy-mm-dd>.pdf

Recommended Python library:

- reportlab (preferred for controlled table layout)
  Alternative:
- WeasyPrint if HTML-to-PDF styling is preferred.

## Frontend Plan (ChatGPT-Style)

### 1) New UI Page

Create new page (example: ui/company_chat.html) with:

- Left: conversation/run list (basic for now)
- Center: chat thread
- Bottom: prompt composer

### 2) Top Actions (Required New Addition)

In top header area of the chat result panel add:

- Download PDF button
- Button disabled until a run finishes successfully and run_id exists

Button behavior:

- Click triggers GET /api/company-intel/run/{run_id}/pdf
- Browser downloads the report for that exact run

### 3) Response Rendering

Assistant response blocks:

- About company
- Services
- Contact details
- Social profiles
- Lead contacts table (7-8)

Also show:

- run status
- warnings/fallback notes
- source links

### 4) UX Rules

- Show loading state while run executes.
- Keep run_id in client state for PDF button.
- If no run selected, PDF button stays disabled.
- If PDF endpoint fails, show inline error toast/log card.

## API Contract Draft

POST /api/company-intel/chat
Request:

- prompt: string
- lead_count: number (optional, default 8)
- session_id: string (optional)

Response:

- success: boolean
- run_id: string
- assistant_message: string
- company_profile: object
- leads: array
- warnings: array
- errors: array
- steps: array

GET /api/company-intel/run/{run_id}/pdf
Response:

- application/pdf file stream
- 404 if run_id missing

## Error Handling

- Missing company in prompt: ask clarifying question.
- Website scraping fail: still return Hunter leads if possible.
- Hunter fail: still return company profile + warning.
- PDF fail: keep chat results and show download error only.

## Security + Validation

- Sanitize URLs before rendering.
- Escape untrusted text in UI rendering.
- Validate lead_count range (1-15, default 8).
- Limit PDF generation to existing run_id records.

## Rollout Steps

1. Add new backend routes and service skeleton.
2. Add feature flag ENABLE_COMPANY_CHAT_INTEL and gate new route/page registration.
3. Wire route in main app and page route /company-chat (inside feature-flag block only).
4. Build chat UI with top Download PDF button.
5. Integrate scraping aggregation.
6. Integrate Hunter company-focused lead fetch.
7. Add run persistence and PDF generation endpoint.
8. Add tests and smoke verification.

## Rollback Checklist

1. Turn off ENABLE_COMPANY_CHAT_INTEL and restart service.
2. Verify /company-chat returns 404/disabled while existing dashboards still work.
3. Verify /api/hunter/search and existing lead verification endpoints are unchanged.
4. Remove only company-intel-specific files if permanent removal is desired.

## Test Checklist

- Prompt: "I want details about Stripe"
- Prompt: "Show details and leads for HubSpot"
- Verify company summary + services + contacts + social links returned.
- Verify 7-8 leads default.
- Verify Download PDF button appears at top and downloads correct run report.
- Verify behavior when Hunter returns partial/no leads.
- Verify behavior when scraping yields limited contact data.

## Acceptance Criteria

- New /company-chat page works independently.
- Existing hunter_search and normal verification flows remain unchanged.
- Chat run returns structured company details plus company-relevant leads.
- Top button downloads PDF for the same run.
- No regression in existing UI pages and existing API routes.
