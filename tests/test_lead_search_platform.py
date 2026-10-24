import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.services.lead_search_engine import LeadSearchEngine, visible_text, indexed_text, company_identity
from core.services.lead_search_jobs import LeadSearchJobs
from core.services.lead_search_policy import SearchIntent, location_evidence, industry_evidence, domain_key, is_listing_source
from core.services.production_lead_pipeline import ProductionLeadPipeline


def test_geography_never_uses_customer_travel_or_other_country():
    assert not location_evidence("Our client Yama Vans from Canada travelled to Hawaii for vacation. Call 5551234567.", "Hawaii")["matched"]
    assert not location_evidence("Canada if not North America not only is the HI", "Hawaii")["matched"]
    assert location_evidence("Office address: 123 Main Street, Honolulu, HI 96813. Call us.", "Hawaii")["matched"]
    assert not location_evidence("Office: Miami FL 33130, USA", "Delhi")["matched"]
    assert not location_evidence("Custom camper vans in Colorado. Build options based on travel needs, island use, and storage requirements. We offer vans for sale in Hawaii.", "Hawaii")["matched"]
    assert location_evidence("Contact our London office: 10 High Street, London EC1A 1BB", "London")["matched"]


def test_query_expansion_stays_in_market_and_splits_niche():
    intent = SearchIntent("Van Upfitters / RV Builders", "Hawaii", 15)
    assert len(intent.terms) > 2
    assert all("Hawaii" in q for n in range(4) for q in intent.queries(n))
    assert not industry_evidence("Our van rental fleet", intent.industry)["matched"]
    assert industry_evidence("Custom van conversion and campervan builds", intent.industry)["matched"]


def test_visible_text_retains_address_and_drops_script_names():
    assert visible_text('<script>Fake Person</script><p>Business</p><address>London EC1A 1BB</address>') == 'Business\nLondon EC1A 1BB'


def test_listing_sources_and_search_urls_are_not_company_evidence():
    for url in ('https://leadiq.com/c/example', 'https://www.designrush.com/agency/digital-marketing/in/mumbai', 'https://accountantsbook.co.uk/firm'):
        assert is_listing_source(url)
    assert is_listing_source('https://unknown-listing.test', 'MJH Accounting Firm in London. Add your Business. Classifieds.')
    assert not is_listing_source('https://agency.test', 'Best Digital Marketing Agency in Mumbai | Agency')
    cleaned = indexed_text('[Contact us](https://example.test/london-office) ![Company](data:image/svg+xml,20345)')
    assert 'london' not in cleaned and '20345' not in cleaned
    assert not location_evidence(cleaned, 'London')['matched']
    assert not industry_evidence('Rent our camper vans for a holiday', 'Van Upfitters / RV Builders')['matched']


def test_organization_name_from_structured_data():
    pages = [{'html': '<script type="application/ld+json">{"@graph":[{"@type":"Organization","name":"Actual Company","url":"https://company.test"}]}</script>'}]
    assert company_identity(pages, 'company.test') == 'Actual Company'
    assert company_identity(pages, 'other.test') == ''


@pytest.mark.parametrize('contact_markup, expected', [
    ('<form><input name="email"></form>', False),
    ('<form><textarea name="message"></textarea></form>', True),
    ('<a href="mailto:examplebusiness@gmail.com">examplebusiness@gmail.com</a>', True),
])
def test_only_real_contact_routes_count(contact_markup, expected):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        markup = '<title>Example Agency</title><p>We are a digital marketing agency in Mumbai.</p><address>Office: Mumbai 400020</address>' + contact_markup
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://example.test/contact', 'html': markup, 'text': visible_text(markup)}])
        engine.extract_fallback = AsyncMock(return_value=[])
        engine.hunter_fallback = AsyncMock(return_value='')
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        lead = await engine.enrich({'url': 'https://example.test', 'title': 'Example Agency'})
        assert bool(lead and lead['usable']) == expected
        if lead:
            assert not lead['email_smtp_verified']
    asyncio.run(run())


def test_search_api_validation_idempotency_and_cancel(tmp_path, monkeypatch):
    from fastapi import FastAPI
    import httpx
    from api.routes import lead_search
    class Pipeline:
        async def run(self, **kwargs):
            await asyncio.sleep(30)
    async def run():
        jobs = LeadSearchJobs(tmp_path / 'api.sqlite3', pipeline_factory=Pipeline)
        monkeypatch.setattr(lead_search, 'jobs', jobs)
        app = FastAPI()
        app.include_router(lead_search.router, prefix='/api/lead-searches')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            request = {'industry': ' Accountants ', 'location': 'London', 'target_count': 15, 'request_key': 'integration-request-001'}
            first = await client.post('/api/lead-searches', json=request)
            assert first.status_code == 202
            job = first.json()
            assert job['request']['industry'] == 'Accountants'
            again = await client.post('/api/lead-searches', json=request)
            assert again.json()['id'] == job['id']
            assert (await client.post('/api/lead-searches', json={**request, 'location': 'Paris'})).status_code == 409
            for bad in ({'target_count': 51}, {'target_count': 0}, {'industry': '  '}, {'request_key': 'short'}):
                assert (await client.post('/api/lead-searches', json={**request, **bad})).status_code == 422
            assert (await client.get('/api/lead-searches/unknown')).status_code == 404
            cancelled = await client.post(f"/api/lead-searches/{job['id']}/cancel")
            assert cancelled.json()['status'] == 'cancelled'
            assert (await client.get(f"/api/lead-searches/{job['id']}")).json()['status'] == 'cancelled'
        await jobs.close()
    asyncio.run(run())


