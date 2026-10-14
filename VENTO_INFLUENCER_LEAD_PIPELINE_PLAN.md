# Vento Influencer Lead Generation Pipeline — Implementation Plan (v2 — Hybrid Discovery)

## Goal

Build a **high-volume influencer lead discovery pipeline** for the **Vento by Comfort Pod** product that can scale toward **1,000+ leads** quickly while staying within free-tier API limits. The system uses a **hybrid discovery model**: bulk data ingestion as the primary source, with Tavily-based web scraping as an automatic fallback. All leads flow through a unified Gemini-powered enrichment and qualification phase before export to a dedicated Google Sheets tab.

## Background & Product Context

**Product**: Vento by Comfort Pod — An app-controlled, smart cooling fan system with remote temperature monitoring and SMS alerts designed to keep pets safe inside parked cars.

**Campaign Goal**: Recruit ~28 influencers (nano → upper mid-tier, 5K–500K followers) for a July–September UGC campaign across Instagram, TikTok, and YouTube Shorts. Budget: US$23K–27K.

**Target Influencer Archetypes**:
1. **Pet Lifestyle Creators** — "Dog Mom/Dad" accounts, pet vloggers, professional dog trainers
2. **UGC Specialists / Aesthetic Reviewers** — Micro-creators focused on "Car Essentials", "Amazon Finds", problem-solving gadget reviews
3. **PNW/Local Lifestyle Vloggers** — Regional creators in Seattle/Portland who share daily life alongside dogs

**Geographic Focus**: United States, high priority on Seattle / Pacific Northwest (PNW) region.

**Scale Target**: 1,000 qualified leads across multiple US regions, processed in bulk batches.

---

## Scope (Additive Only)

- **Add** a new module: `core/services/vento/` (discovery + pipeline)
- **Add** a new API route: `api/routes/vento_leads.py` → `POST /api/vento/search`, `POST /api/vento/ingest`, `POST /api/vento/export`
- **Modify** `ui/leadgen.html` → Add a third "VENTO" mode button alongside Generic/VelitCamping, plus a bulk upload panel
- **Modify** `api/main.py` → Append route registration (feature-flag gated)
- **Modify** `core/services/todo_sheet_store.py` → Add Vento-specific worksheet + headers
- **No deletion** of existing code, data, or pipelines
- **No changes** to `ProductionLeadPipeline`, `VelitLeadPipeline`, or `LeadService` base classes

## Non-Goals

- No use of official Instagram/TikTok APIs (requires brand accounts & review processes).
- No real-time follower count verification (adds complexity and API calls beyond free tier).
- No separate `vento_leads.html` page — everything integrates into the existing dashboard.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Vento Lead Pipeline — Hybrid Discovery                    │
│                                                                              │
│  ┌─────────────────────────────────┐  ┌────────────────────────────────────┐ │
│  │  PRIMARY: Bulk Data Ingestion   │  │  FALLBACK: Tavily Web Discovery   │ │
│  │                                 │  │                                    │ │
│  │  _ingest_bulk_leads()           │  │  _discover_via_tavily_fallback()  │ │
│  │                                 │  │                                    │ │
│  │  Sources:                       │  │  Activates when:                   │ │
│  │  ├── CSV/XLSX file upload       │  │  ├── No SOCIAL_DATA_API_KEY       │ │
│  │  ├── Pasted text (batch input)  │  │  ├── No bulk data uploaded        │ │
│  │  ├── SOCIAL_DATA_API_KEY        │  │  ├── API rate limit hit           │ │
│  │  │   (RapidAPI / Apify)         │  │  └── Bulk returns < target_count  │ │
│  │  └── JSON API payload           │  │                                    │ │
│  │                                 │  │  Constraints:                      │ │
│  │  Expects structured fields:     │  │  ├── VENTO_SEARCH_DEPTH = "basic" │ │
│  │  Name, Email, Instagram,       │  │  ├── Max 6 query loops             │ │
│  │  TikTok, Location,             │  │  └── Gemini: rule-based fallback  │ │
│  │  Follower Count                 │  │                                    │ │
│  └────────────┬────────────────────┘  └──────────────┬─────────────────────┘ │
│               │                                      │                       │
│               └──────────────┬───────────────────────┘                       │
│                              ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │              UNIFIED ENRICHMENT & QUALIFICATION                      │   │
│  │                                                                       │   │
│  │  1. _normalize_raw_leads()                                           │   │
│  │     ├── Clean & standardize all fields                               │   │
│  │     ├── Validate email format                                        │   │
│  │     ├── Normalize Instagram/TikTok handles                           │   │
│  │     └── Dedup by Instagram handle → email → domain                   │   │
│  │                                                                       │   │
│  │  2. _score_influencer_leads()  [Gemini-powered]                      │   │
│  │     ├── Prioritize records WITH email first (conserve LLM credits)   │   │
│  │     ├── Score niche fit (pet / car-gadget / lifestyle)               │   │
│  │     ├── Score location match (PNW=10, US-major=7, US=5)             │   │
│  │     ├── Estimate follower tier from context                          │   │
│  │     └── Generate value_proposition per lead                          │   │
│  │                                                                       │   │
│  │  3. _apply_quality_gate()                                            │   │
│  │     ├── Must have: name + ≥1 contact method (email/insta/tiktok)    │   │
│  │     ├── Reject: no social handles AND no email                       │   │
│  │     └── Soft-filter: non-US creators get lower score, not rejected   │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                              ▼                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │              OUTPUT & EXPORT                                          │   │
│  │                                                                       │   │
│  │  ├── Return to frontend (leadgen.html Vento mode table)              │   │
│  │  ├── Auto-save to Google Sheets → "Vento Influencers" tab            │   │
│  │  └── Download as .XLSX / .CSV with influencer-specific columns       │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Output Fields Per Lead:                                                     │
│    creator_name, email, instagram_handle, instagram_url,                     │
│    tiktok_handle, tiktok_url, youtube_channel, phone,                        │
│    website, location, niche, estimated_follower_tier,                        │
│    relevance_score, value_proposition, quality_score,                         │
│    source (bulk_ingest | tavily_fallback), media_kit_url                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Proposed Changes

---

### Component 1: Vento Discovery Module

#### [NEW] `core/services/vento/__init__.py`

Empty init file for the new module.

#### [NEW] `core/services/vento/discovery.py`

Mirrors the Velit `core/services/velit/discovery.py` pattern but with influencer-specific search queries and filtering. Used only by the Tavily fallback path.

```python
VENTO_SEARCH_DEPTH = "basic"        # Hard-locked to basic for free-tier conservation
VENTO_EXTRACT_DEPTH = "basic"
VENTO_MAX_QUERY_LOOPS = 6           # Restrict query count to save API calls

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

# Social platform domains — whitelisted (NOT noise) for this pipeline
_SOCIAL_PLATFORMS = (
    "instagram.com", "tiktok.com", "youtube.com",
    "linktr.ee", "linkin.bio", "beacons.ai",
    "bio.link", "stan.store", "koji.to",
)

# PNW location expansions (same pattern as _STATE_CITY_EXPANSIONS in velit)
_PNW_CITY_EXPANSIONS = {
    "seattle": ["Seattle", "Bellevue", "Tacoma", "Redmond", "Kirkland", "Everett"],
    "portland": ["Portland", "Beaverton", "Hillsboro", "Gresham", "Lake Oswego"],
    "pnw": ["Seattle", "Portland", "Tacoma", "Bellevue", "Eugene", "Bend"],
    "pacific northwest": ["Seattle", "Portland", "Tacoma", "Bellevue", "Eugene", "Bend"],
}

def build_vento_queries(
    *, location: str, influencer_type: str = "all",
    seed_query: str = "", max_queries: int = VENTO_MAX_QUERY_LOOPS,
) -> List[str]:
    """Build Tavily search queries targeting influencer discovery.

    Queries are crafted per influencer archetype:
    - pet:      '"pet influencer" "Seattle" instagram email contact'
    - gadget:   '"car accessories reviewer" "Seattle" "collaboration" email'
    - lifestyle:'"pnw lifestyle vlogger" "Seattle" instagram tiktok'
    - all:      mix of the above, capped at max_queries
    """

def build_vento_shortfall_queries(
    *, location: str, pass_index: int = 1,
    seed_query: str = "", max_queries: int = 4,
) -> List[str]:
    """Additional queries when initial discovery falls short of target."""

def looks_like_influencer_text(text: str) -> bool:
    """Check if text contains influencer-related keywords."""

def extract_social_handles(text: str) -> Dict[str, List[str]]:
    """Extract Instagram, TikTok, YouTube handles from text via regex.

    Patterns:
    - instagram.com/handle → {"instagram": ["handle"]}
    - tiktok.com/@handle → {"tiktok": ["handle"]}
    - youtube.com/@handle or /c/channel → {"youtube": ["handle"]}
    - @handle near 'instagram'/'insta' keyword → {"instagram": ["handle"]}
    """

def normalize_social_handle(handle: str, platform: str) -> str:
    """Strip leading @, trailing slashes, query params from a handle."""
```

**Key design decisions**:
- `VENTO_SEARCH_DEPTH` is hard-locked to `"basic"` — no override allowed, to stay within free-tier Tavily limits
- `VENTO_MAX_QUERY_LOOPS = 6` — strict cap on total Tavily calls per fallback run
- Social platform domains (`instagram.com`, `tiktok.com`) are **whitelisted** here, unlike in velit/generic where they are noise
- PNW-specific location expansions for Seattle/Portland/Pacific Northwest

---

### Component 2: Vento Lead Pipeline

#### [NEW] `core/services/vento/vento_lead_pipeline.py`

Extends `ProductionLeadPipeline` (same pattern as `VelitLeadPipeline`) with the hybrid discovery model.

