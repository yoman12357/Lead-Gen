import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import company_intel
from core.services.company_intel.pdf import build_company_intel_pdf, company_intel_pdf_filename
from core.services.company_intel.service import CompanyIntelService
from core.services.company_intel.store import CompanyIntelRunStore


class FakeTavily:
    async def search(self, payload):
        return {
            "results": [
                {
                    "title": "Acme Upfit - Official Site",
                    "url": "https://acmeupfit.example",
                    "content": "Acme Upfit provides fleet upfitting and commercial vehicle equipment.",
                },
                {
                    "title": "Acme Upfit LinkedIn",
                    "url": "https://www.linkedin.com/company/acme-upfit",
                    "content": "Company social profile.",
                },
            ]
        }


class FakeHunterPipeline:
    api_key = "test-key"

    async def _hunter_domain_search(self, domain):
        assert domain == "acmeupfit.com"
        return {
            "organization": "Acme Upfit",
            "emails": [
                {
                    "value": "jane@acmeupfit.com",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "position": "Founder",
                    "confidence": 95,
                }
            ],
        }

    def _assemble_domain_search_leads(self, *, domain_payloads, industry, location, target_count):
        return [
            {
                "company_name": "Acme Upfit",
                "contact_person_name": "Jane Smith",
                "contact_person_title": "Founder",
                "contact_email": "jane@acmeupfit.com",
                "quality_score": 95,
                "verification_status": "hunter_verified",
                "source_urls": ["https://acmeupfit.com"],
                "domain": "acmeupfit.com",
            }
        ][:target_count]


class FakeHunterWithoutKey:
    api_key = ""


class HubSpotLikeTavily:
    async def search(self, payload):
        return {
            "results": [
                {
                    "title": "HubSpot - LinkedIn",
                    "url": "https://www.linkedin.com/company/hubspot",
                    "content": "LinkedIn company page.",
                },
                {
                    "title": "HubSpot LinkedIn Integration",
                    "url": "https://closelyhq.com/integrations/hubspot-linkedin-integration",
                    "content": "Third-party integration for HubSpot.",
                },
            ]
        }


class HubSpotHunterPipeline:
    api_key = "test-key"

    def __init__(self):
        self.searched_domain = ""

    async def _hunter_domain_search(self, domain):
        self.searched_domain = domain
        return {
            "organization": "HubSpot",
            "emails": [
                {
                    "value": "jane.smith@hubspot.com",
                    "first_name": "Jane",
                    "last_name": "Smith",
                    "position": "VP Sales",
                    "confidence": 91,
                    "linkedin": "https://www.linkedin.com/in/jane-smith",
                },
                {
                    "value": "support@hubspot.com",
                    "confidence": 80,
                },
            ],
        }

    def _assemble_domain_search_leads(self, *, domain_payloads, industry, location, target_count):
        domain = domain_payloads[0]["domain"]
        data = domain_payloads[0]["data"]
        leads = []
        for email_item in data["emails"]:
            first = email_item.get("first_name") or ""
            last = email_item.get("last_name") or ""
            leads.append(
                {
                    "company_name": "HubSpot",
                    "domain": domain,
                    "contact_person_name": " ".join(part for part in [first, last] if part),
                    "contact_person_title": email_item.get("position") or "",
                    "contact_email": email_item["value"],
                    "quality_score": email_item.get("confidence"),
                    "verification_status": "hunter_verified",
                    "linkedin_url": email_item.get("linkedin") or "",
                }
            )
        return leads[:target_count]


def test_parse_prompt_extracts_company_name():
    parsed = CompanyIntelService.parse_prompt("Show details and leads for HubSpot")
    assert parsed["company_name"] == "HubSpot"


def test_chat_asks_clarifying_question_when_company_missing(tmp_path):
    service = CompanyIntelService(store=CompanyIntelRunStore(tmp_path / "runs.json"))
    result = asyncio.run(service.chat(prompt="show me company details"))
    assert result["success"] is False
    assert result["run_id"] == ""
    assert "Which company" in result["assistant_message"]


def test_company_intel_run_collects_profile_leads_and_persists(tmp_path, monkeypatch):
    async def fake_fetch_page(self, url):
        return {
            "url": url,
            "html": "<html><body>Call (212) 555-0199. Email hello@acmeupfit.com.</body></html>",
            "text": "Acme Upfit provides fleet upfitting and commercial vehicle equipment.",
        }

    monkeypatch.setattr(CompanyIntelService, "_fetch_page", fake_fetch_page)
    store = CompanyIntelRunStore(tmp_path / "runs.json")
    service = CompanyIntelService(
        store=store,
        tavily_factory=lambda: FakeTavily(),
        hunter_pipeline_factory=lambda: FakeHunterPipeline(),
    )

    result = asyncio.run(service.chat(prompt="Show details and leads for Acme Upfit", lead_count=8))

    assert result["success"] is True
    assert result["run_id"]
    assert result["company_profile"]["website"] == "https://www.acmeupfit.com"
    assert result["leads"][0]["contact_person_name"] == "Jane Smith"
    assert store.get_run(result["run_id"])["run_id"] == result["run_id"]


