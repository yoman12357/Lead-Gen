# Apify+tavily — Vento Creator Lead Enrichment Plan

## Goal

Integrate Apify with the existing Tavily-based Vento pipeline so creator leads are more accurate before export.

Current behavior:

1. Tavily discovers possible pet/dog/cat influencer profiles.
2. The pipeline extracts names, Instagram/TikTok links, emails, and follower counts from snippets/public pages.
3. Leads below the configured follower threshold are rejected.

Target behavior:

1. Tavily still discovers candidate Instagram/TikTok profiles.
2. Apify enriches those social profiles with structured profile data.
3. The pipeline keeps only creators with verified/observed follower count above the threshold.
4. Export includes the follower count and better name/profile/contact fields.
5. If Apify is not configured, the pipeline continues using the current Tavily + public crawler fallback.

This keeps the workflow cheap and flexible:

- Tavily = discovery/search layer.
- Apify = structured profile verification/enrichment layer.
- Existing crawler/snippet logic = fallback.

---

## Why Apify Here

Apify is not a full influencer database like Modash or HypeAuditor, but it is useful for this project because:

- It can enrich known Instagram/TikTok usernames.
- It can return follower counts more consistently than search snippets.
- It can extract public bio/name/profile fields.
- Some actors can extract emails from bio/link-in-bio pages.
- Cost is usually much lower than enterprise influencer APIs.

Expected limitations:

- Instagram/TikTok can still block or throttle scrapers.
- Actor output schemas differ by actor, so mapping must be defensive.
- Email will not be available for every profile.
- Location may be weak unless present in bio or search evidence.
- Apify should verify/enrich candidates, not replace Tavily discovery.
- Apify actors can become expensive if the same handles are enriched repeatedly, so caching and max-per-run limits are required.
- A search result can mention multiple creators in one article; Instagram and TikTok handles must not be blindly merged unless they appear to belong to the same creator.

---

## Final Workflow

```text
User chooses:
  Category: Dog Parent Influencers
  Location: Los Angeles, CA
  Lead count: 50
  Min followers: env-controlled, default 50,000 after this integration

Pipeline:
  1. Tavily discovery
     - Search dog/pet/cat influencer queries by location.
     - Extract Instagram/TikTok handles.
     - Remove obvious bad rows: media pages, stores, shelters, placeholder usernames.

  2. Tavily enrichment
     - Run candidate-specific search.
     - Recover email, second social platform, location evidence, and any snippet follower count.

  3. Apify profile enrichment
     - For every Instagram handle, call configured Instagram actor.
     - For every TikTok handle, call configured TikTok actor.
     - Use cache first so repeated handles do not spend Apify credits again.
     - Normalize profile data into the Vento lead schema.
     - Prefer Apify follower count over snippet/crawler count.
     - Prefer Apify display name when it is a real creator name.
     - Pull public email/bio/website if present.
     - Do not merge mismatched Instagram/TikTok accounts from unrelated creators.

  4. Quality gate
     - Require at least one Instagram/TikTok profile.
     - Require follower count >= VENTO_MIN_SOCIAL_FOLLOWERS.
     - Reject unknown follower count if VENTO_REQUIRE_SOCIAL_FOLLOWERS=true.
     - Reject obvious non-creator accounts.

  5. Export
     - Save only usable leads.
     - Last column includes Follower Count.
     - Keep notes/tags clean for CRM upload.
```

---

## Environment Variables

Add these to `.env.example` and `.env` when implementing:

```env
# ----- Vento Apify + Tavily Enrichment -----
VENTO_CREATOR_DATA_PROVIDER=apify
APIFY_API_TOKEN=

# Actor IDs are configurable so we can switch actors without code changes.
APIFY_INSTAGRAM_PROFILE_ACTOR=apify/instagram-scraper
APIFY_TIKTOK_PROFILE_ACTOR=clockworks/tiktok-scraper

# Use Apify after Tavily has found social handles.
VENTO_APIFY_ENRICHMENT_ENABLED=true
VENTO_APIFY_TIMEOUT_SECONDS=90
VENTO_APIFY_BATCH_SIZE=25
VENTO_APIFY_MAX_PROFILES_PER_RUN=200
VENTO_APIFY_CACHE_TTL_DAYS=7
VENTO_APIFY_CACHE_PATH=data/vento/apify_profile_cache.json

# Lead quality target.
VENTO_MIN_SOCIAL_FOLLOWERS=50000
VENTO_REQUIRE_SOCIAL_FOLLOWERS=true

# Keep fallback enabled so the pipeline still works without Apify.
VENTO_SOCIAL_NAME_FETCH_ENABLED=true
VENTO_SOCIAL_NAME_TIMEOUT_SECONDS=6
```

Notes:

- `APIFY_API_TOKEN` should not be committed with a real value.
- `VENTO_MIN_SOCIAL_FOLLOWERS` should become `50000` for the mentor requirement.
- If Apify is not configured, the current Tavily/crawler path should still work.
- `VENTO_APIFY_MAX_PROFILES_PER_RUN` prevents accidental credit burn.
- `VENTO_APIFY_CACHE_TTL_DAYS` prevents paying again for the same profile during normal repeat runs.

---

## Files to Add

### 1. `core/services/vento/apify_enrichment.py`

New module responsible only for Apify calls and output normalization.

Responsibilities:

- Build Apify actor URLs.
- Call actor run-sync dataset endpoint.
- Parse Instagram actor results.
- Parse TikTok actor results.
- Normalize different actor field names into one internal shape.
- Read/write a small profile cache keyed by `platform:handle`.
- Enforce batch size and max-profiles-per-run guardrails.
- Detect likely Instagram/TikTok mismatches before merging both platforms into one lead.
- Return enrichment records without mutating pipeline state directly.

Suggested classes/functions:

```python
@dataclass
class ApifyProfileRecord:
    platform: str
    handle: str
    profile_url: str = ""
    display_name: str = ""
    biography: str = ""
    email: str = ""
    website: str = ""
    follower_count: Optional[int] = None
    platform_follower_count: Optional[int] = None
    following_count: Optional[int] = None
    post_count: Optional[int] = None
    verified: Optional[bool] = None
    observed_at: str = ""
    source_actor: str = ""
    source_status: str = "unknown"
    raw: Dict[str, Any] = field(default_factory=dict)
```

```python
class ApifyCreatorEnricher:
    def __init__(self, *, client: Optional[httpx.AsyncClient] = None) -> None:
        ...

    @property
    def configured(self) -> bool:
        ...

    async def enrich_profiles(
        self,
        leads: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        ...
```

Important implementation rule:

Apify output must be normalized before touching the lead. Do not scatter actor-specific field names throughout `vento_lead_pipeline.py`.

---

## Core Edge-Case Rules

### 1. Use profile-enrichment actors first

The first implementation should use actors that enrich profiles/users only.

Avoid post/reel/video scraping in version 1 because:

- It costs more.
- It returns noisy post-level data.
- The Vento export only needs profile-level details.

Only add post/reel scraping later if we need engagement quality, recent content proof, or product-fit scoring.

### 2. Normalize flexible actor schemas

Different Apify actors return different field names. The normalizer must check multiple candidate paths.

Follower count candidates:

```text
followersCount
followers
followerCount
edge_followed_by.count
authorMeta.fans
authorMeta.followers
stats.followerCount
stats.followers
user.stats.followerCount
```

Display name candidates:

```text
fullName
full_name
name
nickname
nickName
authorMeta.nickName
authorMeta.name
user.nickname
```

Bio candidates:

```text
biography
bio
signature
authorMeta.signature
user.signature
```

Email candidates:

```text
email
businessEmail
publicEmail
contactEmail
emails[0]
```

The actor-specific raw output should stay inside `ApifyProfileRecord.raw`; the rest of the pipeline only reads normalized fields.

### 3. Keep platform-specific follower counts

If both Instagram and TikTok exist, keep separate counts internally:

```text
instagram_follower_count
tiktok_follower_count
```

Then export:

```text
follower_count = max(instagram_follower_count, tiktok_follower_count)
```

Why:

- A creator may be small on Instagram but large on TikTok.
- The mentor requirement is 50K+ followers, so passing on either platform is acceptable.
- Export stays simple with one final `Follower Count` column.

### 4. Do not blindly merge Instagram and TikTok

Tavily snippets/articles often mention more than one creator. Example: an article about one dog creator may also link the publication's TikTok account.

Only attach both platforms to the same lead if at least one is true:

- Handles are the same or very similar after normalization.
- Apify display names are the same or very similar.
- Tavily evidence contains both handles close together and the creator name matches.
- One platform bio links to the other platform.

Otherwise:

- Keep the stronger/social-profile platform.
- Drop the suspicious second platform.
- Add `platform_mismatch_dropped` to internal notes/rejection metadata.

Suggested similarity helper:

```python
def _same_creator_socials(lead, instagram_record, tiktok_record) -> bool:
    ...
```

### 5. Cache Apify results

Use a lightweight JSON cache:

```text
data/vento/apify_profile_cache.json
```

Cache key:

```text
instagram:itsdougthepug
tiktok:brodiethatdood
```

Cache value:

```json
{
  "platform": "instagram",
  "handle": "itsdougthepug",
  "follower_count": 3800000,
  "display_name": "Doug The Pug",
  "email": "",
  "website": "https://...",
  "observed_at": "2026-07-14T00:00:00Z",
  "source_actor": "apify/instagram-scraper"
}
```

Rules:

- Use cached record if it is newer than `VENTO_APIFY_CACHE_TTL_DAYS`.
- Refresh expired records when budget allows.
- Cache successful lookups and "not found" results separately.
- Do not cache transient failures like timeout/429 as permanent.

### 6. Cost guardrails

Before calling Apify:

1. Deduplicate handles by platform.
2. Remove handles already satisfied by fresh cache.
3. Stop at `VENTO_APIFY_MAX_PROFILES_PER_RUN`.
4. Batch calls using `VENTO_APIFY_BATCH_SIZE`.

If candidate count exceeds the limit:

- Prioritize leads with email or stronger Tavily relevance.
- Prioritize leads with location evidence.
- Prioritize leads with existing snippet follower count near/above threshold.
- Put the rest through fallback only.

### 7. Email quality rule

Apify may return source/platform/media emails. Do not blindly trust them.

Reject or ignore emails when the domain/local part suggests media/platform/source instead of creator:

```text
news@
press@
editor@
tips@
support@
help@
info@instagram.com
info@tiktok.com
```

For creator leads, prefer:

- Gmail/personal email from bio.
- Creator domain email.
- Link-in-bio extracted email.

Never overwrite a good existing creator email with a blank or worse Apify email.

### 8. Phone is optional

Phone should not block influencer leads.

Most creators will not publish a phone number. For `dog_parent_influencers`, acceptable contact is:

```text
email OR instagram OR tiktok
```

The stricter gate is follower count, not phone.

---

## Files to Modify

### 1. `core/services/vento/vento_lead_pipeline.py`

Add optional Apify enrichment between Tavily enrichment and dedup/scoring.

Current run order:

```python
raw_candidates = await self._discover_candidates(...)
enriched = await self._enrich_candidates(...)
deduped, duplicate_count = self._dedup(enriched, old_keys)
scored = await self._score_leads(...)
usable, rejected = self._quality_gate(...)
```

New run order:

```python
raw_candidates = await self._discover_candidates(...)
enriched = await self._enrich_candidates(...)
enriched = await self._enrich_with_apify_if_enabled(enriched, category)
deduped, duplicate_count = self._dedup(enriched, old_keys)
scored = await self._score_leads(...)
usable, rejected = self._quality_gate(...)
```

Add helper:

```python
async def _enrich_with_apify_if_enabled(
    self,
    leads: Sequence[Dict[str, Any]],
    category: str,
) -> List[Dict[str, Any]]:
    if category != "dog_parent_influencers":
        return list(leads)
    if not self.apify_enrichment_enabled or not self.apify_enricher.configured:
        return list(leads)
    enriched, stats = await self.apify_enricher.enrich_profiles(leads)
    self._stats.update(...)
    return enriched
```

Add stats:

```python
"apify_enabled": 0,
"apify_profile_requests": 0,
"apify_profiles_enriched": 0,
"apify_cache_hits": 0,
"apify_cache_misses": 0,
"apify_profiles_skipped_by_budget": 0,
"apify_followers_found": 0,
"apify_emails_found": 0,
"apify_platform_mismatches_dropped": 0,
"apify_failures": 0,
```

Add init fields:

```python
self.apify_enrichment_enabled = env bool VENTO_APIFY_ENRICHMENT_ENABLED
self.apify_enricher = ApifyCreatorEnricher()
self.require_social_followers = env bool VENTO_REQUIRE_SOCIAL_FOLLOWERS
```

Do not require Apify at startup. The app should still run without token.

---

### 2. `core/services/vento/discovery.py`

Keep Tavily query templates, but make influencer queries more Apify-friendly by prioritizing direct profile discovery:

```python
"dog_parent_influencers": [
    'site:instagram.com "{location}" "dog mom"',
    'site:tiktok.com/@ "{location}" "dog mom"',
    'site:instagram.com "{location}" "dog dad"',
    'site:tiktok.com/@ "{location}" "dog dad"',
    'site:instagram.com "{location}" "pet influencer"',
    'site:tiktok.com/@ "{location}" "pet influencer"',
]
```

Reason:

Apify performs best when we feed it real handles/profile URLs, not articles or directories.

Keep some broader queries only if quantity drops too much.

---

### 3. `core/services/todo_sheet_store.py`

Already has `Follower Count` as the last Vento export column.

No structural change needed unless we add extra columns later.

Optional future columns:

- `Follower Source`
- `Engagement Rate`
- `Profile Verified`

For now, keep export stable.

---

### 4. `ui/leadgen.html`

Current UI can stay simple.

Optional UI improvement:

- Show follower count in the Vento table so the user can see why the lead passed.

Add near the score/social area:

```javascript
const followerLabel = lead.follower_count
  ? `${Number(lead.follower_count).toLocaleString()} followers`
  : 'Follower count unknown';
```

No API key input should be added to the UI. API tokens belong in `.env`.

---

### 5. `.env.example`

Add the Apify env variables listed above.

Do not add real keys to `.env.example`.

---

### 6. `core/services/vento/README.md`

Update provider configuration section:

```md
For Vento creator leads, Tavily is used for discovery and Apify can optionally be used for structured Instagram/TikTok enrichment.

Required:
- TAVILY_API_KEY

Optional:
- APIFY_API_TOKEN
- VENTO_APIFY_ENRICHMENT_ENABLED=true
```

Clarify fallback behavior:

```md
If Apify is not configured, Vento still runs using Tavily snippets and public profile metadata, but follower counts may be less complete.
```

---

## Actor API Design

Use Apify run-sync dataset endpoint:

```text
POST https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={APIFY_API_TOKEN}
```

Where `{actor_id}` is URL-encoded, for example:

```text
apify/instagram-scraper -> apify~instagram-scraper
clockworks/tiktok-scraper -> clockworks~tiktok-scraper
```

Implementation helper:

```python
def _actor_url(actor_id: str) -> str:
    safe_actor_id = actor_id.replace("/", "~")
    return f"https://api.apify.com/v2/acts/{safe_actor_id}/run-sync-get-dataset-items"
```

Then call:

```python
await client.post(
    url,
    params={"token": self.token},
    json=payload,
)
```

---

## Apify Input Payloads

Because actor schemas vary, these should be configurable in code and easy to adjust after testing the chosen actor.

### Instagram profile enrichment payload

Candidate payload shape:

```json
{
  "directUrls": [
    "https://www.instagram.com/examplecreator/"
  ],
  "resultsType": "details",
  "resultsLimit": 1,
  "searchType": "user"
}
```

Possible fields to parse:

```text
username
fullName
full_name
biography
followersCount
followers
followerCount
edge_followed_by.count
followsCount
postsCount
isVerified
externalUrl
email
businessEmail
url
```

### TikTok profile enrichment payload

Candidate payload shape:

```json
{
  "profiles": [
    "examplecreator"
  ],
  "resultsPerPage": 1,
  "shouldDownloadVideos": false
}
```

Possible fields to parse:

```text
authorMeta.name
authorMeta.nickName
authorMeta.signature
authorMeta.fans
authorMeta.followers
authorMeta.following
authorMeta.heart
authorMeta.verified
stats.followerCount
user.stats.followerCount
webVideoUrl
profileUrl
email
```

Important:

The first implementation should log/save a small redacted sample of actor output in tests or dev notes so we can tune field mapping after seeing the real actor response.

---

## Normalized Field Mapping

Map Apify records into existing Vento lead fields:

| Apify normalized field | Vento lead field |
|---|---|
| `display_name` | `creator_name` if better than handle fallback |
| `email` | `email` if current email is blank |
| `website` | `website` if current website is blank and not social URL |
| `platform_follower_count` | `instagram_follower_count` or `tiktok_follower_count` |
| max platform count | `follower_count` |
| `source_status` | `follower_count_status = "apify_verified"` |
| `profile_url` | `follower_source_url` if it produced the max count |
| `profile_url` | `instagram_url` or `tiktok_url` |
| `biography` | append short public bio to `notes` only if useful |

Do not overwrite a known creator email with a generic media/source email.

Do not overwrite a better social display name with a handle-like name.

Keep these internal fields when possible:

```text
instagram_follower_count
tiktok_follower_count
follower_source_platform
follower_source_url
follower_observed_at
follower_count_status
```

---

## Lead Acceptance Rule

For `dog_parent_influencers`:

```python
passes = (
    has_instagram_or_tiktok
    and follower_count is not None
    and follower_count >= VENTO_MIN_SOCIAL_FOLLOWERS
)
```

Recommended default:

```env
VENTO_MIN_SOCIAL_FOLLOWERS=50000
VENTO_REQUIRE_SOCIAL_FOLLOWERS=true
```

Rejection reasons:

```text
social_followers_unknown
social_followers_below_50000
missing_social_profile
not_individual_creator
not_pet_related
```

---

## Fallback Behavior

If Apify token is missing:

```text
Tavily discovery -> Tavily enrichment -> public social page crawler -> quality gate
```

If Apify actor fails/rate-limits:

```text
Keep lead's existing Tavily/crawler evidence.
Increment apify_failures.
Do not crash the whole Vento run.
Reject later if follower count remains unknown and followers are required.
```

If Apify returns HTTP 429:

```text
Stop calling that actor for this run.
Use cached results and Tavily/crawler evidence for remaining leads.
Mark apify_status = rate_limited.
```

If Apify times out:

```text
Retry once if no profiles were returned.
If partial profiles were returned, use partial data and continue.
```

If Apify returns no follower count:

```text
Keep existing follower count if Tavily/crawler found one.
Otherwise follower_count remains unknown.
```

If Instagram and TikTok look mismatched:

```text
Do not merge both into one lead.
Keep the platform that has stronger creator evidence and/or higher follower count.
Drop suspicious second platform from that lead.
```

---

## Tests to Add

### 1. `tests/test_vento_apify_enrichment.py`

Test cases:

1. Inert without token.
2. Instagram actor response maps `followersCount` to `follower_count`.
3. TikTok actor response maps `authorMeta.fans` to `follower_count`.
4. Apify email fills blank email.
5. Apify does not overwrite an existing good email with blank/bad value.
6. Actor failure returns original leads and increments failure stats.
7. Batch size is respected.
8. Unknown actor fields do not crash normalization.
9. Cache hit prevents a second Apify request.
10. Expired cache record is refreshed.
11. Instagram/TikTok mismatch is not merged.
12. Multiple follower field names normalize correctly.
13. Bad media/source emails are ignored.