```python
import os
import csv
import io
import json
from typing import Any, Dict, List, Optional

class VentoLeadPipeline(ProductionLeadPipeline):
    """Hybrid influencer discovery pipeline for the Vento by Comfort Pod campaign.

    Execution order:
    1. If bulk data is provided (file upload / pasted text / API payload) →
       _ingest_bulk_leads()
    2. If SOCIAL_DATA_API_KEY is set and no bulk data →
       _fetch_from_social_data_api()
    3. If neither available, OR results < target_count →
       _discover_via_tavily_fallback()
    4. All results → _normalize_raw_leads() → _score_influencer_leads() →
       _apply_quality_gate()
    """

    CONTACT_PATHS = (
        "", "/contact", "/about", "/media-kit", "/press",
        "/collaborate", "/partnerships", "/work-with-me",
        "/hire-me", "/brands", "/collabs",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.linkedin_enrichment_limit = 0   # Not relevant for influencers
        self.max_contact_scrapes = 30
        self.contact_search_limit = 6
        self.social_data_api_key = os.getenv("SOCIAL_DATA_API_KEY", "")

    # ──────────────────────────────────────────────────────────────────────
    # MAIN ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────

    async def run(
        self,
        *,
        location: str = "",
        influencer_type: str = "all",   # "pet", "gadget", "lifestyle", "all"
        follower_tier: str = "all",     # "nano", "mid", "upper_mid", "all"
        target_count: int = 50,
        seed_query: str = "",
        bulk_data: Optional[str] = None,        # Raw CSV/TSV/JSON text pasted by user
        bulk_file_path: Optional[str] = None,   # Path to uploaded CSV/XLSX file
    ) -> Dict[str, Any]:
        steps = []
        raw_leads: List[Dict[str, Any]] = []

        # ── Phase 1: Primary — Bulk Data Ingestion ──
        if bulk_data or bulk_file_path:
            ingested = self._ingest_bulk_leads(
                raw_text=bulk_data,
                file_path=bulk_file_path,
            )
            raw_leads.extend(ingested)
            steps.append({
                "phase": "bulk_ingest",
                "status": "completed",
                "count": len(ingested),
            })

        # ── Phase 1b: Primary — Social Data API (if configured) ──
        if not raw_leads and self.social_data_api_key:
            api_leads = await self._fetch_from_social_data_api(
                location=location,
                influencer_type=influencer_type,
                follower_tier=follower_tier,
                limit=target_count,
            )
            raw_leads.extend(api_leads)
            steps.append({
                "phase": "social_data_api",
                "status": "completed" if api_leads else "no_results",
                "count": len(api_leads),
            })

        # ── Phase 2: Fallback — Tavily Discovery ──
        #    Executes if: no bulk data, no API key, or results < target_count
        if len(raw_leads) < target_count:
            shortfall = target_count - len(raw_leads)
            tavily_leads = await self._discover_via_tavily_fallback(
                location=location,
                influencer_type=influencer_type,
                seed_query=seed_query,
                target_count=min(shortfall, 20),  # Cap fallback to 20
            )
            raw_leads.extend(tavily_leads)
            steps.append({
                "phase": "tavily_fallback",
                "status": "completed",
                "count": len(tavily_leads),
                "reason": "shortfall" if raw_leads else "primary_unavailable",
            })

        # ── Phase 3: Unified Enrichment & Qualification ──
        normalized = self._normalize_raw_leads(raw_leads)
        scored = await self._score_influencer_leads(
            normalized,
            location=location,
            influencer_type=influencer_type,
        )
        final_leads = self._apply_vento_quality_gate(scored)
        final_leads = final_leads[:target_count]

        steps.append({
            "phase": "enrichment_and_scoring",
            "status": "completed",
            "input_count": len(normalized),
            "scored_count": len(scored),
            "final_count": len(final_leads),
        })

        return {
            "leads": final_leads,
            "steps": steps,
            "metadata": {
                "pipeline": "vento_influencer_pipeline",
                "total_raw_ingested": len(raw_leads),
                "total_normalized": len(normalized),
                "total_scored": len(scored),
                "total_leads": len(final_leads),
                "leads_with_email": sum(1 for l in final_leads if l.get("email")),
                "leads_with_instagram": sum(1 for l in final_leads if l.get("instagram_handle")),
                "leads_with_tiktok": sum(1 for l in final_leads if l.get("tiktok_handle")),
                "leads_with_phone": sum(1 for l in final_leads if l.get("phone")),
                "discovery_source": self._determine_primary_source(steps),
            },
        }

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 1: PRIMARY — BULK DATA INGESTION
    # ──────────────────────────────────────────────────────────────────────

    def _ingest_bulk_leads(
        self,
        *,
        raw_text: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Accept structured bulk data and parse into normalized lead dicts.

        Supported input formats:
        - CSV text (auto-detected by comma/tab separators)
        - JSON text (array of objects)
        - XLSX/CSV file path

        Expected columns (case-insensitive, flexible matching):
        Name | Email | Instagram | TikTok | Location | Follower Count | YouTube | Phone

        Returns list of raw lead dicts with standardized keys.
        """
        leads: List[Dict[str, Any]] = []

        if file_path:
            leads.extend(self._parse_file(file_path))
        if raw_text:
            leads.extend(self._parse_raw_text(raw_text))

        return leads

    def _parse_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse CSV or XLSX file into lead dicts."""
        if file_path.endswith((".xlsx", ".xls")):
            return self._parse_xlsx(file_path)
        return self._parse_csv_file(file_path)

    def _parse_raw_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse pasted CSV/TSV or JSON text into lead dicts."""
        text = text.strip()
        if text.startswith("["):
            # JSON array
            try:
                rows = json.loads(text)
                return [self._map_flexible_columns(row) for row in rows if isinstance(row, dict)]
            except json.JSONDecodeError:
                pass
        # CSV/TSV auto-detect
        dialect = csv.Sniffer().sniff(text[:2000])
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        return [self._map_flexible_columns(row) for row in reader]

    @staticmethod
    def _map_flexible_columns(row: Dict[str, Any]) -> Dict[str, Any]:
        """Map flexible/messy column names to canonical lead fields.

        Handles: 'Name', 'name', 'Creator Name', 'Full Name', 'creator_name'
                 'Email', 'email', 'Email Address', 'contact_email'
                 'Instagram', 'instagram', 'IG', 'ig_handle', 'instagram_handle'
                 'TikTok', 'tiktok', 'TT', 'tiktok_handle'
                 etc.
        """
        def _find(keys):
            for key in keys:
                for col, val in row.items():
                    if col.strip().lower().replace(" ", "_").replace("-", "_") == key:
                        return str(val or "").strip()
            return ""

        return {
            "creator_name": _find(["name", "creator_name", "full_name", "influencer_name", "creator"]),
            "email": _find(["email", "email_address", "contact_email", "e_mail"]),
            "instagram_handle": _find(["instagram", "ig", "ig_handle", "instagram_handle", "insta", "instagram_username"]),
            "tiktok_handle": _find(["tiktok", "tt", "tiktok_handle", "tiktok_username", "tt_handle"]),
            "youtube_channel": _find(["youtube", "yt", "youtube_channel", "youtube_handle", "yt_channel"]),
            "phone": _find(["phone", "phone_number", "contact_phone", "mobile"]),
            "location": _find(["location", "city", "region", "area", "geo"]),
            "follower_count": _find(["follower_count", "followers", "follower", "audience_size"]),
            "website": _find(["website", "url", "blog", "site"]),
            "niche": _find(["niche", "category", "vertical", "content_type"]),
            "source": "bulk_ingest",
        }

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 1b: PRIMARY — SOCIAL DATA API
    # ──────────────────────────────────────────────────────────────────────

    async def _fetch_from_social_data_api(
        self,
        *,
        location: str,
        influencer_type: str,
        follower_tier: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Hit an indexed social data endpoint (RapidAPI / Apify) to pull
        creator records in batch.

        Requires: SOCIAL_DATA_API_KEY env var.
        Falls back gracefully (returns []) on any failure.

        The exact API shape is configurable via SOCIAL_DATA_API_URL env var.
        Default behavior: POST to the configured URL with location/niche/tier
        filters, receive JSON array of creator records.
        """
        api_url = os.getenv("SOCIAL_DATA_API_URL", "")
        if not api_url or not self.social_data_api_key:
            return []

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {self.social_data_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "location": location,
                        "niche": self._map_influencer_type_to_niche(influencer_type),
                        "follower_min": self._tier_to_follower_range(follower_tier)[0],
                        "follower_max": self._tier_to_follower_range(follower_tier)[1],
                        "limit": limit,
                    },
                )
                if response.status_code != 200:
                    self.logger.warning("vento_social_api_error", extra={"status": response.status_code})
                    return []
                data = response.json()
                records = data if isinstance(data, list) else data.get("results", data.get("data", []))
                return [self._map_flexible_columns(record) for record in records]
        except Exception as exc:
            self.logger.warning("vento_social_api_failed", extra={"error": str(exc)})
            return []

    @staticmethod
    def _tier_to_follower_range(tier: str) -> tuple:
        ranges = {
            "nano": (5000, 20000),
            "mid": (20000, 100000),
            "upper_mid": (100000, 500000),
            "all": (5000, 500000),
        }
        return ranges.get(tier, ranges["all"])

    @staticmethod
    def _map_influencer_type_to_niche(influencer_type: str) -> str:
        mapping = {
            "pet": "pet lifestyle",
            "gadget": "product review",
            "lifestyle": "lifestyle",
            "all": "pet,product review,lifestyle",
        }
        return mapping.get(influencer_type, mapping["all"])

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 2: FALLBACK — TAVILY WEB DISCOVERY
    # ──────────────────────────────────────────────────────────────────────

    async def _discover_via_tavily_fallback(
        self,
        *,
        location: str,
        influencer_type: str = "all",
        seed_query: str = "",
        target_count: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fallback discovery using Tavily search + web scraping + regex parsing.

        This is the original custom discovery plan, kept as a strict fallback.
        Automatically executes when:
        - No SOCIAL_DATA_API_KEY is configured
        - No bulk data was uploaded/pasted
        - The primary source returned fewer leads than target_count

        Constraints (free-tier conservation):
        - VENTO_SEARCH_DEPTH = "basic" (enforced, not overridable)
        - Max VENTO_MAX_QUERY_LOOPS (6) Tavily search calls
        - Gemini scoring falls back to rule-based if quota exhausted

        Discovery flow:
        1. Build influencer-specific Tavily queries via build_vento_queries()
        2. Execute searches, collect results (social URLs NOT filtered as noise)
        3. Resolve creator profiles — scrape linktrees, media kits, bio pages
        4. Extract social handles via regex from page content
        5. Return raw lead dicts for unified enrichment
        """
        from core.services.vento.discovery import (
            build_vento_queries,
            build_vento_shortfall_queries,
            looks_like_influencer_text,
            extract_social_handles,
            VENTO_SEARCH_DEPTH,
            VENTO_MAX_QUERY_LOOPS,
        )

        queries = build_vento_queries(
            location=location,
            influencer_type=influencer_type,
            seed_query=seed_query,
            max_queries=VENTO_MAX_QUERY_LOOPS,
        )

        raw_leads: List[Dict[str, Any]] = []
        seen_urls: set = set()

        for query in queries:
            try:
                data = await self.tavily.search({
                    "query": query,
                    "search_depth": VENTO_SEARCH_DEPTH,
                    "max_results": 10,
                    "include_raw_content": False,
                    # NOTE: Do NOT exclude social domains — they are targets
                })
            except Exception as exc:
                self.logger.warning("vento_tavily_search_failed", extra={"error": str(exc)})
                continue

            for item in data.get("results") or []:
                url = str(item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = str(item.get("title") or "").strip()
                content = str(item.get("content") or "").strip()
                combined = f"{title} {content}"

                # Extract social handles from search snippet
                handles = extract_social_handles(combined)

                raw_leads.append({
                    "creator_name": self._infer_creator_name(title, url),
                    "email": self._first_valid_email(combined) or "",
                    "instagram_handle": (handles.get("instagram") or [""])[0],
                    "tiktok_handle": (handles.get("tiktok") or [""])[0],
                    "youtube_channel": (handles.get("youtube") or [""])[0],
                    "phone": "",
                    "website": url,
                    "location": location,
                    "niche": influencer_type if influencer_type != "all" else "",
                    "source": "tavily_fallback",
                    "raw_title": title,
                    "raw_content": content[:2000],
                })

            if len(raw_leads) >= target_count:
                break

        # Shortfall pass if needed
        if len(raw_leads) < target_count:
            shortfall_queries = build_vento_shortfall_queries(
                location=location,
                pass_index=1,
                seed_query=seed_query,
                max_queries=min(4, VENTO_MAX_QUERY_LOOPS - len(queries)),
            )
            for query in shortfall_queries:
                if len(raw_leads) >= target_count:
                    break
                try:
                    data = await self.tavily.search({
                        "query": query,
                        "search_depth": VENTO_SEARCH_DEPTH,
                        "max_results": 8,
                        "include_raw_content": False,
                    })
                except Exception:
                    continue
                for item in data.get("results") or []:
                    url = str(item.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = str(item.get("title") or "").strip()
                    content = str(item.get("content") or "").strip()
                    handles = extract_social_handles(f"{title} {content}")
                    raw_leads.append({
                        "creator_name": self._infer_creator_name(title, url),
                        "email": self._first_valid_email(f"{title} {content}") or "",
                        "instagram_handle": (handles.get("instagram") or [""])[0],
                        "tiktok_handle": (handles.get("tiktok") or [""])[0],
                        "youtube_channel": (handles.get("youtube") or [""])[0],
                        "phone": "",
                        "website": url,
                        "location": location,
                        "niche": influencer_type if influencer_type != "all" else "",
                        "source": "tavily_fallback",
                    })

        return raw_leads[:target_count]

    # ──────────────────────────────────────────────────────────────────────
    # PHASE 3: UNIFIED ENRICHMENT & QUALIFICATION
    # ──────────────────────────────────────────────────────────────────────

    def _normalize_raw_leads(self, raw_leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Clean, standardize, and dedup all leads regardless of source.

        Steps:
        1. Strip whitespace, normalize empty values
        2. Normalize Instagram handles (strip @, trailing /, query params)
        3. Normalize TikTok handles (strip @, trailing /)
        4. Validate email format (reject obviously invalid)
        5. Build Instagram/TikTok URLs from handles
        6. Dedup by: instagram_handle (primary) → email → website domain
        7. Sort: leads WITH email first (for Gemini scoring priority)
        """
        normalized: List[Dict[str, Any]] = []
        seen_instagram: set = set()
        seen_email: set = set()
        seen_domain: set = set()

        for lead in raw_leads:
            # Normalize handles
            ig = self._normalize_handle(lead.get("instagram_handle", ""))
            tt = self._normalize_handle(lead.get("tiktok_handle", ""))
            email = str(lead.get("email", "")).strip().lower()
            domain = self._extract_domain(lead.get("website", ""))

            # Dedup
            if ig and ig in seen_instagram:
                continue
            if not ig and email and email in seen_email:
                continue
            if not ig and not email and domain and domain in seen_domain:
                continue

            if ig:
                seen_instagram.add(ig)
            if email:
                seen_email.add(email)
            if domain:
                seen_domain.add(domain)

            normalized.append({
                "creator_name": str(lead.get("creator_name", "")).strip(),
                "email": email if self._is_valid_email_format(email) else "",
                "instagram_handle": f"@{ig}" if ig else "",
                "instagram_url": f"https://instagram.com/{ig}" if ig else "",
                "tiktok_handle": f"@{tt}" if tt else "",
                "tiktok_url": f"https://tiktok.com/@{tt}" if tt else "",
                "youtube_channel": str(lead.get("youtube_channel", "")).strip(),
                "youtube_url": self._build_youtube_url(lead.get("youtube_channel", "")),
                "phone": str(lead.get("phone", "")).strip(),
                "website": str(lead.get("website", "")).strip(),
                "media_kit_url": "",
                "linktree_url": "",
                "location": str(lead.get("location", "")).strip(),
                "niche": str(lead.get("niche", "")).strip(),
                "follower_count": str(lead.get("follower_count", "")).strip(),
                "estimated_follower_tier": self._estimate_tier_from_count(lead.get("follower_count", "")),
                "source": str(lead.get("source", "unknown")).strip(),
                "raw_title": str(lead.get("raw_title", "")).strip(),
                "raw_content": str(lead.get("raw_content", "")).strip()[:2000],
            })

        # Sort: leads with email first (Gemini scoring priority)
        normalized.sort(key=lambda l: (0 if l.get("email") else 1, l.get("creator_name", "")))
        return normalized

    async def _score_influencer_leads(
        self,
        leads: List[Dict[str, Any]],
        *,
        location: str,
        influencer_type: str,
    ) -> List[Dict[str, Any]]:
        """Gemini-powered scoring specific to Vento campaign fit.

        Scoring order: leads WITH email are scored first to conserve LLM credits.
        If Gemini quota is exhausted, falls back to rule-based heuristic scoring.

        Scoring criteria:
        - Niche fit (pet=10, car-gadget=7, lifestyle=5, generic=3)
        - Location match (Seattle/PNW=10, major US=7, US=5, non-US=2)
        - Has media kit / collaboration page = +2 bonus
        - Number of social platforms present = +1 per platform
        - Has email = +2 bonus
        """
        scored: List[Dict[str, Any]] = []
        gemini_budget = min(len(leads), 40)  # Max 40 Gemini calls per run
        gemini_used = 0

        for lead in leads:
            if gemini_used < gemini_budget and self._gemini_client:
                try:
                    ai_score = await self._gemini_score_influencer(lead, location=location)
                    lead.update(ai_score)
                    gemini_used += 1
                except Exception:
                    # Quota hit — switch to heuristic for remaining
                    lead.update(self._heuristic_score_influencer(lead, location=location))
            else:
                lead.update(self._heuristic_score_influencer(lead, location=location))

            # Calculate contact_method_count
            contact_count = sum(1 for field in ["email", "instagram_handle", "tiktok_handle", "youtube_channel", "phone"]
                                if lead.get(field))
            lead["contact_method_count"] = contact_count
            scored.append(lead)

        scored.sort(key=lambda l: l.get("relevance_score", 0), reverse=True)
        return scored

    async def _gemini_score_influencer(
        self, lead: Dict[str, Any], *, location: str,
    ) -> Dict[str, Any]:
        """Call Gemini to score a single influencer lead for Vento campaign fit."""
        prompt = json.dumps({
            "task": "Score this influencer for the Vento pet car cooling fan campaign.",
            "product": "Vento by Comfort Pod — smart cooling fan for parked cars, keeps pets safe",
            "creator": {
                "name": lead.get("creator_name", ""),
                "instagram": lead.get("instagram_handle", ""),
                "tiktok": lead.get("tiktok_handle", ""),
                "location": lead.get("location", ""),
                "niche": lead.get("niche", ""),
                "bio_text": lead.get("raw_content", "")[:3000],
            },
            "target_location": location,
            "scoring_criteria": [
                "NICHE FIT (0-10): pet safety / car accessories / outdoor lifestyle",
                "AUDIENCE MATCH (0-10): US pet owners, dog parents, tech-savvy consumers",
                "CONTENT QUALITY (0-10): media kit, multiple platforms, engagement signals",
                "LOCATION MATCH (0-10): Seattle/PNW=10, major US=7, US=5, non-US=2",
            ],
            "output_schema": {
                "relevance_score": "0-10 float",
                "niche": "string (Pet Lifestyle / Gadget Reviewer / Lifestyle / General)",
                "estimated_tier": "nano | mid | upper_mid",
                "value_proposition": "one sentence describing why this creator is good for Vento",
            },
        }, ensure_ascii=False)

        parsed = await self._gemini_json(
            prompt=prompt,
            system_prompt=VENTO_INFLUENCER_SCORING_PROMPT,
            max_output_tokens=200,
        )
        return {
            "relevance_score": self._coerce_score_10(parsed.get("relevance_score", 5)),
            "quality_score": self._coerce_score_10(parsed.get("relevance_score", 5)) * 10,
            "niche": parsed.get("niche", lead.get("niche", "")),
            "estimated_follower_tier": parsed.get("estimated_tier", lead.get("estimated_follower_tier", "")),
            "value_proposition": parsed.get("value_proposition", ""),
        }

    def _heuristic_score_influencer(
        self, lead: Dict[str, Any], *, location: str,
    ) -> Dict[str, Any]:
        """Rule-based fallback scoring when Gemini quota is exhausted."""
        score = 5.0  # Base score

        # Niche bonus
        niche = (lead.get("niche") or lead.get("raw_content") or "").lower()
        if any(kw in niche for kw in ("pet", "dog", "animal", "puppy")):
            score += 2.0
        elif any(kw in niche for kw in ("car", "gadget", "review", "amazon", "essentials")):
            score += 1.5
        elif any(kw in niche for kw in ("lifestyle", "vlog", "adventure")):
            score += 1.0

        # Location bonus
        loc = (lead.get("location") or "").lower()
        if any(city in loc for city in ("seattle", "portland", "tacoma", "bellevue", "pnw", "pacific northwest")):
            score += 2.0
        elif any(state in loc for state in ("wa", "or", "washington", "oregon")):
            score += 1.5

        # Contact method bonus
        if lead.get("email"):
            score += 1.0
        if lead.get("instagram_handle"):
            score += 0.5
        if lead.get("tiktok_handle"):
            score += 0.5

        score = max(0, min(score, 10))
        return {
            "relevance_score": round(score, 1),
            "quality_score": int(score * 10),
            "niche": lead.get("niche", "General"),
            "estimated_follower_tier": lead.get("estimated_follower_tier", ""),
            "value_proposition": "",
        }

    def _apply_vento_quality_gate(self, leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Quality gate for influencer leads.

        Must have: creator_name + at least one contact method (email OR instagram OR tiktok)
        Reject: no name AND no social handles AND no email
        Soft-filter: non-US creators get lower score but are NOT rejected
        """
        gated: List[Dict[str, Any]] = []
        for lead in leads:
            name = lead.get("creator_name", "").strip()
            has_contact = any(lead.get(field) for field in
                             ["email", "instagram_handle", "tiktok_handle", "youtube_channel", "phone"])
            if not name and not has_contact:
                continue  # Reject: completely empty
            if not has_contact:
                continue  # Reject: name but zero contact methods
            lead["usable"] = True
            lead["rejected"] = False
            gated.append(lead)
        return gated

    # ──────────────────────────────────────────────────────────────────────
    # HELPER METHODS
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_handle(handle: str) -> str:
        """Strip @, trailing slashes, query params from a social handle."""
        cleaned = str(handle or "").strip().lstrip("@").rstrip("/")
        cleaned = cleaned.split("?")[0].split("#")[0]
        # If it's a full URL, extract just the handle part
        if "instagram.com/" in cleaned:
            cleaned = cleaned.split("instagram.com/")[-1].rstrip("/")
        if "tiktok.com/@" in cleaned:
            cleaned = cleaned.split("tiktok.com/@")[-1].rstrip("/")
        elif "tiktok.com/" in cleaned:
            cleaned = cleaned.split("tiktok.com/")[-1].lstrip("@").rstrip("/")
        return cleaned.lower() if cleaned else ""

    @staticmethod
    def _estimate_tier_from_count(count_str: str) -> str:
        """Estimate follower tier from a count string."""
        text = str(count_str or "").strip().lower().replace(",", "").replace("k", "000").replace("m", "000000")
        try:
            count = int(float(text))
        except (ValueError, TypeError):
            return ""
        if count < 20000:
            return "nano"
        if count < 100000:
            return "mid"
        return "upper_mid"

    @staticmethod
    def _build_youtube_url(channel: str) -> str:
        cleaned = str(channel or "").strip()
        if not cleaned:
            return ""
        if cleaned.startswith("http"):
            return cleaned
        return f"https://youtube.com/@{cleaned.lstrip('@')}"

    @staticmethod
    def _determine_primary_source(steps: List[Dict]) -> str:
        for step in steps:
            if step.get("count", 0) > 0:
                return step.get("phase", "unknown")
        return "none"
```

