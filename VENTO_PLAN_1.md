# Vento Plan 1 — Expanded Tavily Instagram + TikTok Lead Workflow

## Purpose

Extend the isolated Vento influencer pipeline so it can return substantially more usable leads when no paid social-data provider is configured and Tavily is the active discovery source.

This plan is additive. It does not replace or modify `VENTO_INFLUENCER_LEAD_PIPELINE_PLAN.md`.

## User Outcome

For a requested usable target such as 10 leads, the system must:

1. Search a much larger raw creator pool instead of searching only 10–20 results.
2. Search Instagram and TikTok deliberately and in balanced query groups.
3. Prefer creators with both platforms but accept either Instagram or TikTok when the creator otherwise qualifies.
4. Enforce the selected influencer type strictly. Pet mode must require real pet-content evidence.
5. Remove creators already present in the uploaded historical CSV/XLSX.
6. Return every usable A/B lead found, up to the requested target.
7. Report an honest shortfall when the target cannot be reached.
8. Keep C leads in the review filter instead of accepting unrelated creators.

## Problem in the Existing Fallback

- Tavily fallback is capped near 20 raw results.
- Six query loops are often insufficient for narrow locations.
- Queries do not reserve balanced capacity for Instagram and TikTok.
- The requested influencer type influences search text but is not a strict A/B qualification rule.
- Adjacent creators, such as general road-trip bloggers, can pass Pet Lifestyle as Level B.
- A usable target and raw-discovery target are treated as the same value in parts of the workflow.

## New Discovery Funnel

```text
Requested usable target: 10
              ↓
Raw target: 60–80 candidates
              ↓
Balanced Instagram + TikTok Tavily queries
              ↓
URL/handle normalization and historical deduplication
              ↓
Profile, email, location and niche verification
              ↓
Strict selected-type qualification
              ↓
Return up to 10 A/B leads
              ↓
If fewer exist, return every A/B lead and report the shortfall
```

## Configurable Tavily Budget

Add environment configuration:

```env
VENTO_TAVILY_MAX_QUERIES=12
VENTO_TAVILY_RESULTS_PER_QUERY=10
VENTO_TAVILY_RAW_CAP=100
VENTO_TAVILY_RAW_MULTIPLIER=8
VENTO_TAVILY_CROSS_PLATFORM_LOOKUPS=4
VENTO_TAVILY_RETRIES=3
```

Rules:

- `raw_target = usable_target × VENTO_TAVILY_RAW_MULTIPLIER` when no explicit raw target is supplied.
- Clamp raw target to `VENTO_TAVILY_RAW_CAP` for Tavily.
- Stop early once enough raw candidates exist to satisfy the usable target after verification.
- Never exceed `VENTO_TAVILY_MAX_QUERIES` primary/cross-platform query calls, excluding bounded retries.
- Use Tavily `basic` depth to control cost.
- Return partial results when Tavily quota or query limits are reached.

## Balanced Platform Queries

Every selected influencer type must generate both Instagram and TikTok searches.

### Pet Lifestyle

```text
site:instagram.com "dog mom" "Seattle" creator
site:tiktok.com/@ "dog mom" "Seattle" creator
site:instagram.com "pet creator" "Pacific Northwest" collaboration
site:tiktok.com/@ "pet creator" "Pacific Northwest"
"pet influencer" "Seattle" Instagram TikTok email
"dog parent creator" "Seattle" Linktree collaboration
```

### Gadget / Car Review

```text
site:instagram.com "car accessories reviewer" "Seattle"
site:tiktok.com/@ "car accessories" reviewer "Seattle"
site:instagram.com "car essentials" UGC creator
site:tiktok.com/@ "car essentials" UGC creator
```

### Lifestyle / PNW

```text
site:instagram.com "PNW lifestyle creator" "Seattle"
site:tiktok.com/@ "PNW lifestyle" creator "Seattle"
site:instagram.com "outdoor lifestyle" dog creator "Portland"
site:tiktok.com/@ "outdoor lifestyle" dog creator "Portland"
```

Query ordering must alternate platforms so the query budget cannot be exhausted by Instagram-only searches.

## Platform Extraction

For every Tavily result:

1. Inspect the result URL itself.
2. Inspect title and snippet text.
3. Extract Instagram URL/handle when present.
4. Extract TikTok URL/handle when present.
5. Extract YouTube as an optional third platform.
6. Preserve source URL and observed timestamp.
7. Deduplicate by normalized platform + handle.

Preferred result:

```json
{
  "instagram_handle": "@creator",
  "instagram_url": "https://instagram.com/creator",
  "tiktok_handle": "@creator",
  "tiktok_url": "https://tiktok.com/@creator"
}
```

Acceptable result:

```json
{
  "instagram_handle": "@creator",
  "instagram_url": "https://instagram.com/creator",
  "tiktok_handle": "",
  "tiktok_url": ""
}
```

or the inverse TikTok-only record.

## Cross-Platform Lookup

Reserve a small query budget for high-quality leads that have only one platform.

Examples:

```text
"creator display name" "instagram handle" TikTok
"tiktok handle" Instagram creator
```

Rules:

- Run only for top candidates with a stable name or handle.
- Limit with `VENTO_TAVILY_CROSS_PLATFORM_LOOKUPS`.
- Merge a discovered missing platform only when the handle/name evidence is consistent.
- Never reject an otherwise usable lead merely because the second platform is unavailable.

## Strict Selected-Type Qualification

### Pet mode

A/B requires at least one evidence-backed tag:

- Pet Creator
- Dog Parent
- Dog Trainer
- Pet Safety
- Repeated pet/dog content evidence

