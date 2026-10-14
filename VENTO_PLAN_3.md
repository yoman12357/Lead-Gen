# Plan 3 — Vento Pet Industry Lead Finder (Customer-Ready)

## Goal

Build a **simple, aggressive lead finder** for the Vento product that any team member can use. The user selects a **target audience type**, a **location**, and a **lead count** — and gets back that many usable leads with real contact details. No complexity. No "needs review" waste. If you ask for 50, you get close to 50.

## How It Works (User's Perspective)

```
User selects:  Target Audience  →  "Dog Parent Influencers"
               Location         →  "Los Angeles, CA"
               Number of Leads  →  50

Pipeline does:
  Step 1 → Tavily search: find 70-80 names/pages for that audience in that location
  Step 2 → For EACH result, do a second Tavily search to find their contact details
  Step 3 → Clean, dedup, score with Gemini
  Step 4 → Return ~50 usable leads with contact info filled in
  Step 5 → Auto-save to "Vento Influencers" Google Sheet
```

## Product Context

**Vento by Comfort Pod** — Smart pet-safe automotive cooling system. We need leads to market this product to pet-adjacent audiences across the US.

---

## Target Audience Categories

The user picks ONE of these from a dropdown. Each category determines what we search for and what contact details we prioritize:

| Category | What We Search For | Contact Details Needed |
|---|---|---|
| 🐕 **Dog Parent Influencers** | Instagram/TikTok creators who are dog parents, pet vloggers, dog trainers | Instagram, TikTok, Email |
| 🛒 **Online Pet Businesses** | E-commerce pet stores, online pet product retailers, pet subscription boxes | Website, Email, Phone |
| 🏪 **Pet Shops** | Physical pet stores, pet supply shops, local pet retailers | Email, Phone, Website |
| ✂️ **Pet Grooming Shops** | Dog groomers, pet spas, mobile grooming services | Email, Phone, Website |

---

## User Inputs (UI — Vento Mode Panel)

Only 3 inputs + 1 optional CSV upload:

| Input | Type | Notes |
|---|---|---|
| **Target Audience** | Dropdown | The 4 categories above |
| **Location** | Text | Any US location: city, state, or region |
| **Number of Leads** | Number | Default 50, max 200 |
| **CSV Import** (optional) | File upload | Old leads CSV to merge with new results on export |

> [!IMPORTANT]
> **Removed from old plans**: Nano/budget filters, follower tier selector, follower requirements, paid UGC toggle, strict PNW restrictions, bulk JSON import, quality mode selector, product fit selector, result filter dropdown, strict US toggle. All of these are gone. Simple inputs only.

---

## Two-Step Search Pipeline

This is the core difference from the old plan. Instead of one broad search, we do **two passes**:

### Step 1 — Discovery Pass (find names)

For each audience type, run Tavily searches with targeted queries to discover leads. Over-discover by ~40% to account for dedup and bad results.

**Query templates per category:**

```python
DISCOVERY_QUERIES = {
    "dog_parent_influencers": [
        '"dog mom" "{location}" instagram',
        '"pet influencer" "{location}" tiktok',
        '"dog dad" "{location}" content creator',
        '"pet vlogger" "{location}" instagram email',
        '"dog trainer" "{location}" social media',
        '"pet content creator" "{location}"',
    ],
    "online_pet_businesses": [
        '"online pet store" "{location}"',
        '"pet supplies" "{location}" shop',
        '"pet products" "{location}" ecommerce',
        '"pet subscription box" "{location}"',
        '"dog food delivery" "{location}"',
        '"pet accessories" "{location}" online',
    ],
    "pet_shops": [
        '"pet shop" "{location}"',
        '"pet store" "{location}"',
        '"pet supply store" "{location}"',
        '"dog store" "{location}"',
        '"pet supermarket" "{location}"',
        '"local pet shop" "{location}"',
    ],
    "pet_grooming": [
        '"dog grooming" "{location}"',
        '"pet grooming" "{location}"',
        '"dog spa" "{location}"',
        '"mobile dog grooming" "{location}"',
        '"pet salon" "{location}"',
        '"dog wash" "{location}"',
    ],
}
```

**Search settings**: `search_depth: "basic"`, `max_results: 10` per query. This uses ~6 Tavily calls per run.

**Output from Step 1**: A list of ~60-80 raw candidate names/URLs.

### Step 2 — Enrichment Pass (find contact details)

For **each** promising candidate from Step 1, run a **targeted Tavily search** to find their specific contact details:

```python
# For influencers:
f'"{creator_name}" instagram tiktok email contact'

# For businesses/shops:
f'"{business_name}" "{location}" phone email website contact'
```

