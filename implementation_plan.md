# Vento Influencer Lead Generation Pipeline — Implementation Plan

## Goal

Build a **bulk influencer lead discovery pipeline** for the **Vento by Comfort Pod** product. The system discovers influencers across North American locations (primarily US, Seattle/PNW focus), extracts their **name, email, Instagram, TikTok, phone number**, and outputs verified leads — exactly like the existing `generic` and `velit` pipelines but purpose-built for influencer/creator discovery.

## Background & Product Context

**Product**: Vento by Comfort Pod — An app-controlled, smart cooling fan system with remote temperature monitoring and SMS alerts designed to keep pets safe inside parked cars.

**Campaign Goal**: Recruit ~28 influencers (nano → upper mid-tier, 5K–500K followers) for a July–September UGC campaign across Instagram, TikTok, and YouTube Shorts. Budget: US$23K–27K.

**Target Influencer Archetypes**:
1. **Pet Lifestyle Creators** — "Dog Mom/Dad" accounts, pet vloggers, professional dog trainers
2. **UGC Specialists / Aesthetic Reviewers** — Micro-creators focused on "Car Essentials", "Amazon Finds", problem-solving gadget reviews
3. **PNW/Local Lifestyle Vloggers** — Regional creators in Seattle/Portland who share daily life alongside dogs

**Geographic Focus**: United States, high priority on Seattle / Pacific Northwest (PNW) region.

---

## User Review Required

> [!IMPORTANT]
> **Data Source Strategy**: This pipeline uses **web scraping + Tavily search + Gemini AI analysis** to discover influencers from public directories, social platform bios, and creator databases. It does NOT use any official Instagram/TikTok APIs (which require brand accounts & review processes). This means:
> - Instagram/TikTok handles are extracted from web mentions, bio pages, linktrees, etc.
> - Phone numbers are found from public contact pages / media kits when available
> - Email addresses are found from creator bios, linktree pages, media kits, and contact pages
> - Results are genuine but coverage of phone/TikTok will vary (many creators only share email)

> [!WARNING]
> **Rate Limits & Costs**: Each location run will consume ~8-12 Tavily API calls and ~4-8 Gemini API calls. Running 10+ locations in batch will use significant API quota. The pipeline reuses the existing `TavilyClient` and `Gemini` infrastructure.

---

## Open Questions

> [!IMPORTANT]
> 1. **Follower Count Verification**: Should the pipeline attempt to verify follower counts from public profile data, or just discover and return the leads with whatever social links are found? (Verification adds complexity and API calls)
> 2. **Batch Scheduler Integration**: Should we integrate into the existing Velit Batch Scheduler UI so you can queue multiple locations (Seattle, Portland, Los Angeles, etc.) in one go? Or keep it as a standalone page?
> 3. **Google Sheets Export**: Should leads export to the same Google Sheets structure as Velit leads, or a separate "Vento Influencers" sheet with different columns?
> 4. **Existing `leadgen.html` Integration**: The current lead dashboard has a `mode` selector. Should "Vento Influencer" become a new mode in the existing dashboard, or remain a completely separate UI page?

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Vento Lead Pipeline                         │
│                                                                 │
│  Input: location + influencer_type + follower_tier              │
│                                                                 │
│  Phase 1: Influencer Discovery (Tavily Search)                  │
│    ├── Search for pet influencers, car/gadget reviewers,        │
│    │   lifestyle vloggers in target location                    │
│    ├── Search creator databases, media kit directories          │
│    └── Output: raw search results with URLs                     │
│                                                                 │
│  Phase 2: Creator Profile Resolution                            │
│    ├── Resolve official websites, linktree pages, media kits    │
│    ├── Gemini AI extracts creator names from directory pages    │
│    └── Output: list of creator profiles with URLs               │
│                                                                 │
│  Phase 3: Contact & Social Extraction                           │
│    ├── Scrape creator pages for email, phone, social links      │
│    ├── Extract Instagram handles from bios/linktrees            │
│    ├── Extract TikTok handles from bios/linktrees               │
│    ├── Extract YouTube channels                                 │
│    └── Output: enriched creator profiles                        │
│                                                                 │
│  Phase 4: Gemini Scoring & Qualification                        │
│    ├── Score relevance to Vento product (pet + car + tech)      │
│    ├── Estimate follower tier from context clues                │
│    ├── Rate content quality signals                             │
│    └── Output: scored and ranked influencer leads               │
│                                                                 │
│  Phase 5: Quality Gate & Deduplication                          │
│    ├── Remove duplicates by social handle / domain              │
│    ├── Apply quality gate (must have name + ≥1 contact method)  │
│    └── Output: final verified influencer leads                  │
│                                                                 │
│  Output Fields Per Lead:                                        │
│    name, email, instagram_handle, tiktok_handle,                │
│    youtube_channel, phone, website, location, niche,            │
│    estimated_follower_tier, relevance_score,                    │
│    value_proposition, media_kit_url                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes

### Component 1: Vento Discovery Module

#### [NEW] [discovery.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/vento/discovery.py)

Mirrors the Velit `discovery.py` pattern but with influencer-specific search queries and filtering.

```python
VENTO_SEARCH_DEPTH = "basic"
VENTO_EXTRACT_DEPTH = "basic"

# Influencer archetype keywords for text matching
_INFLUENCER_KEYWORDS = (
    "pet influencer", "dog mom", "dog dad", "pet vlogger",
    "dog trainer", "pet content creator", "animal lover",
    "car essentials", "amazon finds", "gadget review",
    "car accessories", "car organization", "product review",
    "lifestyle vlogger", "seattle blogger", "portland blogger",
    "pnw lifestyle", "pacific northwest", "outdoor lifestyle",
    "ugc creator", "content creator", "micro influencer",
    "tiktok creator", "instagram influencer",
)

# Social platform domains — NOT noise for this pipeline
_SOCIAL_PLATFORMS = (
    "instagram.com", "tiktok.com", "youtube.com",
    "linktr.ee", "linkin.bio", "beacons.ai",
    "bio.link", "stan.store", "koji.to",
)

def build_vento_queries(*, location: str, influencer_type: str, ...) -> List[str]:
    """Build Tavily search queries targeting influencer discovery."""
    # Examples:
    # '"pet influencer" "Seattle" instagram email contact'
    # '"dog mom" "Pacific Northwest" tiktok "media kit"'
    # '"car accessories reviewer" "Seattle" "collaboration" email'
    # '"ugc creator" "pet" "Seattle" instagram tiktok'

def build_vento_shortfall_queries(...) -> List[str]:
    """Additional queries when initial discovery falls short."""

def looks_like_influencer_text(text: str) -> bool:
    """Check if text contains influencer-related keywords."""

def extract_social_handles(text: str) -> Dict[str, str]:
    """Extract Instagram, TikTok, YouTube handles from text using regex."""
    # @handle patterns, full URL patterns, linktree extraction
```

**Key design decisions**:
- Social platform domains (instagram.com, tiktok.com) are **whitelisted** here, unlike in velit/generic where they are noise
- Search queries are crafted per influencer archetype (pet, gadget, lifestyle)
- Location handling reuses the existing `normalize_velit_location()` approach + adds PNW-specific expansions

---

#### [NEW] [__init__.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/vento/__init__.py)

Empty init file for the new module.

---

### Component 2: Vento Lead Pipeline

#### [NEW] [vento_lead_pipeline.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/vento/vento_lead_pipeline.py)

Extends `ProductionLeadPipeline` (same pattern as `VelitLeadPipeline`) with influencer-specific overrides.

