# Aryan — Lead-Gen

Aryan's personal workspace for discovering companies and people, enriching contact details, verifying email/phone data, and exporting leads.

## Features

- Generic B2B business discovery followed by official-website enrichment.
- Velit van/RV company discovery and a multi-location batch scheduler.
- Vento influencer discovery, social enrichment, scoring, and deduplication.
- Hunter company/contact search and optional company research reports.
- Bulk email/phone verification, JSON/CSV/XLSX exports, and optional Google Sheets persistence.
- Agent Studio backed by Firestore; optional Qdrant knowledge retrieval for research.

## Run locally

```powershell
python -m pip install -r requirements.txt
# On a fresh checkout only: Copy-Item .env.example .env
# Fill .env with your own credentials; keep existing configured .env files.
python -X utf8 -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://localhost:8000. API documentation is available at /docs.

## Lead quality checks

The main discovery pipeline checks official websites, category/location evidence, contact sources, and international phone formats before returning leads. Company inboxes are preserved; unknown people stay blank. `Needs_Review` means a company contact was found but a person or email deliverability remains unconfirmed. A successful website request is never counted as email verification. Phone validation confirms numbering format, not live ownership or reachability.

Generic and Velit now share the same bounded company engine. It discovers businesses, resolves official websites from relevant directory sections or named-business searches, and checks the companies themselves. Directory/publisher contacts never become the listed company's contacts. The crawler follows contact/location/team links, reads business-owned structured addresses and public team cards, pairs office contacts, and records published WhatsApp/social links. It does not infer WhatsApp availability from a phone number or generate employee email addresses.

HTTP requests retry transient failures, reuse page results and remain inside the run deadline. Once results start arriving, a run stops after 90 seconds without another verified business (`LEAD_SEARCH_IDLE_SECONDS`, 0 disables this) rather than spending the remaining budget on an unproductive tail. Public JavaScript shells can use a local Playwright browser (up to three sites per run); indexed official-site extraction provides an independent fallback. For Chromium, run `python -m playwright install chromium`. Windows can instead use installed Edge with `LEAD_BROWSER_CHANNEL=msedge`. Set `LEAD_RENDER_JS=false` to disable rendering. Challenge/login pages remain unavailable rather than being treated as scraped data.

Vento retains its pet-business/creator model and batch/CSV history support. Its website scraper shares structured-data and source extraction, follows several contact pages in parallel and validates redirect destinations before requesting them. Business contacts come from official pages. Creator searches prefer profile results, validate email syntax, and require explicit pet-niche/location evidence before a production run accepts them. Profile follower counts do not by themselves prove local relevance.

Generic and Velit searches persist incrementally, support refresh recovery/cancellation, and expose reported Tavily usage. Historical saved results are marked as predating the newer quality policy. Company search targets are 1–50 for Generic and 1–100 for Velit; Vento retains its 1–200 cap. Counts are targets: sparse markets, blocked sources, budgets and missing evidence produce explicit shortfalls. An incomplete provider usage report is a lower bound, not a claim of exact billing.

See [SCRAPING_UPGRADE_AUDIT.md](SCRAPING_UPGRADE_AUDIT.md) for this upgrade's confirmed defects and verification. Reproduce selected live API/export checks with `python -X utf8 -m scripts.verify_scraping_upgrade --case texas-rv --case velit-california --case accountants-london --case vento-grooming --case vento-creators --output exports/my-audit` (uses provider credits; refuses to overwrite previous runs). `LEAD_TEST_BROWSER=1` enables the optional real JavaScript-rendering integration test when running pytest.

Use `SaaS Development` for software agencies; `SaaS` searches for subscription products. The system can return fewer leads than requested when evidence is insufficient.

Run `python -X utf8 -m scripts.verify_lead_quality` for small live tests across three categories (uses configured API credits; sends no outreach). Results and a checked Excel workbook are saved locally under `exports/quality-audit/`. Run `python -X utf8 -m scripts.verify_lead_ui` against the local server for a browser/Excel regression check with synthetic data.

For the current persisted search API, start the server and run `python -X utf8 -m scripts.verify_pipeline_matrix`. It tests marketing in Mumbai, accountants in London, SaaS development in Delhi, and van/RV builders in Hawaii, requesting two leads per market. It saves raw job results, a summary, and a reopened/checked workbook under `exports/pipeline-audit/`. A sparse market can return a documented shortfall. This uses configured search/enrichment credits and sends no outreach. `python -X utf8 -m scripts.verify_lead_platform_ui` checks browser recovery, cancellation, mode routing, responsive layouts and Excel export using synthetic API responses.

Persisted searches and the Velit scheduler currently require **one long-running application worker**, a writable persistent `data/` directory, and persistent exports storage. In-process background jobs and local SQLite/JSON state are unsuitable for ephemeral serverless execution or multiple workers; use a shared durable queue and database before such deployments. Generic searches cap at 50 leads, two concurrent jobs and ten active/queued jobs. Query and time budgets are configurable with `LEAD_SEARCH_QUERY_BUDGET` and `LEAD_SEARCH_MAX_SECONDS`; transient safe reads retry once within the run deadline. Restarted searches retain saved results and become `interrupted`; they are not silently reissued against paid providers.

See [LEAD_PIPELINE_AUDIT.md](LEAD_PIPELINE_AUDIT.md) for architecture, root causes, fixes, and verification evidence.

The larger 15-per-market quality review is documented in [LEAD_15_QUALITY_AUDIT.md](LEAD_15_QUALITY_AUDIT.md). Use `--count 15` with the matrix verifier to test volume, `scripts.review_lead_quality` to capture independent official-source/contact evidence, and `scripts.build_quality_review_report` with explicit per-company manual decisions to export a reviewed workbook. Saved terminal results can be checked again with `--replay`, without restarting paid searches.

## Pages

| Page | Path |
|---|---|
| Dashboard / research agents | `/` |
| Lead generation | `/leads` |
| Batch scheduling | `/velit-batch-scheduler` |
| Bulk contact verification | `/email-verifier` |
| Agent Studio | `/studio` |
| Hunter search | `/hunter-search` |
| Company research (optional) | `/company-chat` |

Enable company research with `ENABLE_COMPANY_CHAT_INTEL=true`. Hunter and Vento have their own feature flags in `.env.example`.

## Your credentials

| Setting | Purpose |
|---|---|
| `GOOGLE_API_KEY` | Gemini reasoning, extraction, and optional knowledge embeddings |
| `TAVILY_API_KEY` | Web search and company/social discovery |
| `HUNTER_API_KEY` | Hunter search and verification |
| `APIFY_API_TOKEN` | Optional Instagram/TikTok enrichment |
| `FIREBASE_CREDENTIALS_PATH` | Your Firebase service-account file |
| `FIRESTORE_BUSINESS_ID` | Your workspace namespace; defaults to `aryan-lead-gen` |
| `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION` | Optional company/document knowledge search |
| `GOOGLE_CREDENTIALS_PATH`, `TODO_SHEET_ID` | Optional Google Sheets lead persistence |
| `APOLLO_API_KEY`, `GOOGLE_PEOPLE_API_TOKEN` | Optional Apollo and Google Contacts enrichment |
| `AGENTIC_CORE_API_KEY` | Your application API secret, required in production |
| `ALLOWED_ORIGINS`, `PUBLIC_BASE_URL` | Public deployment origin and URL |

The `TODO_*` names remain for compatibility with the shared lead spreadsheet store. They do not enable a separate task-management agent.

For Sheets, enable the Sheets API in your own Google project, create a spreadsheet in your account, share it with your service-account email as Editor, and set `TODO_SHEET_ID`. If using file credentials, leave `GOOGLE_SERVICE_ACCOUNT_JSON` and its base64 alternative blank. Enable Drive API only if using Drive features.

## Firestore

The backend reads and writes under:

```text
businesses/aryan-lead-gen/
  agents/{agent_id}
  workflows/{workflow_id}
  remote_tools/{tool_name}
  agent_directory/{agent_id}