### 2. Update `tests/test_vento_plan3.py`

Add:

1. Apify enrichment runs after Tavily enrichment for influencers.
2. Apify enrichment is skipped for pet shops/groomers/businesses.
3. A 49,999 follower creator is rejected when min is 50K.
4. A 50,000 follower creator passes.
5. A creator with 20K Instagram followers and 80K TikTok followers passes with exported follower count 80K.
6. Unknown follower count is rejected when `VENTO_REQUIRE_SOCIAL_FOLLOWERS=true`.
7. Unknown follower count can pass only when `VENTO_REQUIRE_SOCIAL_FOLLOWERS=false` and other contact rules pass.

### 3. Update `tests/test_vento_export.py`

Add:

1. `Follower Count` is preserved in Sheets export.
2. Export does not save rejected/unknown-follower creator leads.
3. Platform-specific follower fields do not create extra export columns unless intentionally added.

---

## Implementation Phases

### Phase 1 — Plan and env only

Status: this document.

No API key needed.

### Phase 2 — Build Apify adapter

Create:

```text
core/services/vento/apify_enrichment.py
tests/test_vento_apify_enrichment.py
```

Use mocked `httpx.AsyncClient` tests. No real Apify calls in tests.

Include cache support in this phase so cost control exists from day one.

### Phase 3 — Connect adapter to Plan 3 pipeline

Modify:

```text
core/services/vento/vento_lead_pipeline.py
```

Add:

- `self.apify_enricher`
- `_enrich_with_apify_if_enabled`
- Apify stats in metrics
- Apify enrichment step after Tavily enrichment
- mismatch prevention when combining Instagram and TikTok evidence
- platform-specific follower counts and max-count export logic

### Phase 4 — Tighten follower gate to 50K

Modify:

```text
.env.example
.env
tests/test_vento_plan3.py
```

Set:

```env
VENTO_MIN_SOCIAL_FOLLOWERS=50000
VENTO_REQUIRE_SOCIAL_FOLLOWERS=true
```

### Phase 5 — UI/export visibility

Modify:

```text
ui/leadgen.html
```

Show follower count in the Vento lead table and keep `Follower Count` in XLSX export.

### Phase 6 — Real API-key test

After user provides API key:

1. Add token to local `.env`.
2. Run one small test with 3-5 known Instagram/TikTok URLs.
3. Inspect actual actor output fields.
4. Adjust normalizers if actor schema differs.
5. Run a small Vento search with `target_count=5`.
6. Confirm exported leads all have `follower_count >= 50000`.
7. Run the same test again and confirm cache hits reduce Apify calls.

---

## Acceptance Criteria

The integration is complete when:

1. App starts without Apify token.
2. With Apify token, creator leads are enriched with follower counts.
3. Leads under 50K followers are rejected.
4. Unknown follower-count leads are rejected when follower count is required.
5. Export has `Follower Count` as the final column.
6. Tests pass without making real network calls.
7. One real small run confirms Apify output mapping works.
8. Re-running the same handles uses cache and does not spend duplicate Apify calls.
9. Instagram/TikTok mismatches are not merged into incorrect leads.
10. Apify 429/timeouts do not crash the whole Vento run.

---

## Recommended First Real Test

After adding the API key, test with a tiny fixed set:

```text
Instagram:
- itsdougthepug
- agoldendogmom
- mo_mountain_mutts

TikTok:
- brodiethatdood
- theworldsbestdogdad
- jimyofficial
```

Expected:

- At least some profiles return follower counts.
- Any profile below 50K is rejected.
- Any profile above 50K appears in export with follower count filled.

---

## Final Note

This design intentionally does not make Apify mandatory. Tavily keeps finding candidates, and Apify improves correctness when configured. That gives the best balance for Vento right now: lower cost than enterprise influencer APIs, but much better follower-count accuracy than relying only on snippets.