```python
class VentoLeadPipeline(ProductionLeadPipeline):
    """Influencer discovery pipeline for the Vento by Comfort Pod campaign."""

    CONTACT_PATHS = (
        "", "/contact", "/about", "/media-kit", "/press",
        "/collaborate", "/partnerships", "/work-with-me",
        "/hire-me", "/brands", "/collabs",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Configure for influencer discovery (more scraping, less LinkedIn)
        self.linkedin_enrichment_limit = 0  # Not relevant for influencers
        self.max_contact_scrapes = 30
        self.contact_search_limit = 6

    async def run(
        self,
        *,
        location: str,
        influencer_type: str = "all",  # "pet", "gadget", "lifestyle", "all"
        follower_tier: str = "all",    # "nano", "mid", "upper_mid", "all"
        target_count: int = 15,
        seed_query: str = "",
    ) -> Dict[str, Any]:
        """
        Full pipeline:
        1. _discover_influencers() — Tavily search for creators
        2. _resolve_creator_profiles() — Find official pages / linktrees
        3. _extract_creator_contacts() — Scrape for email, phone, social handles
        4. _score_influencer_leads() — Gemini scoring for Vento relevance
        5. _apply_quality_gate() — Dedup, validate, filter
        """
```

**Key methods unique to Vento**:

```python
async def _discover_influencers(self, *, location, influencer_type, seed_query):
    """Phase 1: Search for influencers using crafted queries."""
    queries = build_vento_queries(
        location=location,
        influencer_type=influencer_type,
        seed_query=seed_query,
        max_queries=self.discovery_query_limit,
    )
    # Execute Tavily searches, collect results
    # UNLIKE generic/velit: DO NOT filter out social media domains

async def _extract_social_handles_from_page(self, html, visible_text, url):
    """Extract Instagram, TikTok, YouTube handles from a page."""
    handles = {
        "instagram": [],
        "tiktok": [],
        "youtube": [],
    }
    # Regex patterns:
    # Instagram: instagram.com/handle, @handle (context-dependent)
    # TikTok: tiktok.com/@handle, @handle
    # YouTube: youtube.com/@handle, youtube.com/c/channel

async def _score_influencer_leads(self, extracted, *, location, influencer_type):
    """Gemini-powered scoring specific to Vento campaign fit."""
    # Scoring criteria:
    # - Niche match (pet content = high, car/gadget = medium, general = low)
    # - Location match (Seattle/PNW = high, other US = medium)
    # - Has media kit / collaboration page = bonus
    # - Number of social platforms present = bonus
    # - Content quality signals from page text
```

**Output lead schema** (each lead dict):
```python
{
    "creator_name": "Jane Smith",
    "email": "jane@example.com",
    "instagram_handle": "@janedogmom",
    "instagram_url": "https://instagram.com/janedogmom",
    "tiktok_handle": "@janedogmom",
    "tiktok_url": "https://tiktok.com/@janedogmom",
    "youtube_channel": "",
    "youtube_url": "",
    "phone": "+1-206-555-1234",
    "website": "https://janedogmom.com",
    "media_kit_url": "https://janedogmom.com/media-kit",
    "linktree_url": "https://linktr.ee/janedogmom",
    "location": "Seattle, WA",
    "niche": "Pet Lifestyle",
    "estimated_follower_tier": "mid",  # nano/mid/upper_mid
    "relevance_score": 8.5,
    "value_proposition": "Active dog mom creating pet safety content in Seattle area",
    "quality_score": 78,
    "source": "tavily_discovery",
    "contact_method_count": 3,  # How many contact methods found
}
```

---

### Component 3: API Routes

#### [NEW] [vento_leads.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/api/routes/vento_leads.py)

```python
router = APIRouter()

class VentoSearchRequest(BaseModel):
    location: str
    influencer_type: str = "all"        # "pet", "gadget", "lifestyle", "all"
    follower_tier: str = "all"          # "nano", "mid", "upper_mid", "all"
    target_count: int = Field(default=15, ge=1, le=50)
    seed_query: str = ""

class VentoExportRequest(BaseModel):
    leads: List[Dict[str, Any]]

@router.post("/search")
async def search_influencers(request: VentoSearchRequest) -> Dict[str, Any]:
    pipeline = VentoLeadPipeline()
    return await pipeline.run(
        location=request.location,
        influencer_type=request.influencer_type,
        follower_tier=request.follower_tier,
        target_count=request.target_count,
        seed_query=request.seed_query,
    )

@router.post("/export")
async def export_vento_leads(request: VentoExportRequest) -> Dict[str, Any]:
    """Export leads to Google Sheets with Vento-specific columns."""
    state = get_state()
    if not state.todo_store:
        raise HTTPException(status_code=500, detail="Google Sheets not configured")
    service = LeadService(state.todo_store)
    return await service.export_leads(request.leads, mode="vento")
```

