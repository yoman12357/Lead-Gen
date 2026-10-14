# Vento Plan 2 — Quality-First Social, Contact, Follower and Product-Fit Workflow

## Purpose

Upgrade the isolated Vento influencer workflow so exported leads are genuinely useful for outreach, not merely social URLs found by search.

This plan is additive and removable. It does not replace or modify:

- `VENTO_INFLUENCER_LEAD_PIPELINE_PLAN.md`
- `VENTO_PLAN_1.md`
- Generic lead generation
- Velit Campaign
- Existing old-file history, selection and export behavior

The upgrade will be controlled by a Vento-only feature flag and implemented in separate quality/enrichment modules where practical.

Plan 2 is yield-optimized. It must not attempt to solve quality by multiplying the requested target into a much larger fixed raw target. It must make each discovery query and each candidate produce more usable evidence before requesting additional candidates.

## Product Context

Vento is a smart cooling fan for parked cars, with a strong use case around pet comfort and pet safety.

The best creator is not just a generic influencer. The strongest campaign fit is a creator whose public content shows one or more of these combinations:

1. Pets plus cars, heat, cooling or pet safety.
2. Dog-parent content plus road trips, camping or outdoor travel.
3. Established pet content suitable for a product demonstration.
4. Car-accessory or automotive-product content with genuine pet ownership.
5. A capable UGC creator who can produce Vento advertising, even if they do not provide influencer distribution.

Marketing copy must not suggest that Vento makes it safe to leave a pet unattended in a dangerous hot-car situation.

## Workbook Audit That Motivates This Plan

The reviewed Vento workbook contained 42 Level B rows, but:

- Zero rows had a follower count.
- Only one row had a valid email.
- Thirty-three rows had unknown locations.
- Only eight Instagram profiles were HTTP verified.
- Thirty-four TikTok profiles were only search-indexed/rate-limited.
- No row contained both Instagram and TikTok.
- Some creator names were video titles instead of creator identities.
- A directory page, corporate account, possible stores and aggregators were accepted.
- Location parsing produced false states such as `IN`, `ME` and `ID` from ordinary text.
- Generic UGC, pet-only and car-only leads received similar Level B treatment.

The workflow therefore needs a strict distinction between:

- Discovered candidate
- Real creator identity
- Product-relevant creator
- Contactable creator
- Verified influencer

## User Outcome

For every accepted lead, the user must receive:

- A canonical Instagram profile, canonical TikTok profile, or both.
- A clear profile status that distinguishes verified, indexed, private, rate-limited and unknown.
- A Vento-specific product-fit level and evidence.
- A quality level with human-readable reasons.
- Public business email when available, with source and verification status.
- Follower count when available, with source and evidence status.
- Explicit location evidence when available.
- A real creator name or handle, not a post/video title.
- A source URL and evidence timestamp.

The system must return an honest shortfall instead of lowering standards silently.

## Yield-Optimized Strategy

The primary optimization goal is:

```text
usable A/B leads returned ÷ unique raw candidates inspected
```

The secondary optimization goals are:

```text
usable leads per Tavily search
enriched fields per Tavily search
verified identities per profile fetch
```

Rules:

1. Do not calculate a large fixed raw target from the usable target.
2. Discover candidates in a streaming sequence, one high-precision query group at a time.
3. Normalize and reject bad entities immediately, before any enrichment expense.
4. Enrich a promising candidate from its existing profile, snippet, website and bio-link before running another Tavily search.
5. Reuse one search response for identity, platform, niche, location, email and follower evidence whenever those fields are present.
6. Search for a second platform only when the first platform cannot already support a usable lead or when the identity match is likely to succeed.
7. Prefer provider bulk endpoints for multiple handles instead of one provider request per creator.
8. Cache creator evidence so repeated daily searches do not spend credits rediscovering the same profile.
9. Measure which query templates produce usable leads and prioritize the highest-yield templates during the same run and future runs.
10. Stop discovery as soon as the requested usable target is satisfied.
11. If high-precision sources are exhausted, return an honest shortfall instead of switching automatically to broad low-quality searches.

Plan 2 must not introduce a fixed daily credit cap, fixed per-run credit cap, fixed raw multiplier or fixed enrichment-count cap. Provider rate limits and actual provider quota exhaustion still apply, but they are external availability constraints rather than artificial Plan 2 limits.

