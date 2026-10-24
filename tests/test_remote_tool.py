import asyncio

from core.tools.base import ToolContext
from core.tools.external.remote_tool import RemoteToolWrapper


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeAsyncClient:
    last_request = None

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, json, headers):
        FakeAsyncClient.last_request = {
            "method": method,
            "url": url,
            "json": json,
            "headers": headers,
        }
        return FakeResponse({"result": {"ok": True}})


def test_remote_tool_can_send_raw_arguments_with_header_mapping(monkeypatch):
    monkeypatch.setattr("core.tools.external.remote_tool.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("CRM_API_KEY", "test-secret")

    tool = RemoteToolWrapper(
        name="crm_create_prospect",
        description="Create a prospect in your CRM",
        endpoint_url="https://crm.example.com/api/prospects",
        auth_header_name="Authorization",
        auth_header_env="CRM_API_KEY",
        auth_header_prefix="Bearer ",
        request_body_mode="raw_arguments",
        argument_headers={"x-tenant-id": "tenant_id"},
        omit_arguments_from_body=["tenant_id"],
    )

    context = ToolContext(
        session_id="SESS_TEST",
        trace_id="TRACE_TEST",
        state={"agent_id": "lead_gen_agent"},
    )

    result = asyncio.run(
        tool.execute(
            {
                "tenant_id": "tenant_001",
                "title": "Create marketing agent landing page",
                "description": "Build a landing page draft for the marketing agent use case.",
            },
            context,
        )
    )

    assert result.ok is True
    assert FakeAsyncClient.last_request["method"] == "POST"
    assert FakeAsyncClient.last_request["url"] == "https://crm.example.com/api/prospects"
    assert FakeAsyncClient.last_request["headers"]["Authorization"] == "Bearer test-secret"
    assert FakeAsyncClient.last_request["headers"]["x-tenant-id"] == "tenant_001"
    assert "tenant_id" not in FakeAsyncClient.last_request["json"]
    assert FakeAsyncClient.last_request["json"]["title"] == "Create marketing agent landing page"