```

Collections appear when the first document is written. Preview and initialize the included lead/research library:

```powershell
python -X utf8 scripts/seed_firestore.py --dry-run
python -X utf8 scripts/seed_firestore.py
```

The seed command skips existing documents unless `--force` is supplied. Restart the server after seeding, or use `POST /api/admin/reload` to reload definitions.

## API groups

- `/api/leads`: discovery, lead runs, contact enrichment, exports, and LinkedIn session setup.
- `/api/workflow` and `/api/agent`: lead/research workflows and tool-calling agents.
- `/api/email-verification`: workbook email/phone verification.
- `/api/velit-batch`: scheduling and batch exports.
- `/api/vento`: influencer discovery and imported-lead processing.
- `/api/hunter`: optional Hunter pipeline.
- `/api/admin`, `/api/directory`, `/api/studio`: Firestore definitions and Studio.
- `/api/blocks`: reusable LLM, knowledge retrieval, document analysis, JSON extraction, and audio transcription.

LinkedIn enrichment requires your own authorized session. The existing LinkedIn campaign HTML is an experimental preview with no campaign backend route; it is not a completed sending integration.

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -X utf8 -m pytest
```

Lead data, exports, `.env`, Firebase keys, and LinkedIn sessions are excluded from Git. Generic, Velit, and Vento pipelines share the same runtime infrastructure; keep their verification, scraping, document, and export dependencies installed.

Educational tutoring, student profiles, generated teaching images, support-ticket workflows, script-writing agents, and Aurika task-service integrations have been removed from the active project.