**Gemini System Prompt** (referenced as `VENTO_INFLUENCER_SCORING_PROMPT`):

```python
VENTO_INFLUENCER_SCORING_PROMPT = """
You are an influencer campaign analyst for Comfort Pod (Vento product).
Vento is a smart cooling fan for parked cars that keeps pets safe.
You are scoring creators for a UGC campaign (July-September, US-focused).

Score ONLY based on the data provided. Do not invent information.
Output only valid JSON matching the requested schema.
Be strict: generic/irrelevant creators should score 3 or below.
Pet-focused creators in the PNW region should score 8+.
"""
```

---

### Component 3: API Routes

#### [NEW] `api/routes/vento_leads.py`

```python
router = APIRouter()

class VentoSearchRequest(BaseModel):
    location: str = ""
    influencer_type: str = "all"        # "pet", "gadget", "lifestyle", "all"
    follower_tier: str = "all"          # "nano", "mid", "upper_mid", "all"
    target_count: int = Field(default=50, ge=1, le=1000)
    seed_query: str = ""
    bulk_data: Optional[str] = None     # Pasted CSV/JSON text

class VentoExportRequest(BaseModel):
    leads: List[Dict[str, Any]]

@router.post("/search")
async def search_influencers(request: VentoSearchRequest) -> Dict[str, Any]:
    """Run the hybrid Vento pipeline (bulk ingest OR Tavily fallback)."""
    pipeline = VentoLeadPipeline()
    return await pipeline.run(
        location=request.location,
        influencer_type=request.influencer_type,
        follower_tier=request.follower_tier,
        target_count=request.target_count,
        seed_query=request.seed_query,
        bulk_data=request.bulk_data,
    )

@router.post("/ingest")
async def ingest_bulk_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload a CSV/XLSX file for bulk influencer ingestion."""
    # Save temp file, run pipeline with file_path, return results
    import tempfile, shutil
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        pipeline = VentoLeadPipeline()
        return await pipeline.run(bulk_file_path=tmp_path, target_count=1000)
    finally:
        os.unlink(tmp_path)

@router.post("/export")
async def export_vento_leads(request: VentoExportRequest) -> Dict[str, Any]:
    """Export leads to Google Sheets → 'Vento Influencers' tab."""
    state = get_state()
    if not state.todo_store:
        raise HTTPException(status_code=500, detail="Google Sheets not configured")
    service = LeadService(state.todo_store)
    return await service.export_leads(request.leads, mode="vento")
```

