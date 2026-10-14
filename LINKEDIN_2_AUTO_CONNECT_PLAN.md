# LinkedIn Auto Connection Sender — Implementation Plan (2 of 4)

## Goal

Upload an Excel file containing **LinkedIn URLs**, and automatically send connection requests to those people using the authenticated LinkedIn session.

## Scope (Additive Only)

- **Add** a new service: `core/services/linkedin_tools/auto_connector.py`
- **Add** a new API route in `api/routes/linkedin_tools.py` → `POST /api/linkedin-tools/send-connections`
- **Add** a new UI page: `ui/linkedin_auto_connect.html`
- **No changes** to any existing files except `api/main.py` (to register the UI route)
- **No deletion** of existing code or data.

## Non-Goals

- Bypassing LinkedIn limits. The system will respect strict rate limits and daily caps.
- Auto-solving CAPTCHAs.

## Architecture

```
Excel Upload (LinkedIn URL)
    │
    ▼
POST /api/linkedin-tools/send-connections
    │
    ▼
AutoConnectorService.send_connections(urls)
    │
    ├── Check daily limit & delays
    ├── For each URL:
    │   ├── Resolve Profile URN using Voyager API (similar to existing logic)
    │   ├── Call: POST /voyager/api/voyagerRelationshipsDashMemberRelationships?action=verifyQuotaAndCreate
    │   ├── Wait random delay (e.g., 45-90 seconds) to avoid ban
    │   └── Record Success/Failure
    │
    ▼
Return Results → Frontend updates table statuses
```

## Backend Plan

### [NEW] `core/services/linkedin_tools/auto_connector.py`

Create a service class that leverages the existing `li_at` cookie.
```python
class AutoConnectorService:
    def __init__(self):
        # Configure safe limits
        self.daily_limit = 20  # Very safe limit
        self.delay_min = 45
        self.delay_max = 90

    async def send_connections(self, urls: List[str]) -> Dict[str, Any]:
        # 1. Load session from linkedin_session.json
        # 2. Setup HTTPX client with correct headers (CSRF, User-Agent)
        # 3. For each URL:
        #    a. Resolve to URN
        #    b. Send connection request
        #    c. Sleep random delay
        # 4. Return summary of sent/failed/skipped
```

### [MODIFY] `api/routes/linkedin_tools.py`

Append route:
```python
class SendConnectionsRequest(BaseModel):
    urls: List[str]

@router.post("/send-connections")
async def send_connections(request: SendConnectionsRequest):
    service = AutoConnectorService()
    return await service.send_connections(request.urls)
```

## Frontend Plan

### [NEW] `ui/linkedin_auto_connect.html`

- Excel upload button targeting a column named "LinkedIn URL" or "LinkedIn".
- Table showing the uploaded URLs and a "Status" column (Pending, Sent, Failed).
- A "Start Sending" button that triggers the API.
- A visual progress bar and real-time status updates (if using SSE) or chunked polling to respect the long delays without timing out the HTTP request.

## Safety — Additive Only Checklist

- [x] No existing files deleted
- [x] Isolated service class
- [x] Uses existing session file without modifying it