Then **scrape** the candidate's own website (if found) to extract:
- Email addresses (regex: `[\w.-]+@[\w.-]+\.\w+`)
- Phone numbers (regex for US format)
- Instagram/TikTok URLs
- Website URL

**Search settings**: `search_depth: "basic"`, `max_results: 5` per enrichment query. Budget: up to 50 enrichment calls per run.

> [!IMPORTANT]
> **Why two passes?** The old pipeline did one broad search and hoped the results contained contact info. They usually didn't — leading to tons of "needs review" leads with no email or social handles. By doing a second targeted search per lead, we actually find their contact details.

---

## Scoring & Filtering (Keep It Simple)

### Gemini Scoring

After enrichment, send each lead to Gemini for a quick relevance score (0-10). Use a **40-lead Gemini budget per run**. If Gemini quota is hit, fall back to keyword-based heuristic scoring.

Scoring criteria (simplified):
- **Niche match** (is this actually a pet-related lead?): 0-4 points
- **Has contact info** (email, phone, or social): 0-3 points  
- **Location match** (is the lead actually in the requested location?): 0-3 points

### Quality Gate (Aggressive — Maximize Usable Leads)

A lead is **usable** if it has:
- A name (creator name OR business name)
- At least ONE contact method:
  - For influencers: Instagram handle OR TikTok handle OR email
  - For businesses/shops: Email OR phone OR website

A lead is **rejected** ONLY if:
- It has no name AND no contact info (completely empty)
- It's a duplicate of another lead in this batch
- It's clearly not pet-related (e.g., a car dealership)

> [!IMPORTANT]
> **No "Needs Review" category.** Leads are either usable or rejected. Period. If it has a name and at least one way to contact them, it's usable. This maximizes the number of leads returned to the user.

---

## Lead Schema (Per Category)

### Influencer Lead
```python
{
    "creator_name": str,        # Name / handle
    "email": str,               # Business email if found
    "instagram_handle": str,    # @handle
    "instagram_url": str,       # Full URL
    "tiktok_handle": str,       # @handle
    "tiktok_url": str,          # Full URL
    "phone": str,               # Optional, rarely found
    "website": str,             # Personal site / linktree
    "location": str,            # City, State
    "niche": str,               # "Dog Parent", "Pet Trainer", etc.
    "relevance_score": float,   # 0-10
    "source": str,              # "tavily_discovery"
    "category": str,            # "dog_parent_influencers"
}
```

### Business / Shop / Grooming Lead
```python
{
    "business_name": str,       # Store / company name
    "email": str,               # Contact email
    "phone": str,               # Business phone
    "website": str,             # Business website
    "instagram_handle": str,    # If they have one
    "tiktok_handle": str,       # If they have one
    "location": str,            # Address or City, State
    "niche": str,               # "Pet Shop", "Grooming", etc.
    "relevance_score": float,   # 0-10
    "source": str,              # "tavily_discovery"
    "category": str,            # "pet_shops" / "pet_grooming" / "online_pet_businesses"
}
```

---

## CSV Import & Merge

### Import (Old Leads)
- User can upload a CSV file of previously found leads
- The system reads it, extracts names/emails/handles for dedup purposes
- New leads found in this run are checked against the imported list
- Duplicates are skipped (dedup by: name, email, instagram handle, website domain)

### Export (Merged Download)
- When user clicks "Export", the download contains:
  - **All old rows from the imported CSV** (untouched, in original order)
  - **Plus all new leads** appended at the bottom
- This way the user always has one growing master file

> [!IMPORTANT]
> **JSON import removed.** Only CSV/XLSX import is supported. Simple and practical.

---

## Proposed Changes

---

### Component 1: Vento Pipeline Rewrite

#### [MODIFY] [vento_lead_pipeline.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/vento/vento_lead_pipeline.py)

**Major rewrite.** Strip out the overengineered verification/qualification/daily-batch system. Replace with the simple two-step pipeline:

```python
class VentoLeadPipeline:
    """Simple two-step pet industry lead finder."""

    async def run(
        self,
        *,
        category: str,          # "dog_parent_influencers" | "online_pet_businesses" | "pet_shops" | "pet_grooming"
        location: str,          # "Los Angeles, CA"
        target_count: int = 50, # How many leads user wants
        old_leads_csv: Optional[str] = None,  # CSV text for dedup
    ) -> Dict[str, Any]:

        # Step 1: Discovery — find names
        raw_candidates = await self._discover_candidates(category, location, target_count)

        # Step 2: Enrichment — find contact details for each
        enriched = await self._enrich_candidates(raw_candidates, category)

        # Step 3: Dedup against old leads + within batch
        old_keys = self._extract_dedup_keys_from_csv(old_leads_csv) if old_leads_csv else set()
        deduped = self._dedup(enriched, old_keys)

        # Step 4: Score with Gemini (or heuristic fallback)
        scored = await self._score_leads(deduped, category, location)

        # Step 5: Quality gate — keep usable, reject empty
        final = self._quality_gate(scored)

        return {"leads": final[:target_count], ...}

    async def _discover_candidates(self, category, location, target_count):
        """Step 1: Run 6 Tavily searches, collect 60-80 raw names/URLs."""
        queries = self._build_discovery_queries(category, location)
        # ... tavily search loop ...

    async def _enrich_candidates(self, candidates, category):
        """Step 2: For each candidate, run 1 Tavily search + scrape their site."""
        for candidate in candidates:
            # Search: '"Business Name" "location" phone email website'
            # Scrape: candidate's website for emails, phones, social links
            # ... extract contact details via regex ...

    async def _score_leads(self, leads, category, location):
        """Score with Gemini (budget: 40 calls). Fallback to heuristic."""
        # ... gemini scoring or keyword heuristic ...

    def _quality_gate(self, leads):
        """Keep if: has name + at least 1 contact method. Reject otherwise."""
        # ... simple filter ...
```

Key methods to implement:
- `_build_discovery_queries(category, location)` — returns 6 Tavily query strings
- `_discover_candidates(category, location, target_count)` — runs Step 1
- `_enrich_single_candidate(candidate, category)` — runs Step 2 for one lead
- `_enrich_candidates(candidates, category)` — loops Step 2 over all candidates
- `_extract_emails_from_text(text)` — regex email extraction
- `_extract_phones_from_text(text)` — regex US phone extraction
- `_extract_social_handles_from_text(text)` — regex Instagram/TikTok extraction
- `_dedup(leads, old_keys)` — dedup by name/email/handle/domain
- `_extract_dedup_keys_from_csv(csv_text)` — parse CSV, extract keys for dedup
- `_score_leads(leads, category, location)` — Gemini + heuristic fallback
- `_heuristic_score(lead, category, location)` — keyword-based scoring
- `_quality_gate(leads)` — name + contact = keep; otherwise reject

---

### Component 2: Simplified Discovery Module

#### [MODIFY] [discovery.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/vento/discovery.py)

Rewrite to support the 4 audience categories instead of the old influencer-only approach:

- New `DISCOVERY_QUERIES` dict with templates per category
- New `ENRICHMENT_QUERY_TEMPLATES` dict for Step 2 queries
- Keep `extract_social_handles()` — it works fine
- Remove PNW-specific expansions and follower keywords
- Add US phone regex extraction
- Add website URL extraction from search results

---

### Component 3: API Route Update

#### [MODIFY] [vento_leads.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/api/routes/vento_leads.py)

Simplify the API contract:

```python
class VentoSearchRequest(BaseModel):
    category: str           # "dog_parent_influencers" | "online_pet_businesses" | "pet_shops" | "pet_grooming"
    location: str           # "Los Angeles, CA"
    target_count: int = 50  # 1-200
    old_leads_csv: Optional[str] = None  # CSV text for dedup

@router.post("/search")
async def search(request: VentoSearchRequest):
    pipeline = VentoLeadPipeline()
    return await pipeline.run(
        category=request.category,
        location=request.location,
        target_count=request.target_count,
        old_leads_csv=request.old_leads_csv,
    )

@router.post("/ingest")
async def ingest_csv(file: UploadFile):
    """Upload CSV for old-lead dedup + merge."""
    # ... read file, pass to pipeline ...
```

**Removed endpoints**: `/api/vento/daily-run`, `/api/vento/review/{id}`, `/api/vento/daily-runs`. Too complex for now.

---

### Component 4: UI Overhaul (Vento Panel in leadgen.html)

#### [MODIFY] [leadgen.html](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/ui/leadgen.html)

**Replace the entire Vento panel** (lines ~392-473) with the simplified version:

```html
<div id="vento-panel" class="hidden space-y-4 rounded-2xl border border-emerald-500/15 bg-emerald-500/5 p-4">
  <!-- Target Audience Dropdown -->
  <div>
    <label class="...">Target Audience</label>
    <select id="vento-category" class="field">
      <option value="dog_parent_influencers">🐕 Dog Parent Influencers</option>
      <option value="online_pet_businesses">🛒 Online Pet Businesses</option>
      <option value="pet_shops">🏪 Pet Shops</option>
      <option value="pet_grooming">✂️ Pet Grooming Shops</option>
    </select>
  </div>

  <!-- CSV Import for old leads -->
  <div>
    <label class="...">Import Previous Leads (CSV)</label>
    <div class="flex items-center gap-3">
      <label for="vento-file-input" class="...">Upload CSV</label>
      <input id="vento-file-input" type="file" accept=".csv,.xlsx" class="hidden" />
      <span id="vento-file-name" class="...">No file selected</span>
    </div>
    <p class="text-[9px] text-lv-500 mt-1">
      Upload your existing leads CSV. New leads will be merged when you export.
    </p>
  </div>
</div>
```