**API Contract**:

**POST `/api/vento/search`** — Search with optional pasted bulk data:
```json
{
    "location": "Seattle, WA",
    "influencer_type": "pet",
    "follower_tier": "mid",
    "target_count": 100,
    "bulk_data": "Name,Email,Instagram,Location\nJane Smith,jane@x.com,@janedogmom,Seattle\n..."
}
```

**POST `/api/vento/ingest`** — Upload CSV/XLSX file (multipart form):
```
Content-Type: multipart/form-data
file: influencers.csv
```

**POST `/api/vento/export`** — Export to Google Sheets:
```json
{
    "leads": [...]
}
```

---

#### [MODIFY] `api/main.py` — ADDITIVE ONLY

Append route registration at the bottom (same pattern as existing routes):

```python
# ── Vento Influencer Lead Pipeline ──
if _include_optional_route("ENABLE_VENTO_PIPELINE", True):
    try:
        from api.routes import vento_leads as vento_leads_route
        app.include_router(vento_leads_route.router, prefix="/api/vento", tags=["Vento Leads"])
    except Exception as exc:
        print(f"Vento pipeline disabled: {exc}")
```

No new UI page route needed — Vento mode lives inside the existing `/leads` page.

---

### Component 4: Google Sheets — Dedicated "Vento Influencers" Tab

#### [MODIFY] `core/services/todo_sheet_store.py`

Add a new worksheet name + header set for the Vento influencer schema:

```python
# Add alongside existing LEAD_HEADERS
VENTO_LEAD_HEADERS = [
    "Creator Name",
    "Email",
    "Instagram Handle",
    "Instagram URL",
    "TikTok Handle",
    "TikTok URL",
    "YouTube Channel",
    "YouTube URL",
    "Phone",
    "Website",
    "Location",
    "Niche",
    "Follower Tier",          # nano / mid / upper_mid
    "Relevance Score",        # 0-10
    "Quality Score",          # 0-100
    "Value Proposition",
    "Source",                  # bulk_ingest / tavily_fallback / social_data_api
    "Status",
    "Notes",
]

# In __init__:
self.vento_leads_worksheet_name = os.getenv("VENTO_LEADS_WORKSHEET_NAME", "Vento Influencers")

# In ensure_store():
self._vento_leads_ws = self._ensure_worksheet(self._spreadsheet, self.vento_leads_worksheet_name)
self._vento_lead_headers_current = self._ensure_headers(self._vento_leads_ws, self.VENTO_LEAD_HEADERS)

# New method:
def save_vento_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
    """Append a single influencer lead to the 'Vento Influencers' worksheet."""
    self._require_ready()
    row_data = {
        "Creator Name": str(lead.get("creator_name", "")).strip(),
        "Email": str(lead.get("email", "")).strip(),
        "Instagram Handle": str(lead.get("instagram_handle", "")).strip(),
        "Instagram URL": str(lead.get("instagram_url", "")).strip(),
        "TikTok Handle": str(lead.get("tiktok_handle", "")).strip(),
        "TikTok URL": str(lead.get("tiktok_url", "")).strip(),
        "YouTube Channel": str(lead.get("youtube_channel", "")).strip(),
        "YouTube URL": str(lead.get("youtube_url", "")).strip(),
        "Phone": str(lead.get("phone", "")).strip(),
        "Website": str(lead.get("website", "")).strip(),
        "Location": str(lead.get("location", "")).strip(),
        "Niche": str(lead.get("niche", "")).strip(),
        "Follower Tier": str(lead.get("estimated_follower_tier", "")).strip(),
        "Relevance Score": str(lead.get("relevance_score", "")).strip(),
        "Quality Score": str(lead.get("quality_score", "")).strip(),
        "Value Proposition": str(lead.get("value_proposition", "")).strip(),
        "Source": str(lead.get("source", "")).strip(),
        "Status": str(lead.get("status", "New")).strip() or "New",
        "Notes": str(lead.get("notes", "")).strip(),
    }
    row = [row_data.get(h, "") for h in self._vento_lead_headers_current]
    self._vento_leads_ws.append_row(row, value_input_option="USER_ENTERED")
    return row_data
```

The existing `LeadService.export_leads()` method already accepts a `mode` parameter. When `mode="vento"`, it will route to `save_vento_lead()` instead of `save_lead()`, writing to the "Vento Influencers" tab with the influencer-specific schema.

---

### Component 5: Frontend Integration — `leadgen.html` Vento Mode

#### [MODIFY] `ui/leadgen.html`

Add a third mode button and Vento-specific UI controls. Changes are scoped to three areas:

**5a. Mode Toggle Bar** (line ~384):

Add a third "VENTO" button to the existing toggle strip:

```html
<!-- Existing toggle bar — add third button -->
<div class="flex p-1 bg-lv-950/50 rounded-xl border border-lv-500/10 mb-6">
  <button id="btn-mode-generic" class="flex-1 py-2 text-[10px] font-bold rounded-lg ...">GENERIC</button>
  <button id="btn-mode-velit" class="flex-1 py-2 text-[10px] font-bold rounded-lg ...">VELITCAMPING</button>
  <button id="btn-mode-vento" class="flex-1 py-2 text-[10px] font-bold rounded-lg transition-all text-lv-400 hover:text-lv-200">VENTO</button>
</div>
```

**5b. Vento-Specific Controls Panel** (shown only when mode === 'vento'):

Inserted below the mode toggle, hidden by default. Revealed when Vento mode is active:

```html
<!-- Vento-specific panel (hidden unless mode === 'vento') -->
<div id="vento-panel" class="hidden space-y-4">

  <!-- Influencer Type Selector -->
  <div>
    <label class="text-[11px] text-lv-300/70 mb-2 block font-medium uppercase tracking-wider">Influencer Type</label>
    <select id="vento-type-select" class="field">
      <option value="all">All Types</option>
      <option value="pet">🐕 Pet Lifestyle</option>
      <option value="gadget">📱 Gadget / Car Reviewers</option>
      <option value="lifestyle">🌲 Lifestyle / PNW Vloggers</option>
    </select>
  </div>

  <!-- Follower Tier Selector -->
  <div>
    <label class="text-[11px] text-lv-300/70 mb-2 block font-medium uppercase tracking-wider">Follower Tier</label>
    <select id="vento-tier-select" class="field">
      <option value="all">All Tiers</option>
      <option value="nano">Nano (5K–20K)</option>
      <option value="mid">Mid (20K–100K)</option>
      <option value="upper_mid">Upper Mid (100K–500K)</option>
    </select>
  </div>

  <!-- Bulk Data Upload/Paste Area -->
  <div>
    <label class="text-[11px] text-lv-300/70 mb-2 block font-medium uppercase tracking-wider">
      Bulk Lead Import (CSV / JSON)
    </label>
    <textarea id="vento-bulk-input" class="field" rows="5"
      placeholder="Paste CSV or JSON data here...&#10;Name,Email,Instagram,TikTok,Location&#10;Jane Smith,jane@x.com,@janedogmom,@janetiktok,Seattle"></textarea>
  </div>

  <!-- File Upload -->
  <div class="flex items-center gap-3">
    <label for="vento-file-input"
      class="px-4 py-2 rounded-xl border border-lv-500/20 text-[11px] font-medium hover:bg-lv-500/10 transition-all cursor-pointer flex items-center gap-1.5 text-lv-200">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1M12 4v12m0-12l-4 4m4-4l4 4"/>
      </svg>
      Upload CSV / XLSX
    </label>
    <input type="file" id="vento-file-input" accept=".csv,.xlsx,.xls" class="hidden" />
    <span id="vento-file-name" class="text-[10px] text-lv-500"></span>
  </div>

  <p class="text-[9px] text-lv-600 leading-relaxed">
    💡 Paste or upload bulk influencer data (from Apify, RapidAPI, etc.) for instant processing.
    If no bulk data is provided, the pipeline falls back to Tavily web discovery (limited by free-tier quotas).
  </p>
</div>
```

**5c. JavaScript Mode Switching** (in the `<script>` section):

Extend the existing `setMode()` function to handle the 'vento' case:

```javascript
// state.mode: 'generic' | 'velit' | 'vento'

const btnModeVento = document.getElementById('btn-mode-vento');
const ventoPanel = document.getElementById('vento-panel');
const ventoTypeSelect = document.getElementById('vento-type-select');
const ventoTierSelect = document.getElementById('vento-tier-select');
const ventoBulkInput = document.getElementById('vento-bulk-input');
const ventoFileInput = document.getElementById('vento-file-input');
const ventoFileName = document.getElementById('vento-file-name');

function setMode(mode) {
  state.mode = mode;
  const allBtns = [btnModeGeneric, btnModeVelit, btnModeVento];
  const activeClass = 'flex-1 py-2 text-[10px] font-bold rounded-lg transition-all bg-lv-600 text-white shadow-lg';
  const inactiveClass = 'flex-1 py-2 text-[10px] font-bold rounded-lg transition-all text-lv-400 hover:text-lv-200';
  allBtns.forEach(b => b.className = inactiveClass);

  if (mode === 'generic') {
    btnModeGeneric.className = activeClass;
    modeBadge.textContent = 'Generic';
    modeBadge.className = '... bg-lv-500/10 border border-lv-500/20 text-lv-400 ...';
    industryWrap.classList.remove('hidden');
    ventoPanel.classList.add('hidden');
    industryInput.value = '';
  } else if (mode === 'velit') {
    btnModeVelit.className = activeClass;
    modeBadge.textContent = 'VelitCamping';
    modeBadge.className = '... bg-orange-500/10 border border-orange-500/20 text-orange-400 ...';
    industryWrap.classList.add('hidden');
    ventoPanel.classList.add('hidden');
    industryInput.value = 'Van Upfitters / RV Builders';
  } else {
    btnModeVento.className = activeClass;
    modeBadge.textContent = 'Vento';
    modeBadge.className = '... bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 ...';
    industryWrap.classList.add('hidden');
    ventoPanel.classList.remove('hidden');     // Show Vento controls
    industryInput.value = 'Influencer / Creator';
  }
}

btnModeVento.addEventListener('click', () => setMode('vento'));
```

**5d. Updated `runLeadGen()` Function**:

When `state.mode === 'vento'`, call the Vento API endpoint instead of the generic agent:

```javascript
async function runLeadGen() {
  // ... existing validation ...

  if (state.mode === 'vento') {
    return runVentoSearch();
  }

  // ... rest of existing generic/velit logic unchanged ...
}

async function runVentoSearch() {
  const location = locationInput.value.trim();
  const bulkData = ventoBulkInput?.value?.trim() || '';
  const influencerType = ventoTypeSelect?.value || 'all';
  const followerTier = ventoTierSelect?.value || 'all';
  const targetCount = parseInt(leadCountInput.value) || 50;

  state.leads = [];
  renderTable();
  setBusy(true);
  startTimer();
  startProgress();

  addLog(bulkData
    ? `Processing <strong>${bulkData.split('\n').length - 1} bulk records</strong> for Vento pipeline...`
    : `Searching for <strong>${influencerType}</strong> influencers in <strong>${location || 'US'}</strong>...`
  );

  try {
    const res = await fetch('/api/vento/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        location,
        influencer_type: influencerType,
        follower_tier: followerTier,
        target_count: targetCount,
        bulk_data: bulkData || undefined,
      }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

    const leads = data.leads || [];
    state.leads = leads.map(normalizeVentoLead);
    renderTable();

    // Log metadata
    const meta = data.metadata || {};
    addLog(`✅ Found <strong>${leads.length}</strong> influencer leads.`, 'success');
    addLog(`📊 With email: ${meta.leads_with_email || 0} | Instagram: ${meta.leads_with_instagram || 0} | TikTok: ${meta.leads_with_tiktok || 0} | Phone: ${meta.leads_with_phone || 0}`, 'info');
    addLog(`🔍 Discovery source: ${meta.discovery_source || 'unknown'}`, 'info');

    // Log pipeline steps
    (data.steps || []).forEach(step => {
      addLog(`⚙️ Phase: ${step.phase} → ${step.count || 0} records (${step.status})`, 'info');
    });

    // Auto-save to Google Sheets
    await autoSaveToSheets(state.leads);

  } catch (err) {
    addLog(`❌ Error: ${err.message}`, 'error');
  } finally {
    setBusy(false);
    stopTimer();
    finishProgress();
  }
}

function normalizeVentoLead(lead) {
  // Map Vento lead fields to the existing table renderer's expected format
  return {
    company_name: lead.creator_name || lead.instagram_handle || '—',
    company_website: lead.website || lead.instagram_url || '',
    founder_name: lead.creator_name || '',
    contact_email: lead.email || '',
    contact_phone: lead.phone || '',
    linkedin_url: '',
    instagram_url: lead.instagram_url || '',
    tiktok_url: lead.tiktok_url || '',
    location: lead.location || '',
    industry: lead.niche || 'Influencer',
    value_proposition: lead.value_proposition || '',
    lead_summary: `${lead.creator_name || 'Creator'} (${lead.instagram_handle || ''}${lead.tiktok_handle ? ' / ' + lead.tiktok_handle : ''}) — ${lead.niche || 'Influencer'}. Score: ${lead.relevance_score || '—'}/10.`,
    quality_score: lead.quality_score || 0,
    verification_status: lead.email ? 'pending' : '',
    // Preserve Vento-specific fields for export
    ...lead,
  };
}
```

