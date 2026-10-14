# LinkedIn Profile Finder — Implementation Plan (1 of 4)

## Goal

Upload an Excel file with **person names + company names**, the system web-searches Google/Tavily to find each person's **LinkedIn profile URL**, verifies the URL actually matches the person (name check + company check), and returns the results as a downloadable enriched Excel.

## Scope (Additive Only)

- **Add** a new service: `core/services/linkedin_tools/profile_finder.py`
- **Add** a new API route: `api/routes/linkedin_tools.py` → `POST /api/linkedin-tools/find-profiles`
- **Add** a new UI page: `ui/linkedin_profile_finder.html` → served at `/linkedin-profile-finder`
- **Add** route registration in `api/main.py` (feature-flag gated: `ENABLE_LINKEDIN_TOOLS`)
- **No changes** to any existing files except `api/main.py` (additive only — append new route block)
- **No deletion** of existing code, data, or pipelines

## Non-Goals

- No modification to existing `LinkedInResearchTool`, `LinkedInCampaignService`, or `ProductionLeadPipeline`.
- No modification to existing UI pages.
- No changes to existing Hunter or lead verification flows.

## Architecture

```
Excel Upload (Person Name | Company Name)
    │
    ▼
POST /api/linkedin-tools/find-profiles
    │
    ▼
ProfileFinderService.find_profiles(rows)
    │
    ├── For each row:
    │   ├── Step 1: Tavily web search: "{person_name}" "{company_name}" site:linkedin.com/in
    │   ├── Step 2: Parse search results for linkedin.com/in/ URLs
    │   ├── Step 3: Verify: does the URL slug contain parts of the person's name?
    │   ├── Step 4: Verify: does the search snippet mention the company?
    │   ├── Step 5: Score confidence (high/medium/low)
    │   └── Return: linkedin_url, confidence, verification_notes
    │
    ▼
Return enriched JSON → Frontend renders table + Download XLSX button
```

## Backend Plan

### [NEW] `core/services/linkedin_tools/__init__.py`
Empty init file for the new module.

### [NEW] `core/services/linkedin_tools/profile_finder.py`

```python
class ProfileFinderService:
    async def find_profiles(self, rows: List[Dict]) -> Dict[str, Any]:
        """
        For each row with person_name + company_name:
        1. Build search query: '"{person_name}" "{company_name}" site:linkedin.com/in'
        2. Call TavilyClient.search() (reuse existing)
        3. Extract linkedin.com/in/ URLs from results
        4. Verify each URL:
           - URL slug contains person's first + last name tokens
           - Search snippet or title mentions the company name
        5. Score confidence:
           - HIGH: name tokens match + company matches in snippet
           - MEDIUM: name tokens partially match or company found
           - LOW: URL found but weak match
        6. Return best match for each row
        """
```

**Verification logic (critical):**
```python
def _verify_linkedin_url(self, url, person_name, company_name):
    # Extract slug from URL: linkedin.com/in/john-doe → "john-doe"
    slug = extract_slug(url)
    name_tokens = person_name.lower().split()  # ["john", "doe"]
    
    # Check 1: Do name tokens appear in the slug?
    slug_clean = slug.replace("-", " ").replace("_", " ")
    name_match = all(token in slug_clean for token in name_tokens[:2])
    
    # Check 2: Does the search snippet/title mention the company?
    company_match = company_name.lower() in snippet.lower()
    
    # Check 3: Is it a /in/ URL (person profile, not /company/)?
    is_person_url = "/in/" in url
    
    return {
        "verified": name_match and is_person_url,
        "confidence": "high" if (name_match and company_match) else 
                      "medium" if name_match else "low",
        "notes": f"Name match: {name_match}, Company match: {company_match}"
    }
```

**Concurrency:** Process rows in batches of 5 with `asyncio.gather()` to avoid overwhelming Tavily.

### [NEW] `api/routes/linkedin_tools.py`

```python
router = APIRouter()

class FindProfilesRequest(BaseModel):
    rows: List[Dict[str, str]]  # Each row: {"person_name": "...", "company_name": "..."}

@router.post("/find-profiles")
async def find_profiles(request: FindProfilesRequest) -> Dict[str, Any]:
    service = ProfileFinderService()
    return await service.find_profiles(request.rows)
```

### [MODIFY] `api/main.py` — ADDITIVE ONLY

Append at the bottom (after existing route registrations):

```python
if _include_optional_route("ENABLE_LINKEDIN_TOOLS", True):
    try:
        from api.routes import linkedin_tools as linkedin_tools_route
        app.include_router(linkedin_tools_route.router, prefix="/api/linkedin-tools", tags=["LinkedIn Tools"])
    except Exception as exc:
        print(f"LinkedIn tools disabled: {exc}")

    @app.get("/linkedin-profile-finder", include_in_schema=False)
    async def linkedin_profile_finder_page():
        return FileResponse("ui/linkedin_profile_finder.html")
```

## Frontend Plan

### [NEW] `ui/linkedin_profile_finder.html`

**Layout:**
- Same design system as existing pages (dark theme, glassmorphism, Outfit font)
- **Upload section**: XLSX file upload button + drag-and-drop
- **Column mapping**: Auto-detect "Person Name" and "Company Name" columns, allow user to remap
- **Results table**: Person Name | Company Name | LinkedIn URL (clickable) | Confidence | Notes
- **Download button**: Export enriched results as XLSX with LinkedIn URLs added
- **Progress**: Show processing progress (row X of Y)

**Excel parsing**: Use `xlsx.js` (already included in the project via CDN) to parse uploaded files.

**API call flow:**
1. Parse XLSX → extract rows with person_name + company_name
2. POST to `/api/linkedin-tools/find-profiles` with rows
3. Render results in table
4. "Download XLSX" button creates enriched file with LinkedIn URL column

## API Contract

**POST /api/linkedin-tools/find-profiles**

Request:
```json
{
  "rows": [
    {"person_name": "John Doe", "company_name": "Acme Corp"},
    {"person_name": "Jane Smith", "company_name": "Beta Inc"}
  ]
}
```

Response:
```json
{
  "success": true,
  "results": [
    {
      "person_name": "John Doe",
      "company_name": "Acme Corp",
      "linkedin_url": "https://www.linkedin.com/in/john-doe",
      "confidence": "high",
      "verification_notes": "Name match: true, Company match: true",
      "search_source": "tavily"
    }
  ],
  "summary": {"total": 2, "found": 2, "high_confidence": 1, "medium_confidence": 1, "not_found": 0}
}
```

## Error Handling

- Missing person_name → skip row, return `"not_found"` with reason
- Tavily search fails → return row with `"error"` status, continue with next
- No LinkedIn URL found → return `"not_found"`, suggest manual search
- Rate limiting → process in batches with delays between batches

## Files Changed Summary

| Action | File |
|--------|------|
| **NEW** | `core/services/linkedin_tools/__init__.py` |
| **NEW** | `core/services/linkedin_tools/profile_finder.py` |
| **NEW** | `api/routes/linkedin_tools.py` |
| **NEW** | `ui/linkedin_profile_finder.html` |
| **MODIFY** | `api/main.py` (append route registration only) |

## Safety — Additive Only Checklist

- [x] No existing files deleted
- [x] No existing service classes modified
- [x] No existing route handlers changed
- [x] No existing UI pages touched
- [x] New routes use isolated prefix (`/api/linkedin-tools/`)
- [x] Feature-flag gated (`ENABLE_LINKEDIN_TOOLS`)
- [x] Removal: set flag to false, delete new files only