The legacy `raw_target` API field remains accepted for backward compatibility. In Quality V2 it is treated only as an optional legacy hint and not as the main discovery strategy.

## Non-Negotiable Acceptance Rules

An A or B lead must have at least one of:

- Canonical Instagram profile URL and normalized Instagram handle.
- Canonical TikTok profile URL and normalized TikTok handle.

The following cannot qualify as A or B without a separately confirmed creator profile:

- Search-result list pages
- “Top influencer” directories
- Individual posts with no extractable profile identity
- Corporate brands
- News or media publications
- Product stores
- Repost/aggregation accounts
- Generic agencies or social-media managers

Either Instagram or TikTok is sufficient. Both platforms increase confidence but are not mandatory.

## Quality-First Funnel

```text
Requested usable target
        ↓
Highest-yield product-intersection query
        ↓
Canonical social-profile extraction
        ↓
Creator/entity exclusion gate
        ↓
Same-run and historical deduplication
        ↓
Vento product-fit evaluation
        ↓
Location, email, follower and second-platform enrichment
        ↓
Evidence-preserving profile verification
        ↓
Strict A / B / Review / Rejected classification
        ↓
If target is incomplete, choose the next query from observed yield
        ↓
Return requested target or an honest shortfall
```

## Vento Product-Fit Model

Add deterministic `product_fit_level`, `product_fit_score`, `product_fit_tags` and `product_fit_evidence` fields.

### Fit P1 — Excellent

Examples:

- Dog/pet creator discussing hot cars, cooling or pet safety.
- Pet creator showing car travel with their animal.
- Dog-parent creator discussing summer heat in a vehicle.

Suggested score: 85–100.

### Fit P2 — Strong

Examples:

- Dog-parent plus road-trip/camping/outdoor content.
- Pet creator with product-review or UGC experience.
- Automotive-accessory reviewer with explicit pet ownership.

Suggested score: 70–84.

### Fit P3 — Relevant

Examples:

- Established pet creator without car/heat evidence.
- Personal car-gadget reviewer with strong product-demonstration ability.
- Paid UGC creator with explicit pet or automotive evidence.

Suggested score: 55–69.

### Fit P4 — Weak / Review

Examples:

- Generic UGC creator.
- Car content with no evidence of product reviews or pet ownership.
- General lifestyle creator with no pet, car, heat or travel evidence.

Suggested score: 25–54.

### Fit P5 — Unrelated / Reject

Examples:

- Directory, store, corporate brand or media account.
- Content unrelated to pets, vehicles, travel, cooling or UGC production.

Suggested score: 0–24.

Gemini may summarize supplied evidence, but it may not invent or override missing product-fit evidence. Deterministic tags and source snippets remain authoritative.

## Creator Identity and Canonical Profile Extraction

Add a Vento-only identity normalizer that:

1. Extracts a handle from the result URL, title and snippet.
2. Converts post/reel/video URLs to canonical profile URLs when the handle is known.
3. Removes query strings and locale parameters.
4. Rejects reserved platform paths such as explore, reels, tags, videos and search.
5. Uses the handle as the fallback creator name when a real display name is unavailable.
6. Rejects names that look like article/video titles.
7. Stores the original discovery URL separately from the canonical profile URL.

Example:

```json
{
  "creator_name": "Luv N The Cru",
  "tiktok_handle": "@luvnthecru",
  "tiktok_url": "https://www.tiktok.com/@luvnthecru",
  "discovery_source_url": "https://www.tiktok.com/@luvnthecru/video/7550392705004604703",
  "identity_confidence": "high"
}
```

## Creator-Type Exclusion Gate

Add deterministic signals for:

- `individual_creator`
- `pet_creator`
- `ugc_creator`
- `review_creator`
- `store_or_shop`
- `directory_or_listicle`
- `corporate_brand`
- `media_or_publisher`
- `agency_or_manager`
- `unknown_entity`

Rules:

- Stores, directories, corporate brands and media accounts are rejected from influencer output.
- Agencies and UGC studios may enter a separate `Paid UGC` review category.
- Unknown entities remain Review until a personal creator identity is established.
- `Rover`, a list article and a product storefront must not be treated as equivalent to an individual creator.

## Product-Specific Discovery Queries

Prioritize intersection queries before broad category queries.

