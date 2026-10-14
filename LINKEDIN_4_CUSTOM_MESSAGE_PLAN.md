# LinkedIn Custom Message Sender — Implementation Plan (4 of 4)

## Goal

Upload an Excel file with **LinkedIn URLs and custom message templates**. The system fetches the person's name from their profile to personalize the message, and sends it as a Direct Message (DM) to 1st-degree connections.

## Scope (Additive Only)

- **Add** a new service: `core/services/linkedin_tools/message_sender.py`
- **Add** a new API route in `api/routes/linkedin_tools.py` → `POST /api/linkedin-tools/send-messages`
- **Add** a new UI page: `ui/linkedin_message_sender.html`
- **No changes** to existing pipelines.

## Architecture

```
Upload Excel (LinkedIn URL | Custom Message Template)
    │
    ▼
POST /api/linkedin-tools/send-messages
    │
    ▼
MessageSenderService.send_messages(rows)
    │
    ├── Check daily DM limits
    ├── For each row:
    │   ├── Resolve Profile URN & Fetch Profile Data (to get First Name)
    │   ├── Replace {{first_name}} in the Custom Message Template
    │   ├── Call POST /voyager/api/voyagerMessagingDashMessengerMessages?action=createMessage
    │   ├── Sleep random delay (e.g., 30-60 seconds)
    │   └── Record Success/Failure
    │
    ▼
Return Results → Frontend updates table
```

## Backend Plan

### [NEW] `core/services/linkedin_tools/message_sender.py`

```python
class MessageSenderService:
    def __init__(self):
        self.daily_limit = 30  # Safe DM limit

    async def send_messages(self, rows: List[Dict[str, str]]) -> Dict[str, Any]:
        # row shape: {"url": "...", "template": "Hi {{first_name}}, ..."}
        # 1. Load session & setup client
        # 2. Get sender's own URN (required for sending DMs)
        # 3. For each row:
        #    a. Extract public ID and fetch profile to get first name
        #    b. Build final message string
        #    c. Send DM payload to voyagerMessagingDashMessengerMessages
        #    d. Delay
        # 4. Return results
```

### [MODIFY] `api/routes/linkedin_tools.py`

Append route:
```python
class SendMessagesRequest(BaseModel):
    rows: List[Dict[str, str]]

@router.post("/send-messages")
async def send_messages(request: SendMessagesRequest):
    service = MessageSenderService()
    return await service.send_messages(request.rows)
```

## Frontend Plan

### [NEW] `ui/linkedin_message_sender.html`

- Excel upload looking for columns "LinkedIn URL" and "Message Template".
- Table displays: URL | Rendered Message Preview | Status.
- "Start Campaign" button.
- Status column updates in real-time (using chunked requests or SSE to handle delays).

## Safety — Additive Only Checklist

- [x] No existing files deleted.
- [x] Isolated service class.
- [x] Reuses known safe Voyager endpoints.