**5e. Updated Table Columns** (only when mode === 'vento'):

The table header/body rendering can conditionally show Instagram/TikTok columns instead of the default Company/Person columns. This is done by swapping the `renderTable()` thead content when `state.mode === 'vento'`.

---

### Component 6: Updated `autoSaveToSheets` for Vento Mode

When `state.mode === 'vento'`, the existing `autoSaveToSheets()` already passes `mode: state.mode` to `/api/leads/export`. The `LeadService.export_leads()` method will detect `mode="vento"` and route leads to `todo_store.save_vento_lead()` instead of `todo_store.save_lead()`, writing to the **"Vento Influencers"** tab.

#### [MODIFY] `core/services/lead_service.py`

Add mode-aware routing in `export_leads()`:

```python
async def export_leads(self, leads, mode="generic"):
    await self._call_store(self.todo_store.ensure_store)

    # ... existing dedup logic ...

    for lead in ranked_leads:
        # ... existing dedup checks ...
        if mode == "vento":
            await self._call_store(self.todo_store.save_vento_lead, lead)
        else:
            await self._call_store(self.todo_store.save_lead, lead)
        # ... rest unchanged ...
```

---

## Files Changed Summary

| Action | File | Description |
|--------|------|-------------|
| **NEW** | `core/services/vento/__init__.py` | Empty module init |
| **NEW** | `core/services/vento/discovery.py` | Tavily fallback queries, social handle extraction, keyword matching |
| **NEW** | `core/services/vento/vento_lead_pipeline.py` | Hybrid pipeline: bulk ingest + API + Tavily fallback + unified scoring |
| **NEW** | `api/routes/vento_leads.py` | FastAPI routes: `/api/vento/search`, `/api/vento/ingest`, `/api/vento/export` |
| **MODIFY** | `api/main.py` | Append route registration (additive, feature-flag gated) |
| **MODIFY** | `ui/leadgen.html` | Add "VENTO" mode button, bulk upload panel, Vento search flow |
| **MODIFY** | `core/services/todo_sheet_store.py` | Add "Vento Influencers" worksheet + `VENTO_LEAD_HEADERS` + `save_vento_lead()` |
| **MODIFY** | `core/services/lead_service.py` | Mode-aware routing: `mode="vento"` → `save_vento_lead()` |

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Bulk CSV has wrong columns | `_map_flexible_columns()` handles flexible naming; unmapped columns ignored |
| Bulk CSV is empty | Falls through to Tavily fallback automatically |
| `SOCIAL_DATA_API_KEY` not set | Skipped silently, falls to Tavily or requires bulk upload |
| Social data API returns error/timeout | Logged warning, falls to Tavily fallback |
| Tavily rate limit hit | Retry with backoff (3 retries). Return partial results |
| Gemini quota exhausted mid-run | Switches to `_heuristic_score_influencer()` for remaining leads |
| No influencers found at all | Return empty leads + metadata with `discovery_source: "none"` |
| Duplicate creator across bulk + Tavily | Dedup by Instagram handle (primary key) → email → domain |
| Non-US creator in results | Still included but scored lower (not rejected) |
| Uploaded XLSX file is corrupted | Return HTTP 400 with error detail |
| Google Sheets "Vento Influencers" tab missing | Auto-created by `_ensure_worksheet()` on first export |

---

## Safety — Additive Only Checklist

- [x] No existing pipeline classes modified (`ProductionLeadPipeline`, `VelitLeadPipeline`)
- [x] No existing route handlers changed
- [x] No existing UI modes broken (Generic + VelitCamping work exactly as before)
- [x] New routes use isolated prefix (`/api/vento/`)
- [x] Feature-flag gated (`ENABLE_VENTO_PIPELINE`)
- [x] Existing Google Sheets "leads" tab untouched — Vento writes to separate "Vento Influencers" tab
- [x] Modifications to existing files are purely additive (append new methods, add new mode case)
- [x] Removal: set flag to false, delete new files, revert 4 additive changes
- [x] Reuses existing infrastructure: `TavilyClient`, `Gemini`, `ProductionLeadPipeline` base, `TodoSheetStore`

---

# Additive Extension — Daily 50 Verified, Tagged, Usable Influencer Leads

> **Additive requirement:** This section extends the existing Vento plan without replacing or removing any previous requirement. The original hybrid discovery, enrichment, UI, API, and Google Sheets design remains unchanged.

## Extension Goal

Add a repeatable daily workflow that discovers a larger raw pool and returns up to **50 new, genuine, usable influencer leads per day** for the Vento campaign.

Each accepted lead must include:

- A creator/account name
- At least one verified, active social profile: Instagram, TikTok, or YouTube
- A relevant Vento campaign niche
- A location tag with a confidence level and supporting evidence
- At least one usable outreach channel: verified email or active social DM profile
- Source URL and verification timestamp
- A stable creator identity used for cross-day deduplication

Preferred but not mandatory fields:

- Both Instagram and TikTok
- Public business phone number
- Verified follower count
- Website, Linktree, media kit, or management contact
- Engagement and recent-posting signals

The daily target means **50 accepted A/B leads**, not 50 records containing every optional field. Phone numbers must remain optional because most creators do not publish a business phone number.

## Definitions

### Raw Lead

A creator/profile discovered through bulk import, a configured social-data provider, Tavily, or a previously unprocessed source. It has not yet passed normalization, verification, deduplication, or campaign qualification.

### Genuine Lead

A lead whose social profile resolves successfully, represents a creator rather than a directory/search page, and has enough profile or source evidence to establish identity and campaign relevance.

### Contactable Lead

A genuine lead with at least one of:

- A syntactically valid and deliverable public business email
- An active Instagram/TikTok/YouTube profile that supports brand outreach by DM
- A public management, collaboration, or media-kit contact path

### Usable Lead

A genuine, contactable, relevant lead that passes the Vento quality gate, is not already stored from a previous run, and has sufficient location evidence for tagging.

### Fully Verified Lead

A usable lead with a verified profile, verified email, confirmed or likely target location, reliable follower data, and clear niche evidence. Fully verified leads receive the highest outreach priority but are not required for every daily slot.

## Daily Funnel and Quota

The system must over-discover because some raw results will be duplicates, inactive, irrelevant, outside the target geography, or missing usable contact paths.

```text
Discover/import 100–150 raw candidates
                 ↓
Normalize creator identities and social URLs
                 ↓
Remove same-run and historical duplicates
                 ↓
Verify profiles, location, niche, and activity
                 ↓
Find and validate public business contacts
                 ↓
Score and assign A/B/C quality level
                 ↓
Export up to 50 new A/B usable leads
                 ↓
Place uncertain C leads in the review queue
```

Daily configuration defaults:

```python
VENTO_DAILY_USABLE_TARGET = 50
VENTO_DAILY_RAW_TARGET = 150
VENTO_DAILY_MIN_RAW_TARGET = 100
VENTO_DAILY_MAX_RAW_TARGET = 250
VENTO_DAILY_MIN_EMAIL_READY = 25
VENTO_DAILY_MAX_REVIEW_LEADS = 50
```

`VENTO_DAILY_MIN_EMAIL_READY` is a target for reporting, not a reason to fabricate or accept an invalid email. If fewer email-ready creators are found, the run returns the genuine A/B leads available and clearly reports the shortfall.

## Verification Model

Verification must be stored per field. A single `verified: true` flag is not sufficient.

### Profile Verification

Allowed values:

- `verified_active` — profile resolves and has evidence of recent creator activity
- `verified_inactive` — profile resolves but appears inactive
- `not_found` — URL/handle does not resolve
- `private` — profile exists but cannot be sufficiently reviewed
- `rate_limited` — verification could not finish because the source blocked or limited the request
- `unknown` — no verification attempt or insufficient evidence

Profile verification evidence must include the checked URL and `profile_checked_at` timestamp.

### Email Verification

Reuse the existing email-verification infrastructure where possible. Allowed values:

- `valid`
- `risky`
- `invalid`
- `unknown`
- `not_available`

Only `valid` email addresses count as email-ready. `risky` addresses remain reviewable and must not be presented as verified.

### Location Verification

Allowed values:

- `confirmed` — explicit city/state/country from a reliable creator-owned or provider source
- `likely` — multiple consistent indirect signals
- `uncertain` — one weak signal, requested search location only, or ambiguous text
- `outside_target` — reliable evidence places the creator outside the configured target
- `unknown` — no location evidence

The system must never assign the requested search location as the creator's actual location without evidence. Store:

- `location_city`
- `location_state`
- `location_country`
- `location_region`
- `location_confidence`
- `location_evidence`
- `location_source_url`

### Niche Verification

Allowed values:

- `relevant`
- `possibly_relevant`
- `irrelevant`
- `unknown`