**JS changes:**
- When `mode === 'vento'`, the "Generate Leads" button calls `POST /api/vento/search` with `{category, location, target_count}`
- Location input and Target Leads input are reused from the existing shared inputs
- Remove all follower tier, quality mode, product fit, and result filter dropdowns
- Table columns adapt based on category (influencers show Instagram/TikTok; businesses show Phone/Website)
- Export merges old CSV rows + new leads into one downloadable file

---

### Component 5: Google Sheets Tab

#### [MODIFY] [todo_sheet_store.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/todo_sheet_store.py)

Keep the existing "Vento Influencers" tab but simplify the headers to match the new schema:

```python
VENTO_LEAD_HEADERS_V3 = [
    "Name",              # creator_name OR business_name
    "Category",          # dog_parent_influencers / pet_shops / etc.
    "Email",
    "Phone",
    "Website",
    "Instagram",
    "TikTok",
    "Location",
    "Niche",
    "Relevance Score",
    "Source",
    "Status",
    "Notes",
]
```

---

### Component 6: Lead Service Routing

#### [MODIFY] [lead_service.py](file:///c:/Users/Aryan%20Bokolia/Desktop/Aurika-AI%20Intern/lead-gen/core/services/lead_service.py)

The existing `_export_vento_leads()` method routes Vento leads to the dedicated sheet. Update it to use the simplified schema (V3 headers) and skip the complex A/B/C qualification logic.

---

## Files Changed Summary

| Action | File | What Changes |
|---|---|---|
| **REWRITE** | `core/services/vento/vento_lead_pipeline.py` | Strip to simple 2-step pipeline: discover → enrich → dedup → score → gate |
| **REWRITE** | `core/services/vento/discovery.py` | 4 category query templates, enrichment queries, phone/email regex |
| **SIMPLIFY** | `api/routes/vento_leads.py` | 2 endpoints only: `/search` and `/ingest` |
| **MODIFY** | `ui/leadgen.html` | Replace Vento panel with 1 dropdown + CSV upload. Simplify JS |
| **MODIFY** | `core/services/todo_sheet_store.py` | Simplified Vento headers (13 columns instead of 50+) |
| **MODIFY** | `core/services/lead_service.py` | Simplified Vento export (no A/B/C, just save usable leads) |
| **KEEP** | `core/services/vento/__init__.py` | No change |
| **UNUSED** | `core/services/vento/verification.py` | Not deleted, but not called by the new pipeline |
| **UNUSED** | `core/services/vento/qualification.py` | Not deleted, but not called by the new pipeline |
| **UNUSED** | `core/services/vento/daily_batch.py` | Not deleted, but not called by the new pipeline |

---

## API Costs Per Run (50 leads)

| Service | Calls | Free Tier Limit | Safe? |
|---|---|---|---|
| **Tavily** (Step 1 — Discovery) | ~6 searches | 1,000/month | ✅ Yes |
| **Tavily** (Step 2 — Enrichment) | ~50 searches | 1,000/month | ⚠️ ~56 per run, fine for 1 run/day |
| **Gemini** (Scoring) | ~40 calls | 1,500/day | ✅ Yes |
| **Web Scraping** (Step 2 — site scrape) | ~50 requests | No limit | ✅ Yes |

> [!WARNING]
> At 56 Tavily calls per run, you can do about **17 runs per month** on the free tier (1,000 calls/month). That's roughly 1 run per weekday — plenty for 50 leads/day.

---

## Verification Plan

### Manual Testing
1. Run with each of the 4 categories and verify leads come back with correct contact fields
2. Upload a CSV of 20 old leads → run again → verify no duplicates in results
3. Export → verify the downloaded CSV contains old rows + new rows merged
4. Verify Google Sheets "Vento Influencers" tab gets populated

### Automated Checks
- `python -c "from core.services.vento.vento_lead_pipeline import VentoLeadPipeline; print('OK')"` — import check
- Run the server and hit `/api/vento/search` with a test payload

---

## Open Questions

> [!IMPORTANT]
> 1. **Tavily budget**: At ~56 calls per run (6 discovery + 50 enrichment), should I reduce the enrichment budget to save Tavily credits? We could do enrichment for only the top 30 candidates instead of all 50.
> 2. **Category combinations**: Should the user be able to select multiple categories at once (e.g., "Pet Shops + Pet Grooming"), or one at a time?