Each query should be designed to return a profile plus multiple useful evidence fields. For example, a single query can include the creator archetype, location, platform and collaboration/contact intent. The pipeline should not automatically run separate discovery, email, location and follower queries for every candidate.

### Pet + Vehicle + Heat

```text
site:instagram.com "dog mom" "car" "Los Angeles" creator
site:tiktok.com/@ "dog in car" "SoCal heat"
site:instagram.com "pet safety" "hot car" creator
site:tiktok.com/@ "keeping my dog cool" car creator
```

### Pet + Travel

```text
site:instagram.com "dog road trip" creator "Los Angeles"
site:tiktok.com/@ "dog mom" roadtrip camping creator
site:instagram.com pet travel creator collaboration
```

### Pet + UGC / Reviews

```text
site:instagram.com pet UGC creator email
site:tiktok.com/@ pet product review creator
"pet influencer" media kit Instagram TikTok
```

### Automotive + Pet Ownership

```text
site:instagram.com car accessories reviewer "dog mom"
site:tiktok.com/@ car gadgets "dog owner"
```

Broad pet, car and UGC searches should not run merely to increase the row count. They may run only when their historical usable-lead yield is acceptable for the selected campaign type.

### Adaptive Query Selection

After each query, calculate:

- Unique canonical profiles returned
- Individual creators returned
- P1/P2/P3 product-fit creators returned
- Usable A/B leads returned
- Emails, follower counts and second platforms recovered
- Duplicate, store, directory and irrelevant-result rate

The next query is selected by expected usable yield rather than a fixed query order. Low-yield templates are deprioritized immediately. High-yield location/archetype combinations are reused with controlled keyword variation.

Do not rerun a query whose normalized result set is substantially identical to an earlier query.

## Cross-Platform Enrichment

For the highest product-fit single-platform candidates, run an adaptive secondary search only when it can materially improve contactability or identity confidence.

Examples:

```text
"@instagram_handle" TikTok
"@tiktok_handle" Instagram
"creator display name" Instagram TikTok
```

Merge platforms only when at least two identity signals agree:

- Matching normalized handle
- Matching display name
- Matching website/Linktree
- One profile links to the other
- Matching distinctive biography text

Do not merge profiles from display-name similarity alone.

Cross-platform enrichment has no new fixed Plan 2 lookup count. It is driven by candidate value and stops naturally when the usable target is complete or no unresolved high-value candidates remain.

## Public Email Enrichment

Email enrichment order:

1. Social search snippet or provider biography.
2. Creator website.
3. Linktree/Beacons/bio-link page.
4. Contact or collaboration page.
5. Media kit.
6. Public management or agency contact.

Store:

- `email`
- `email_verification_status`
- `email_source_url`
- `email_source_type`
- `email_is_management`
- `email_last_checked_at`

Rules:

- Only public business/collaboration emails are collected.
- Masked strings such as `****@web.detiktok` are invalid.
- Syntax, disposable-domain and DNS/MX checks are preserved.
- Management emails do not merge unrelated creators.
- Failure to find an email does not reject an otherwise strong DM-ready Level B lead.
- Fetch a known website, contact page or bio-link directly before spending another Tavily search.
- Do not repeat email discovery when cached evidence is still current.
- When Tavily is required, use one creator-enrichment query that can also recover the second platform, location and follower evidence.

## Follower Count Enrichment

Follower count source priority:

1. Configured social-data provider.
2. Provider-returned platform metadata.
3. Explicit current search snippet that names the profile and follower count.
4. Historical import value, labeled imported/unverified.
5. Unknown.

Store:

- `follower_count`
- `follower_status`
- `follower_source_url`
- `follower_observed_at`
- `follower_tier`

Allowed statuses:

- `provider_verified`
- `provider_reported`
- `search_observed`
- `imported_unverified`
- `unknown`

Rules:

- Never manufacture or estimate a count from likes, views or rank.
- Never label unknown follower data as a verified tier.
- Enforce a requested follower tier only when the count has acceptable evidence.
- If no paid provider is configured, preserve the lead and show `Follower count unavailable`.
- Prefer one provider bulk lookup for a group of qualified handles instead of one call per lead.
- Do not use a separate Tavily follower query when the discovery/enrichment response already contains explicit follower evidence.

Optional provider keys remain environment-driven and are never hard-coded.