def test_company_intel_prefers_actual_company_domain_over_integration_pages(tmp_path, monkeypatch):
    async def fake_fetch_page(self, url):
        return {
            "url": url,
            "html": "<html><body>HubSpot customer platform and CRM software.</body></html>",
            "text": "HubSpot customer platform and CRM software.",
        }

    hunter = HubSpotHunterPipeline()
    monkeypatch.setattr(CompanyIntelService, "_fetch_page", fake_fetch_page)
    service = CompanyIntelService(
        store=CompanyIntelRunStore(tmp_path / "runs.json"),
        tavily_factory=lambda: HubSpotLikeTavily(),
        hunter_pipeline_factory=lambda: hunter,
    )

    result = asyncio.run(service.chat(prompt="Show details and leads for HubSpot", lead_count=8))

    assert result["company_profile"]["website"] == "https://www.hubspot.com"
    assert hunter.searched_domain == "hubspot.com"
    assert result["leads"][0]["contact_person_name"] == "Jane Smith"
    assert result["leads"][0]["linkedin_url"] == "https://www.linkedin.com/in/jane-smith"
    assert result["leads"][1]["contact_email"] == "support@hubspot.com"


def test_company_intel_keeps_profile_when_hunter_is_unavailable(tmp_path, monkeypatch):
    async def fake_fetch_page(self, url):
        return {
            "url": url,
            "html": "<html><body>Email hello@acmeupfit.com.</body></html>",
            "text": "Acme Upfit provides fleet upfitting.",
        }

    monkeypatch.setattr(CompanyIntelService, "_fetch_page", fake_fetch_page)
    service = CompanyIntelService(
        store=CompanyIntelRunStore(tmp_path / "runs.json"),
        tavily_factory=lambda: FakeTavily(),
        hunter_pipeline_factory=lambda: FakeHunterWithoutKey(),
    )

    result = asyncio.run(service.chat(prompt="Show details and leads for Acme Upfit", lead_count=8))

    assert result["success"] is True
    assert result["company_profile"]["company_name"] == "Acme Upfit"
    assert result["leads"] == []
    assert any("HUNTER_API_KEY" in warning for warning in result["warnings"])


def test_company_intel_pdf_is_pdf_bytes():
    run = {
        "run_id": "run-1",
        "prompt": "Show details and leads for Acme",
        "timestamp": "2026-07-04T00:00:00+00:00",
        "company_profile": {
            "company_name": "Acme",
            "summary": "Acme builds useful products.",
            "services": ["Consulting"],
            "contacts": {"emails": ["hello@acme.example"], "phones": []},
            "social_links": [],
            "source_urls": ["https://acme.example"],
        },
        "leads": [{"contact_person_name": "Jane Smith", "contact_email": "jane@acme.example"}],
        "warnings": [],
        "errors": [],
    }
    pdf = build_company_intel_pdf(run)
    assert pdf.startswith(b"%PDF-1.4")
    assert company_intel_pdf_filename(run) == "company_intel_acme_2026-07-04.pdf"


def test_company_intel_route_chat_and_pdf(monkeypatch):
    saved_run = {
        "run_id": "abc123",
        "prompt": "Show details and leads for Acme",
        "timestamp": "2026-07-04T00:00:00+00:00",
        "success": True,
        "assistant_message": "ok",
        "company_profile": {"company_name": "Acme", "summary": "Acme summary."},
        "leads": [],
        "warnings": [],
        "errors": [],
        "steps": [],
    }

    class FakeService:
        async def chat(self, *, prompt, lead_count, session_id):
            return saved_run

    class FakeStore:
        def get_run(self, run_id):
            return saved_run if run_id == "abc123" else None

    monkeypatch.setattr(company_intel, "_service", lambda: FakeService())
    monkeypatch.setattr(company_intel, "_run_store", lambda: FakeStore())
    app = FastAPI()
    app.include_router(company_intel.router, prefix="/api/company-intel")
    client = TestClient(app)

    chat_response = client.post("/api/company-intel/chat", json={"prompt": "Show details and leads for Acme"})
    assert chat_response.status_code == 200
    assert chat_response.json()["run_id"] == "abc123"

    pdf_response = client.get("/api/company-intel/run/abc123/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF-1.4")