Niche classification must preserve evidence keywords/content and may assign multiple tags:

- `Pet Creator`
- `Dog Parent`
- `Dog Trainer`
- `Pet Safety`
- `UGC Creator`
- `Product Reviewer`
- `Car Gadgets`
- `Amazon Finds`
- `Outdoor Lifestyle`
- `Road Trip / Camping`
- `PNW Lifestyle`
- `Local Lifestyle`

### Follower Verification

Allowed values:

- `verified`
- `provider_reported`
- `imported_unverified`
- `estimated`
- `unknown`

Follower tiers must only be enforced when a numeric follower count exists with `verified`, `provider_reported`, or an explicitly accepted `imported_unverified` status. Do not use an LLM to invent a follower tier when no follower evidence exists.

## Lead Quality Levels

### Level A — Outreach Ready

Required:

- Verified active creator profile
- Strong or acceptable Vento niche match
- `confirmed` or `likely` target location
- Verified public business email or verified management contact
- No duplicate identity
- No critical brand-safety rejection

### Level B — DM Ready

Required:

- Verified active creator profile
- Strong or acceptable Vento niche match
- `confirmed`, `likely`, or review-approved `uncertain` location
- Active social DM channel
- No verified email required
- No duplicate identity
- No critical brand-safety rejection

### Level C — Needs Review

Examples:

- Location is unknown or uncertain
- Profile is private
- Email is risky
- Creator identity is ambiguous
- Niche is only possibly relevant
- Follower data conflicts across sources

Level C records do not count toward the daily 50 until manually approved.

### Rejected

Reject records when:

- All profile URLs are missing or not found
- The record is a directory/article rather than a creator
- The creator is clearly irrelevant to the campaign
- The only email is invalid
- The creator is a historical or same-run duplicate with no new information
- Location is reliably outside a strict target run
- The content triggers configured critical brand-safety rules

## Location and Campaign Tags

Every accepted lead must have normalized, filterable tags. Tags must be stored as a list internally and exported to Sheets as a comma-separated string.

Tag groups:

```json
{
  "geography": ["US", "Washington", "Seattle", "PNW"],
  "niche": ["Pet Creator", "Dog Parent", "Outdoor Lifestyle"],
  "platform": ["Instagram", "TikTok"],
  "follower_tier": ["Mid-Tier"],
  "contactability": ["Email Verified", "DM Ready"],
  "verification": ["Profile Verified", "Location Confirmed"],
  "priority": ["High Priority"]
}
```

PNW normalization rules:

- Seattle, Bellevue, Tacoma, Redmond, Kirkland, Everett → `Washington`, `PNW`
- Portland, Beaverton, Hillsboro, Gresham, Lake Oswego → `Oregon`, `PNW`
- Eugene and Bend → `Oregon`, `PNW`
- Other US cities → `US` plus normalized state/region tags
- Canadian creators → `Canada`; include only when the run allows North America rather than strict US targeting

## Expanded Lead Schema

Append these fields to the original Vento lead object:

```python
{
    # Stable identity and provenance
    "creator_id": str,
    "import_batch_id": str,
    "source_record_id": str,
    "source_url": str,
    "source_observed_at": str,
    "discovered_at": str,
    "last_verified_at": str,

    # Identity and platforms
    "creator_name": str,
    "instagram_handle": str,
    "instagram_url": str,
    "instagram_profile_status": str,
    "tiktok_handle": str,
    "tiktok_url": str,
    "tiktok_profile_status": str,
    "youtube_channel": str,
    "youtube_url": str,
    "youtube_profile_status": str,

    # Contactability
    "email": str,
    "email_verification_status": str,
    "email_verification_reason": str,
    "phone": str,
    "phone_type": str,                 # public_business / management / unknown
    "contact_page_url": str,
    "media_kit_url": str,
    "management_contact": str,
    "preferred_contact_method": str,  # email / instagram_dm / tiktok_dm / management

    # Geography
    "location": str,
    "location_city": str,
    "location_state": str,
    "location_country": str,
    "location_region": str,
    "location_confidence": str,
    "location_evidence": str,
    "location_source_url": str,

    # Fit and audience
    "niche": str,
    "niche_tags": list[str],
    "niche_verification_status": str,
    "follower_count": int | None,
    "follower_count_status": str,
    "estimated_follower_tier": str,
    "engagement_rate": float | None,
    "average_views": int | None,
    "last_post_date": str,
    "recently_active": bool | None,

    # Qualification
    "profile_verified": bool,
    "quality_level": str,              # A / B / C / Rejected
    "relevance_score": float,
    "contactability_score": float,
    "verification_score": float,
    "overall_score": float,
    "score_breakdown": dict,
    "scoring_version": str,
    "value_proposition": str,
    "tags": list[str],
    "rejection_reasons": list[str],

    # Campaign operations
    "outreach_status": str,
    "owner": str,
    "last_contacted_at": str,
    "follow_up_at": str,
    "do_not_contact": bool,
    "notes": str,
}
```

## Stable Identity and Cross-Day Deduplication

Deduplication must run before verification credits are spent and again before export.

Identity priority:

1. Normalized Instagram handle
2. Normalized TikTok handle
3. Normalized YouTube channel ID/handle
4. Verified email
5. Creator-owned website plus normalized creator name
6. Provider-specific creator ID

Create a stable `creator_id` from the strongest available identity. Example:

```python
creator_id = sha256(f"instagram:{normalized_instagram_handle}").hexdigest()
```

Deduplication requirements:

- Deduplicate within the current raw batch
- Compare against all previously exported Vento creators
- Merge newly discovered platform/contact fields into the existing creator when confidence is high
- Do not deduplicate solely on shared platform domains such as `instagram.com` or `tiktok.com`
- Do not deduplicate solely on link-in-bio domains such as `linktr.ee`
- Do not merge two creators solely because they share a management email/domain
- Record `duplicate_of_creator_id` and merge evidence for auditability

## New Verification Module

### [NEW] `core/services/vento/verification.py`

Responsibilities:

```python
async def verify_creator_profile(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve available profile URLs and classify activity/status."""

async def verify_creator_email(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Use the existing email verifier and return explicit status/evidence."""

def verify_creator_location(lead: Dict[str, Any], *, target: str) -> Dict[str, Any]:
    """Normalize location and grade evidence without copying the search location."""

def verify_creator_niche(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Assign evidence-backed Vento niche tags and relevance status."""

def verify_follower_tier(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Parse numeric counts safely and preserve the count's source/status."""
```

Follower parsing must correctly support:

- `5,000` → `5000`
- `12.5K` → `12500`
- `100K` → `100000`
- `1.2M` → `1200000`

## New Tagging and Qualification Module

### [NEW] `core/services/vento/qualification.py`

Responsibilities:

```python
def build_vento_tags(lead: Dict[str, Any]) -> List[str]:
    """Build normalized geography, niche, platform, tier, and priority tags."""

def calculate_vento_scores(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Return transparent relevance, contactability, and verification scores."""

def classify_quality_level(lead: Dict[str, Any]) -> str:
    """Return A, B, C, or Rejected from deterministic acceptance rules."""
```

Recommended scoring weights:

| Component | Weight |
|---|---:|
| Vento niche/campaign fit | 30 |
| Contactability | 25 |
| Profile/activity verification | 15 |
| Location fit and confidence | 15 |
| Audience/follower fit | 10 |
| Content quality/brand safety | 5 |

Gemini may assist with niche/content interpretation and value-proposition writing. Deterministic code must decide whether required evidence exists. Gemini must not invent follower counts, locations, contact details, or verification statuses.

## Daily Batch Orchestration

### [NEW] `core/services/vento/daily_batch.py`

```python
class VentoDailyBatchRunner:
    async def run(
        self,
        *,
        location: str,
        daily_target: int = 50,
        raw_target: int = 150,
        influencer_type: str = "all",
        follower_tier: str = "all",
        strict_us_only: bool = True,
        bulk_data: Optional[str] = None,
        bulk_file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Produce new A/B Vento leads while preserving C leads for review."""
```

Execution order:

1. Generate `batch_id` and load historical Vento identity keys.
2. Ingest bulk/provider records first.
3. Use Tavily only for the remaining raw-candidate shortfall.
4. Normalize creator/platform identities.
5. Remove same-run and historical duplicates.
6. Verify profiles and recent activity.
7. Enrich public contact paths within configured request limits.
8. Verify emails.
9. Normalize and verify location evidence.
10. Verify niche and follower evidence.
11. Apply deterministic scores and quality levels.
12. Sort A leads first, followed by B leads.
13. Select up to `daily_target` new usable leads.
14. Save C leads to the review queue.
15. Export accepted leads and write a daily run report.

The job must return partial results when the target cannot be reached. It must not lower verification standards merely to fill the quota.

## Geographic Rotation

Allow a user to select one location per run or use a configured rotation.

Suggested default rotation:

| Day | Priority geography |
|---|---|
| Monday | Seattle and nearby Washington cities |
| Tuesday | Portland and nearby Oregon cities |
| Wednesday | Wider PNW |
| Thursday | California and Southwest US |
| Friday | Mountain, Midwest, South, and East Coast US |

The rotation is configurable. Historical deduplication ensures the same creator is not returned on multiple days.

## API Additions

Extend `api/routes/vento_leads.py` additively.

### `POST /api/vento/daily-run`

Request:

```json
{
  "location": "Seattle, WA",
  "daily_target": 50,
  "raw_target": 150,
  "influencer_type": "all",
  "follower_tier": "all",
  "strict_us_only": true,
  "bulk_data": null
}
```

Response:

```json
{
  "batch_id": "vento-2026-07-10-001",
  "status": "completed_with_shortfall",
  "accepted_leads": [],
  "review_leads": [],
  "rejected_count": 31,
  "duplicate_count": 24,
  "daily_target": 50,
  "accepted_count": 43,
  "shortfall": 7,
  "metrics": {
    "raw_discovered": 132,
    "profile_verified": 91,
    "email_ready": 28,
    "dm_ready": 15,
    "level_a": 28,
    "level_b": 15,
    "level_c": 17
  }
}
```

### `POST /api/vento/review/{creator_id}`

Allow a reviewer to approve, reject, or correct a Level C record without editing raw evidence.

### `GET /api/vento/daily-runs`

Return recent batch summaries and quota performance.

### `GET /api/vento/daily-runs/{batch_id}`

Return a batch report, accepted leads, review leads, failures, and source usage.

## Frontend Additions

Extend the existing Vento panel in `ui/leadgen.html` with:

- `Daily target` input, default 50
- `Raw discovery target` input, default 150
- `Strict US only` toggle
- Location/region selector
- `Run Daily Vento Search` button
- Verification filter: All / A / B / Needs Review
- Contact filter: Email Ready / DM Ready / Any
- Tag filters for location, niche, follower tier, and platform
- Batch summary cards
- Review queue panel

Daily summary cards:

- Raw candidates
- New unique creators
- Profile verified
- Email ready
- DM ready
- A leads
- B leads
- Needs review
- Rejected
- Duplicates skipped
- Daily target progress

The table must display a reason/evidence tooltip for every verification status. Do not display a generic green “Verified” badge when only one field has been checked.

## Google Sheets Additions

Keep the original `Vento Influencers` worksheet and append the most important verification fields:

```python
VENTO_VERIFICATION_HEADERS = [
    "Creator ID",
    "Batch ID",
    "Creator Name",
    "Email",
    "Email Verification",
    "Instagram Handle",
    "Instagram URL",
    "Instagram Status",
    "TikTok Handle",
    "TikTok URL",
    "TikTok Status",
    "YouTube URL",
    "Location",
    "Location Confidence",
    "Location Evidence",
    "Niche Tags",
    "Follower Count",
    "Follower Count Status",
    "Follower Tier",
    "Quality Level",
    "Relevance Score",
    "Contactability Score",
    "Verification Score",
    "Overall Score",
    "Preferred Contact Method",
    "Tags",
    "Source",
    "Source URL",
    "Discovered At",
    "Last Verified At",
    "Outreach Status",
    "Owner",
    "Notes",
]
```

Add two additional worksheets:

### `Vento Review Queue`

Stores Level C leads, verification conflicts, manual decisions, reviewer, and review timestamp.

### `Vento Daily Runs`

Stores:

- Batch ID
- Run date
- Target location
- Raw target
- Daily usable target
- Raw discovered
- Duplicates
- A/B/C/rejected counts
- Email-ready count
- DM-ready count
- Shortfall
- Provider/API usage
- Duration
- Final status
- Error summary

Use batch writes rather than one Google Sheets API call per lead wherever supported.

## Search and Enrichment Source Rules

Source priority:

1. User-provided CSV/XLSX/JSON
2. Configured provider adapter with known schema
3. Creator-owned websites/media kits
4. Tavily web discovery fallback
5. Manual review/correction

Every material field must retain its source. A general `source` field alone is insufficient when the email, location, follower count, and handle came from different sources.

Do not claim that a generic `SOCIAL_DATA_API_URL` works automatically with every Apify or RapidAPI product. Implement provider adapters for each configured provider's authentication, request schema, pagination, and response mapping.

## Public Contact and Privacy Rules

- Collect only publicly available creator/business contact information.
- Do not attempt to obtain private personal phone numbers.
- Mark phone numbers as `public_business`, `management`, or `unknown`.
- Preserve the source URL for contact information.
- Support `do_not_contact` and suppression lists.
- Never re-add a suppressed creator during later daily runs.
- Do not treat an email guessed solely from a naming pattern as verified.
- Respect configured source limits and access rules.

## Failure and Edge-Case Handling

| Scenario | Required behavior |
|---|---|
| Fewer than 50 usable leads found | Return genuine partial results and report exact shortfall |
| Same creator found on two platforms | Merge only when identity evidence is strong; preserve both profiles |
| Shared management email | Keep separate creator records; link the same management contact |
| Creator changes handle | Retain alias history and update the canonical identity after verification |
| Profile is private | Mark `private`; allow Level C unless other strong evidence supports B |
| Profile is inactive | Reject or review based on configurable recent-activity threshold |
| Location appears only in search query | Mark `uncertain`; do not treat as confirmed evidence |
| Email is risky | Keep in review; do not count as email-ready |
| Email is invalid | Remove the email, preserve the invalid status, and use DM if otherwise eligible |
| No email but active relevant profile | Allow Level B / DM Ready |
| Both Instagram and TikTok are absent | Require another verified creator platform and contact path or reject |
| Missing follower count | Keep follower tier `unknown`; do not invent it |
| Decimal follower count such as 12.5K | Parse as 12,500 |
| XLSX is corrupted | Return HTTP 400 with a clear parsing error; do not silently run web discovery |
| Provider is rate limited | Retry with bounded backoff, record failure, then use allowed fallback |
| Verification is blocked | Mark `rate_limited` or `unknown`; never mark verified |
| Google Sheets export fails | Keep the batch result available for retry without rerunning discovery |
| Daily run is retried | Use `batch_id`/idempotency key to prevent duplicate export |
| Application restarts | Resume or safely retry an unfinished persisted batch |

## Observability and Daily Reporting

Record for every batch:

- Total raw candidates per source
- Provider/Tavily request counts
- Same-run duplicates
- Historical duplicates
- Verification success/failure counts
- Valid/risky/invalid email counts
- Confirmed/likely/uncertain/unknown location counts
- A/B/C/rejected counts
- Rejection reasons
- Cost/API quota estimates
- Duration per phase
- Export status
- Daily shortfall

Never log API keys, full authentication headers, or unnecessary personal data.

## Tests

### Unit Tests

Add:

- `tests/test_vento_discovery.py`
- `tests/test_vento_ingestion.py`
- `tests/test_vento_verification.py`
- `tests/test_vento_qualification.py`
- `tests/test_vento_daily_batch.py`
- `tests/test_vento_export.py`

Required cases:

- CSV, JSON, XLSX, alternate headers, quoted commas, Unicode names
- Instagram/TikTok URL and handle normalization
- Direct social-result URL extraction
- `12.5K`, `100K`, and `1.2M` follower parsing
- Same-platform and cross-platform deduplication
- Shared management email must not merge creators
- Historical cross-day deduplication
- Location evidence and confidence rules
- Search location must not become creator location automatically
- A/B/C/Rejected classification
- Email valid/risky/invalid handling
- Strict US versus North America behavior
- Partial daily result and shortfall reporting
- Idempotent batch retry
- Separate Vento worksheet export

### Integration Tests

- Mock provider success, timeout, pagination, and rate limiting
- Mock Tavily results containing direct Instagram/TikTok URLs
- Mock profile verifier responses
- Mock email-verification responses
- Mock Gemini quota exhaustion
- Mock Google Sheets batch save and retry
- Verify Vento routes are feature-flagged and isolated

## Acceptance Criteria

The daily extension is complete only when:

- A user can request 50 daily leads from the Vento UI/API.
- The pipeline over-discovers, deduplicates, verifies, scores, and exports in one tracked batch.
- Every accepted lead has a creator identity, active profile, relevant niche, location tag/confidence, outreach path, source URL, and verification timestamp.
- A and B leads count toward the daily target; C leads go to review.
- Phone numbers and both social platforms remain optional.
- No follower tier or location is invented when evidence is absent.
- Duplicate creators are not re-exported on later days.
- Vento leads do not pass through the generic B2B quality gate.
- Vento exports use the dedicated `Vento Influencers` worksheet.
- Failed exports can be retried without re-running discovery.
- The response and daily report show honest shortfalls rather than lowering quality standards.
- Automated tests cover ingestion, verification, tagging, qualification, deduplication, daily batching, and export.

## Additive Files Changed Summary

| Action | File | Description |
|---|---|---|
| **NEW** | `core/services/vento/verification.py` | Profile, email, location, niche, activity, and follower verification |
| **NEW** | `core/services/vento/qualification.py` | Evidence-based tags, component scoring, and A/B/C classification |
| **NEW** | `core/services/vento/daily_batch.py` | Daily raw-to-50 usable lead orchestration and batch reporting |
| **MODIFY** | `core/services/vento/vento_lead_pipeline.py` | Connect verification, qualification, historical dedup, and daily batch metadata |
| **MODIFY** | `core/services/vento/discovery.py` | Extract handles from result URLs and preserve location/source evidence |
| **MODIFY** | `api/routes/vento_leads.py` | Add daily run, review, and batch report endpoints |
| **MODIFY** | `core/services/todo_sheet_store.py` | Add verification columns, review queue, and daily runs worksheet |
| **MODIFY** | `core/services/lead_service.py` | Use Vento-specific gate, historical identity lookup, and batch export |
| **MODIFY** | `ui/leadgen.html` | Daily target controls, verification badges, filters, reports, and review queue |
| **NEW** | `tests/test_vento_*.py` | Vento ingestion, verification, qualification, daily batch, and export coverage |

## Suggested Implementation Order

1. Fix and test ingestion, including genuine XLSX parsing.
2. Add stable creator identity and same-run/historical deduplication.
3. Add evidence-backed profile, email, location, niche, and follower verification.
4. Add deterministic tagging, scoring, and A/B/C qualification.
5. Implement Vento-specific Sheets storage and batch export.
6. Implement the daily batch runner and honest shortfall reporting.
7. Add daily-run, review, and reporting APIs.
8. Add Vento daily controls and review queue to the existing lead dashboard.
9. Add provider adapters and bounded fallback behavior.
10. Complete automated tests and an end-to-end 50-lead acceptance run.