Road Trip / Camping, PNW Lifestyle, UGC Creator, or Product Reviewer alone is insufficient. Adjacent creators go to C unless pet evidence exists.

### Gadget mode

A/B requires Car Gadgets, Product Reviewer, Amazon Finds, automotive accessories, or equivalent evidence.

### Lifestyle mode

A/B requires Local Lifestyle, PNW Lifestyle, Outdoor Lifestyle, Road Trip / Camping, or equivalent evidence.

### All mode

Any of the three campaign archetypes may qualify.

The selected type must be passed into deterministic qualification. Gemini may interpret content but may not override missing evidence.

## Contactability Rules

### Level A

- Exact selected-type match
- Active creator profile
- Valid public business email
- Confirmed or likely target location
- Instagram or TikTok present

### Level B

- Exact selected-type match
- Active creator profile
- Instagram or TikTok DM path
- Confirmed, likely, or explicitly review-allowed uncertain location
- Verified email not required

Both platforms are preferred, but either one is sufficient.

### Level C

- Adjacent niche without exact selected-type evidence
- Private/rate-limited profile
- Unknown location
- Risky email with insufficient alternate evidence
- Ambiguous cross-platform identity

## Raw Target and Usable Target Separation

Update pipeline contracts:

```python
async def run(
    *,
    target_count: int = 10,       # usable A/B target
    raw_target: int | None = None, # candidates to discover before verification
    ...
)
```

Rules:

- `target_count` controls the maximum A/B results returned.
- `raw_target` controls bulk/provider/Tavily discovery volume.
- If `raw_target` is missing, calculate it from the configured multiplier.
- Bulk imports may supply more records than raw target; do not discard imported records before deduplication.
- Tavily discovery respects its separate raw cap.

## API and UI Behavior

Existing endpoints remain compatible.

- `/api/vento/search` calculates an expanded raw target automatically.
- `/api/vento/daily-run` passes both usable and raw targets explicitly.
- `/api/vento/discover-with-history` uses the old file only for deduplication, displays only new leads, and passes both targets.
- Selected export continues to combine unchanged old rows with selected new leads only.

Add response metrics:

```json
{
  "tavily_queries_used": 10,
  "tavily_raw_candidates": 74,
  "instagram_candidates": 42,
  "tiktok_candidates": 36,
  "both_platforms": 9,
  "usable_returned": 8,
  "requested_usable": 10,
  "shortfall": 2
}
```

The activity log must explain that Tavily expanded the raw pool and must not claim the target was guaranteed.

## Files to Change

| Action | File | Change |
|---|---|---|
| Modify | `core/services/vento/discovery.py` | Balanced Instagram/TikTok query pool and platform-specific shortfall queries |
| Modify | `core/services/vento/vento_lead_pipeline.py` | Separate targets, expanded fallback, cross-platform enrichment, metrics |
| Modify | `core/services/vento/qualification.py` | Strict requested-type A/B enforcement |
| Modify | `core/services/vento/verification.py` | Stronger pet/gadget/lifestyle evidence tags |
| Modify | `core/services/vento/daily_batch.py` | Pass usable target and raw target separately |
| Modify | `api/routes/vento_leads.py` | Pass raw target and expose Tavily/platform metrics |
| Modify | `ui/leadgen.html` | Show expanded fallback statistics and honest shortfall log |
| Modify | `.env.example` | Add Tavily expansion controls |
| Modify | `core/services/vento/README.md` | Document cost controls and removal |
| Add/Modify | `tests/test_vento_*.py` | Query balance, volume, strict niche, platform and target tests |

## Error Handling

| Situation | Behavior |
|---|---|
| Tavily key absent | Return no web results and report `tavily_not_configured` |
| Social provider absent | Activate expanded Tavily fallback |
| Tavily quota reached | Return all A/B leads accumulated so far |
| Only Instagram found | Keep lead if otherwise A/B |
| Only TikTok found | Keep lead if otherwise A/B |
| Neither platform found | Require another verified creator platform/contact or reject/review |
| Pet selected but only travel evidence | Level C or Rejected, never A/B |
| Requested 10 but found 8 | Return 8 and report shortfall 2 |
| Old file contains creator | Exclude creator from new website results |

## Tests

Required automated coverage:

- Query pool includes Instagram and TikTok.
- Query ordering alternates platforms.
- Tavily can collect more than 20 raw candidates.
- Target 10 can inspect a configured 60–80 raw pool.
- Pipeline stops returning at 10 usable leads.
- Pipeline returns all 7 or 8 when target 10 cannot be reached.
- TikTok-only exact pet creator can qualify B.
- Instagram-only exact pet creator can qualify B.
- Road-trip creator without pet evidence cannot qualify A/B in pet mode.
- Road-trip creator with real dog-parent evidence may qualify.
- Historical-file deduplication remains active.
- Query count and platform metrics are returned.
- Missing Tavily/provider keys do not break startup or bulk ingestion.

## Acceptance Criteria

- A request for 10 usable leads searches a configurable larger raw pool.
- Tavily is no longer hard-capped at 20 raw candidates.
- Instagram and TikTok receive deliberate query coverage.
- Either Instagram or TikTok is sufficient for a usable DM-ready lead.
- Pet mode never returns a general travel creator as A/B without pet evidence.
- All usable results found are returned when the target is not reached.
- Shortfall, query usage, and platform counts are visible in response metadata.
- Existing old-file selection/export behavior remains unchanged.
- `ENABLE_VENTO_PIPELINE=false` continues to remove all Vento routes.
- The complete project test suite passes.