def test_public_api_does_not_trust_spoofed_origin(monkeypatch):
    from fastapi import FastAPI
    import httpx
    from api.auth import api_key_middleware
    async def run():
        monkeypatch.setenv('APP_ENV', 'production')
        monkeypatch.setenv('AGENTIC_CORE_API_KEY', 'synthetic-test-key')
        app = FastAPI()
        app.middleware('http')(api_key_middleware)
        @app.get('/api/test')
        async def endpoint():
            return {'ok': True}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            for headers in ({'Origin': 'http://localhost'}, {'Referer': 'http://localhost/'}, {'Sec-Fetch-Site': 'same-origin'}):
                assert (await client.get('/api/test', headers=headers)).status_code == 401
            assert (await client.get('/api/test', headers={'X-API-Key': 'synthetic-test-key'})).status_code == 200
    asyncio.run(run())


class FakeExtractor:
    def __init__(self):
        self.tavily = SimpleNamespace(search=AsyncMock())
    _is_directory_or_noise_url = staticmethod(lambda url: "directory.test" in url)


def test_fill_loop_keeps_searching_after_rejections_and_deduplicates():
    async def run():
        extractor = FakeExtractor()
        counter = 0
        async def search(payload):
            nonlocal counter
            counter += 1
            start = 0 if counter <= 3 else (counter - 3) * 10
            return {"results": [{"url": f"https://company{i}.test/contact", "title": f"Marketing company {i}", "content": "Digital marketing agency in London"} for i in range(start, start + 10)]}
        extractor.tavily.search.side_effect = search
        engine = LeadSearchEngine(extractor)
        async def enrich(item):
            index = int(domain_key(item["url"]).split(".")[0].replace("company", ""))
            if index % 3 == 0:
                engine.rejections["location_unconfirmed"] += 1
                return None
            return {"company_name": str(index), "company_website": item["url"], "usable": True, "quality_score": 65, "contact_email": f"info@company{index}.test"}
        engine.enrich = enrich
        updates = []
        async def progress(result):
            updates.append(len(result["leads"]))
        result = await engine.run(SearchIntent("Digital Marketing", "London", 15), on_progress=progress)
        assert len(result["leads"]) == 15
        assert len({domain_key(row["company_website"]) for row in result["leads"]}) == 15
        assert len(result["metadata"]["queries_used"]) > 3
        assert result["metadata"]["stop_reason"] == "target_reached"
        assert any(0 < count < 15 for count in updates)
    asyncio.run(run())


def test_provider_fallback_and_budget_cap():
    async def run():
        extractor = FakeExtractor()
        extractor.tavily.search.side_effect = RuntimeError("primary unavailable")
        engine = LeadSearchEngine(extractor, search_budget=2)
        engine.html_fallback.search = AsyncMock(return_value={"results": [{"url": "https://company.test", "title": "Company"}]})
        engine.enrich = AsyncMock(return_value=None)
        result = await engine.run(SearchIntent("Accounting", "London", 15))
        assert len(result["metadata"]["queries_used"]) == 2
        assert "duckduckgo_html" in result["metadata"]["providers_used"]
        assert result["metadata"]["shortfall"] == 15
        assert result["metadata"]["stage"] == "partial"
    asyncio.run(run())


def test_deadline_preserves_previously_found_leads():
    async def run():
        extractor = FakeExtractor()
        engine = LeadSearchEngine(extractor, max_seconds=.05)
        async def search(query):
            engine.accepted["company.test"] = {"company_name": "Saved", "quality_score": 50}
            await asyncio.sleep(.2)
        engine.search = search
        result = await engine.run(SearchIntent("Accountants", "London", 15))
        assert len(result["leads"]) == 1
        assert result["metadata"]["stop_reason"] == "time_budget_reached"
    asyncio.run(run())


def test_public_fetch_rejects_local_addresses():
    async def run():
        engine = LeadSearchEngine(FakeExtractor())
        assert not await engine.public_url("http://127.0.0.1:8000/private")
        assert not await engine.public_url("http://169.254.169.254/latest/meta-data/")
        assert not await engine.public_url("file:///etc/passwd")
    asyncio.run(run())


def test_jobs_idempotency_cancellation_and_restart_recovery(tmp_path):
    async def run():
        class Pipeline:
            async def run(self, **kwargs):
                await kwargs["on_progress"]({"leads": [{"company_name": "Saved"}], "metadata": {"stage": "enriching"}})
                await asyncio.sleep(30)
        path = tmp_path / "jobs.sqlite3"
        jobs = LeadSearchJobs(path, pipeline_factory=Pipeline)
        request = {"industry": "Accountants", "location": "London", "target_count": 15, "target_role": ""}
        first = await jobs.create(request, "same-key")
        second = await jobs.create(request, "same-key")
        assert first["id"] == second["id"]
        await asyncio.sleep(.02)
        result = await jobs.cancel(first["id"])
        assert result["status"] == "cancelled"
        assert result["result"]["leads"][0]["company_name"] == "Saved"
        other = await jobs.create(request, "other-key")
        await asyncio.sleep(.02)
        await jobs.close()
        restored = LeadSearchJobs(path)
        assert restored.get(other["id"])["status"] == "interrupted"
        assert restored.get(first["id"])["status"] == "cancelled"
    asyncio.run(run())
