# LinkedIn Connection Status Checker — Implementation Plan (3 of 4)

## Goal

Check if previously sent LinkedIn connection requests have been **accepted** or are still pending, so the user knows who they can now send Direct Messages to.

## Scope (Additive Only)

- **Add** a new service: `core/services/linkedin_tools/status_checker.py`
- **Add** a new API route in `api/routes/linkedin_tools.py` → `POST /api/linkedin-tools/check-status`
- **Add** a new UI page: `ui/linkedin_status_checker.html`
- **No changes** to existing pipelines.

## Architecture

LinkedIn's Voyager API allows checking connection status between the authenticated user and a target profile.

```
Upload Excel (LinkedIn URLs)
    │
    ▼
POST /api/linkedin-tools/check-status
    │
    ▼
StatusCheckerService.check_status(urls)
    │
    ├── For each URL:
    │   ├── Resolve Profile URN
    │   ├── Fetch profile data or relationship status via Voyager API
    │   ├── (e.g. GET /voyager/api/identity/profiles/{id}/networkinfo)
    │   ├── Determine if `distance == "DISTANCE_1"` (1st degree connection = Accepted)
    │   └── Return Status: "Connected", "Pending", or "Not Connected"
    │
    ▼
Return Enriched Data → Frontend offers Download XLSX
```

## Backend Plan

### [NEW] `core/services/linkedin_tools/status_checker.py`

```python
class StatusCheckerService:
    async def check_status(self, urls: List[str]) -> Dict[str, Any]:
        # 1. Load session
        # 2. Iterate URLs (can be batched 5-10 at a time for reads, less risky than writes)
        # 3. For each URL:
        #    - Extract public identifier
        #    - GET https://www.linkedin.com/voyager/api/identity/profiles/{id}/networkinfo
        #    - Check response:
        #      if data.get('distance') == 'DISTANCE_1': status = "Connected"
        #      elif data.get('distance') == 'OUT_OF_NETWORK': status = "Not Connected" / "Pending"
        # 4. Return mapping of URL -> Status
```

### [MODIFY] `api/routes/linkedin_tools.py`

Append route:
```python
class CheckStatusRequest(BaseModel):
    urls: List[str]

@router.post("/check-status")
async def check_status(request: CheckStatusRequest):
    service = StatusCheckerService()
    return await service.check_status(request.urls)
```

## Frontend Plan

### [NEW] `ui/linkedin_status_checker.html`

- Excel upload for "LinkedIn URL".
- Table displays: URL | Current Status.
- "Check Status" button.
- "Download Results" button to get the Excel back with a new "Connection Status" column.

## Safety — Additive Only Checklist

- [x] Read-only operations on LinkedIn (very safe).
- [x] No existing files deleted.
- [x] Isolated new service class.