## Location Verification Rewrite

Replace the unsafe standalone two-letter state-code extraction with contextual patterns.

Accept evidence such as:

- `Los Angeles, CA`
- `Seattle, WA`
- `Based in Portland, Oregon`
- `SoCal creator`
- Provider-supplied country/state fields

Do not treat these as location evidence:

- `animal ID A2257886`
- `helping you turn content into income`
- `join me as I...`
- Arbitrary uppercase/lowercase two-letter words

Location rules:

- Named cities and full state names are strongest.
- State abbreviations require comma/address/based-in context.
- Search query location is a target, not creator evidence.
- Conflicting locations produce `location_confidence=conflicting` and Review.
- Strict U.S. mode rejects confirmed non-U.S. creators and moves unknown-location creators to Review.
- When Strict U.S. mode is off, global creators may qualify if the entered location/country rules permit them.

## Quality Levels

### Level A — Outreach Ready

Required:

- Canonical Instagram or TikTok profile.
- Individual creator identity.
- Profile verified active.
- Product fit P1, P2 or strong P3.
- Valid public business/management email.
- Confirmed or likely allowed location.
- Follower count with provider/search evidence when a follower tier was requested.
- No critical safety, entity or location exclusions.

### Level B — DM Ready

Required:

- Canonical Instagram or TikTok profile.
- Individual creator identity.
- Verified-active or clearly search-indexed profile.
- Product fit P1, P2 or P3.
- Usable DM path.
- No confirmed location contradiction.
- Follower count and email may be unavailable.

Strict U.S. behavior:

- Confirmed/likely U.S. location may qualify B.
- Unknown U.S. location goes to Review, not B.

### Review

Use Review for:

- Unknown or conflicting location.
- Profile found only through one post with weak identity.
- Generic UGC or car-only content.
- Missing product evidence.
- Agency/manager rather than creator.
- Possible store/aggregator.
- Ambiguous cross-platform match.
- Requested follower tier without follower evidence.

### Rejected

Reject:

- Directory/listicle.
- Corporate brand or publication.
- Store or product-only account.
- Confirmed outside allowed geography.
- No Instagram or TikTok profile.
- Unrelated content.
- Invalid/fabricated identity.
- Duplicate creator.

## Separate Influencer and Paid UGC Outputs

The UI should distinguish:

- `Influencer — Audience Distribution`
- `Paid UGC — Content Production`

A generic UGC creator with a valid email can be useful for producing an advertisement, but must not be represented as a verified influencer with an established audience when follower data is absent.

## Quality Reasons and Evidence

Every result should include:

```json
{
  "quality_level": "B",
  "product_fit_level": "P1",
  "product_fit_score": 92,
  "quality_reasons": [
    "canonical_tiktok_profile",
    "pet_plus_vehicle_heat_evidence",
    "dm_available",
    "follower_count_unavailable"
  ],
  "review_reasons": [],
  "evidence_urls": []
}
```

The UI and export must expose the reasons instead of relying only on a numerical score.

## API Contract

Extend Vento requests with optional fields:

```json
{
  "quality_mode": "strict",
  "minimum_product_fit": "P3",
  "include_paid_ugc": true,
  "enrich_cross_platform": true,
  "enrich_email": true,
  "enrich_followers": true
}
```

Defaults:

- `quality_mode=strict`
- `minimum_product_fit=P3`
- `include_paid_ugc=true`, but UGC results remain visibly separated
- All enrichment flags enabled through adaptive, evidence-driven execution

Existing clients that omit these fields remain compatible.

## UI Changes

Add or revise Vento-only controls:

- Quality Mode: Strict / Balanced
- Minimum Product Fit: Excellent / Strong / Relevant
- Include Paid UGC checkbox
- Require known follower count checkbox
- Require valid email checkbox
- Strict U.S. targeting label changed to `Strict U.S. targeting (entered location prioritized)`
- Remove `Minimum Raw Target` from the primary Vento workflow; the user supplies the desired usable target only
- Keep any legacy raw-target field hidden under advanced compatibility settings

Add visible result fields:

- Creator Type
- Product Fit
- Instagram status
- TikTok status
- Email status and source
- Follower count and evidence status
- Location confidence
- Quality/review reasons

Summary cards should show:

- Usable influencers
- Paid UGC creators
- Both-platform creators
- Email-ready creators
- Known-follower creators
- Location-confirmed creators
- Review candidates
- Rejected entity types

## Export Behavior

Preserve the existing history workflow:

1. Old CSV/XLSX is used for historical deduplication.
2. Only new leads appear on the page.
3. User selects desired new leads.
4. Export combines unchanged old rows with only selected new rows.

New exports must also include:

- Canonical social URLs
- Creator type
- Product fit level/score/evidence
- Identity confidence
- Email source
- Follower source/status
- Location evidence/confidence
- Quality reasons
- Review reasons

## Configuration

```env
VENTO_QUALITY_V2_ENABLED=true
VENTO_QUALITY_MODE=strict
VENTO_MIN_PRODUCT_FIT_SCORE=55
VENTO_REQUIRE_CANONICAL_SOCIAL=true
VENTO_REJECT_UNKNOWN_LOCATION_IN_STRICT_MODE=true
VENTO_ADAPTIVE_QUERY_SELECTION=true
VENTO_REUSE_CACHED_CREATOR_EVIDENCE=true
```

Optional provider credentials continue to use existing environment variables. No key is required for application startup, bulk import or export.

## Isolated Files and Changes

| Action | File | Change |
|---|---|---|
| Add | `core/services/vento/identity_quality.py` | Canonical profiles, entity type, title-name rejection and identity confidence |
| Add | `core/services/vento/product_fit.py` | Deterministic Vento-specific fit levels, tags, scores and evidence |
| Add | `core/services/vento/creator_enrichment.py` | Cross-platform, public email and follower enrichment coordinator |
| Modify | `core/services/vento/discovery.py` | Intersection-first Vento queries and profile-result preference |
| Modify | `core/services/vento/verification.py` | Context-safe location parsing and evidence statuses |
| Modify | `core/services/vento/qualification.py` | New A/B/Review/Rejected rules and creator exclusions |
| Modify | `core/services/vento/vento_lead_pipeline.py` | Add streaming quality gates and adaptive enrichment stages |
| Modify | `core/services/vento/daily_batch.py` | Add new metrics and separate influencer/UGC counts |
| Modify | `api/routes/vento_leads.py` | Backward-compatible quality/enrichment request fields |
| Modify | `ui/leadgen.html` | Quality controls, evidence display and new summary cards |
| Modify | `core/services/vento/excel_merge.py` | Export new evidence fields while preserving old rows unchanged |
| Modify | `.env.example` | Add Vento Quality V2 controls only |
| Modify | `core/services/vento/README.md` | Document feature flag, provider limits and removal procedure |
| Add/Modify | `tests/test_vento_*.py` | Regression, product-fit, identity, location, enrichment and export tests |

## Observability

Add per-run metrics:

```json
{
  "raw_candidates": 100,
  "canonical_social_profiles": 72,
  "individual_creators": 55,
  "product_fit_p1_p2": 18,
  "both_platforms": 7,
  "email_ready": 5,
  "known_followers": 12,
  "location_confirmed": 20,
  "usable_influencers": 14,
  "paid_ugc": 4,
  "review": 22,
  "rejected_directories": 3,
  "rejected_stores": 6,
  "shortfall": 6,
  "raw_to_usable_yield": 0.31,
  "usable_leads_per_tavily_search": 2.4,
  "tavily_searches_avoided_by_cache": 8,
  "fields_recovered_without_extra_search": 37
}
```

Log the top rejection/review reasons and per-query usable yield without logging secret values.

## Yield and Runtime Optimization

- Apply enrichment only after identity and product-fit prefilters.
- Enrich highest-fit candidates first.
- Stop when the usable target is satisfied and minimum evidence is present.
- Cache enrichment results by normalized platform handle and observation date.
- Use direct profile/website inspection before an additional search request.
- Consolidate second-platform, location, follower and email intent into one enrichment query where practical.
- Prefer provider bulk requests over per-lead requests.
- Batch ambiguous candidates into one Gemini classification request instead of calling Gemini once per lead.
- Adapt query order using observed usable conversion rate.
- Avoid broad searches that historically return stores, directories or irrelevant video titles.
- Respect Tavily and provider rate limits.
- Return partial results with explicit shortfall on quota exhaustion.
- Gemini remains optional and is used only for ambiguous evidence that deterministic logic cannot resolve.
- Do not introduce a new Plan 2 raw-target, search-count, enrichment-count or credit cap.