**API Contract**:

**POST `/api/vento/search`**
```json
{
  "location": "Seattle, WA",
  "influencer_type": "pet",
  "follower_tier": "mid",
  "target_count": 15,
  "seed_query": ""
}
```

**Response**:
```json
{
  "leads": [
    {
      "creator_name": "Jane Smith",
      "email": "jane@gmail.com",
      "instagram_handle": "@janedogmom",
      "instagram_url": "https://instagram.com/janedogmom",
      "tiktok_handle": "@janedogmom",
      "tiktok_url": "https://tiktok.com/@janedogmom",
      "youtube_channel": "",
      "phone": "+1-206-555-1234",
      "website": "https://janedogmom.com",
      "location": "Seattle, WA",
      "niche": "Pet Lifestyle",
      "estimated_follower_tier": "mid",
      "relevance_score": 8.5,
      "value_proposition": "Active dog mom creating pet safety content in Seattle",
      "quality_score": 78,
      "contact_method_count": 3
    }
  ],
  "steps": [...],
  "metadata": {
    "pipeline": "vento_influencer_pipeline",
    "total_discovered": 45,
    "total_leads": 15,
    "leads_with_email": 12,
    "leads_with_instagram": 14,
    "leads_with_tiktok": 9,
    "leads_with_phone": 5
  }
}
```

---

#### [MODIFY] [main.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/api/main.py)

Append route registration (additive only, same pattern as existing routes):

```python
# ── Vento Influencer Lead Pipeline ──
if _include_optional_route("ENABLE_VENTO_PIPELINE", True):
    try:
        from api.routes import vento_leads as vento_leads_route
        app.include_router(vento_leads_route.router, prefix="/api/vento", tags=["Vento Leads"])
    except Exception as exc:
        print(f"Vento pipeline disabled: {exc}")

@app.get("/vento-leads", include_in_schema=False)
async def vento_leads_page():
    return FileResponse("ui/vento_leads.html")
```

---

### Component 4: Frontend UI

#### [NEW] [vento_leads.html](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/ui/vento_leads.html)

Same design system as existing pages (dark theme, glassmorphism, Outfit font). The page will include:

**Search Panel**:
- Location input (with PNW suggestions: Seattle, Portland, Los Angeles, San Francisco, etc.)
- Influencer Type selector: All / Pet Lifestyle / Gadget Reviewers / Lifestyle Vloggers
- Follower Tier selector: All / Nano (5K-20K) / Mid (20K-100K) / Upper Mid (100K-500K)
- Target Count slider (1-50)
- Seed Query (optional freetext)
- "Search" button with loading animation

**Results Table**:

| Creator Name | Email | Instagram | TikTok | YouTube | Phone | Location | Niche | Tier | Score |
|---|---|---|---|---|---|---|---|---|---|

- Instagram/TikTok/YouTube columns render as clickable links
- Email column has a copy button
- Each row has a checkbox for batch export
- Color-coded score badges (green/yellow/red)

**Export Panel**:
- "Export to Google Sheets" button (selected or all)
- "Download CSV" button
- "Download XLSX" button with all contact info columns

**Design Features**:
- Same glassmorphism card design as existing `leadgen.html` and `velit_batch_scheduler.html`
- Progress indicator showing pipeline phases (Discovery → Resolution → Extraction → Scoring)
- Stats bar showing: Total Found | With Email | With Instagram | With TikTok | With Phone
- Responsive layout for mobile use

---

### Component 5: Vento-Specific Gemini Scoring Prompt

The Gemini scoring prompt will be tailored for influencer evaluation:

```python
VENTO_INFLUENCER_SCORING_PROMPT = """
You are an influencer campaign analyst for Comfort Pod (Vento product).
Vento is a smart cooling fan for parked cars that keeps pets safe.

Score this creator for the Vento campaign on these criteria:
1. NICHE FIT (0-10): How well does their content align with:
   - Pet safety / pet lifestyle
   - Car accessories / gadgets
   - Outdoor/adventure lifestyle with pets
2. AUDIENCE MATCH (0-10): Do they target:
   - US-based pet owners
   - Dog parents who travel with pets
   - Tech-savvy consumers
3. CONTENT QUALITY (0-10): Based on available signals:
   - Professional content (media kit, collab page = good)
   - Active social presence (multiple platforms = good)
   - Engagement signals from bio text
4. LOCATION MATCH (0-10): Priority locations:
   - Seattle / PNW = 10
   - Major US cities = 7
   - US-based = 5
   - Non-US = 2

Output JSON: {"relevance_score": 0-10, "niche": "...", "estimated_tier": "nano|mid|upper_mid", "value_proposition": "one sentence"}
"""
```

---

## Files Changed Summary

| Action | File | Description |
|--------|------|-------------|
| **NEW** | `core/services/vento/__init__.py` | Empty module init |
| **NEW** | `core/services/vento/discovery.py` | Influencer search queries, social handle extraction, keyword matching |
| **NEW** | `core/services/vento/vento_lead_pipeline.py` | Main pipeline class extending `ProductionLeadPipeline` |
| **NEW** | `api/routes/vento_leads.py` | FastAPI routes for `/api/vento/search` and `/api/vento/export` |
| **NEW** | `ui/vento_leads.html` | Frontend page (dark theme, glassmorphism, same design system) |
| **MODIFY** | `api/main.py` | Append route registration + UI page route (additive only) |

---

## Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| No influencers found for location | Return empty leads + metadata with `stop_reason: "no_results"`. Suggest broader location. |
| Tavily rate limit hit | Retry with exponential backoff (3 retries). Return partial results if all retries fail. |
| Gemini quota exhausted | Fall back to rule-based scoring (keyword matching + contact method count). |
| Social handle extraction finds wrong handle | Multiple validation: check handle appears in bio context, not in unrelated link. |
| Creator has no public email | Mark `email: ""` — still return lead if Instagram/TikTok found. |
| Duplicate creator across locations | Dedup by Instagram handle (primary key) or domain. |
| Linktree / bio link page is down | Gracefully skip, try alternate contact pages. |
| Non-US creator appears in results | Still include but lower score. Location filter is soft, not hard. |
| Creator account is private | No data extractable — skip with `status: "private_account"`. |
| Media kit is a PDF | Extract text from PDF URL if available via Tavily extract. |

---

## Safety — Additive Only Checklist

- [x] No existing files deleted
- [x] No existing service classes modified
- [x] No existing route handlers changed
- [x] No existing UI pages touched
- [x] New routes use isolated prefix (`/api/vento/`)
- [x] Feature-flag gated (`ENABLE_VENTO_PIPELINE`)
- [x] Removal: set flag to false, delete new files only
- [x] Reuses existing infrastructure: `TavilyClient`, `Gemini`, `ProductionLeadPipeline` base, `TodoSheetStore`

---

## Verification Plan

### Automated Tests
```bash
# Run existing tests to confirm no regressions
pytest tests/ -v

# Test Vento discovery queries generate correctly
python -c "from core.services.vento.discovery import build_vento_queries; print(build_vento_queries(location='Seattle, WA', influencer_type='pet'))"

# Test social handle extraction
python -c "from core.services.vento.discovery import extract_social_handles; print(extract_social_handles('Follow me @janedogmom on instagram and tiktok.com/@jane'))"
```

### Manual Verification
1. Start the server: `uvicorn api.main:app --reload --port 8000`
2. Navigate to `http://localhost:8000/vento-leads`
3. Run a search for "Seattle, WA" with "Pet Lifestyle" type
4. Verify leads appear with Instagram/TikTok handles populated
5. Test CSV/XLSX export downloads correctly
6. Test Google Sheets export creates proper columns
7. Run searches for multiple locations to test diversity of results