## Required Regression Tests From the Reviewed Workbook

- `Top 40 Auto TikTok Influencers` is rejected as a directory/listicle.
- `Roverdotcom` is classified as a corporate brand, not an individual influencer.
- `@cargadget.ae` cannot pass Strict U.S. mode without U.S. evidence.
- `IN` is not extracted from `income` or ordinary prose.
- `ME` is not extracted from `me`.
- `ID` is not extracted from `animal ID`.
- `@luvnthecru` receives strong pet-plus-heat product-fit evidence.
- `@bymichelleavendano` preserves Los Angeles evidence without producing Idaho.
- A post URL is converted to its canonical creator profile URL.
- A masked email such as `****@web.detiktok` is invalid.
- A generic UGC creator without product evidence is Review/Paid UGC, not influencer Level B.
- Missing follower count remains unknown and never becomes a verified tier.
- Instagram-only and TikTok-only strong creators can qualify B.
- A creator with both verified platforms receives a confidence bonus.
- Historical-file deduplication and selected old-plus-new export remain unchanged.

## General Automated Tests

- Canonical Instagram and TikTok URL extraction.
- Reserved platform path rejection.
- Video/article title detection.
- Store, directory, corporate and media entity classification.
- Product-fit P1–P5 classification.
- Cross-platform identity merge with two matching signals.
- Cross-platform false-positive rejection.
- Email discovery, source preservation and validation.
- Follower provider/search/unknown statuses.
- Context-safe city/state/country parsing.
- Strict U.S. and global-mode behavior.
- Quality-level classification.
- Provider-key absence and quota failure.
- Response and export evidence fields.
- Feature flag disabled behavior.
- Adaptive query selection favors higher usable-lead yield.
- Candidate enrichment reuses existing evidence before issuing another search.
- Quality V2 does not require a raw-target multiplier.
- Cached creator evidence avoids repeated searches across daily runs.

## Acceptance Criteria

- Every A/B lead has a canonical Instagram or TikTok profile.
- No directory, store, corporate brand or media page is exported as an influencer A/B lead.
- Product fit is Vento-specific and evidence-backed.
- Pet-plus-car/heat/safety creators rank above generic pet, car and UGC creators.
- Unknown locations do not pass Strict U.S. mode as usable leads.
- Standalone words no longer create false state codes.
- Public email is enriched when available and its source is preserved.
- Follower counts are populated only with evidence and remain unknown otherwise.
- Both social platforms are searched for top single-platform candidates.
- Either Instagram or TikTok remains sufficient for a strong Level B lead.
- Influencer and Paid UGC outputs are visibly distinct.
- The requested count never forces weak candidates into A/B.
- Quality V2 achieves leads through higher candidate conversion rather than a larger fixed raw target.
- The primary UI requests usable leads without requiring a minimum raw target.
- No new fixed Plan 2 credit, raw-candidate or enrichment lookup cap is introduced.
- Honest shortfall and enrichment metrics are visible.
- Old-file history, selection and old-plus-selected-new export behavior remains unchanged.
- Disabling `VENTO_QUALITY_V2_ENABLED` removes the new quality workflow without affecting other modes.
- The complete project test suite passes.

## Suggested Implementation Order

1. Add workbook-derived regression fixtures and failing tests.
2. Implement canonical social identity and entity exclusion module.
3. Replace unsafe location parsing.
4. Implement deterministic Vento product-fit module.
5. Tighten qualification levels and split Paid UGC from influencers.
6. Add adaptive cross-platform enrichment.
7. Add public email enrichment and evidence fields.
8. Add follower provider/search evidence handling.
9. Integrate stages into the Vento pipeline behind the feature flag.
10. Update API contracts and metrics.
11. Update UI controls, reasons and summary cards.
12. Update export columns while preserving historical rows.
13. Run Vento regression tests and the complete project test suite.
14. Validate a real Tavily-only batch and a provider-enabled batch when keys become available.

## Removal Procedure

To remove this upgrade later:

1. Set `VENTO_QUALITY_V2_ENABLED=false`.
2. Remove the three new Vento-only modules.
3. Remove V2 request fields, UI controls and evidence columns.
4. Keep the existing Vento pipeline, history workflow and Plan 1 Tavily expansion unchanged.
