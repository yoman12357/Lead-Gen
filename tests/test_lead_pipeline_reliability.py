"""Regressions for discovered pipeline failures; no external requests or credits."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.services.lead_search_engine import LeadSearchEngine
from core.services.lead_search_jobs import LeadSearchJobs
from core.services.lead_search_policy import SearchIntent, location_evidence, is_listing_source
from core.services.production_lead_pipeline import ProductionLeadPipeline


@pytest.mark.parametrize('text,location,expected', [
    ('Office: London, Ontario N6A 1A1, Canada', 'London, UK', False),
    ('Office: Paris, Texas 75460 USA', 'Paris, France', False),
    ('Office: London EC1A 1BB, United Kingdom', 'London, UK', True),
    ('Office: Austin, TX 78701 USA', 'Austin, Texas, USA', True),
    ('Office: Mumbai 400020 India', 'Mumbai, India', True),
    ('Delhi/NCR India: +91 74286 93901', 'Delhi', False),
    ('Office address: Delhi 110001 India. Call +91 74286 93901', 'Delhi', True),
    ('Office: London, Ontario 12345 Canada\n\nUK Office: Manchester M1 1AA', 'London, UK', False),
    ('Office: Paris, France 75001. Contact us today.', 'Paris, USA', False),
    ('Office: Paris, Texas 75460 US', 'Paris, USA', True),
])
def test_qualified_locations(text, location, expected):
    assert location_evidence(text, location)['matched'] is expected


def test_unknown_listing_cannot_supply_its_admin_email_for_another_company():
    text = ('Digital Corsel - Digital Marketing Agency in Mumbai 400093. '
            'Contact number: +91 8019997777. Official website : https://digitalcorsel.com/ Share this listing.')
    assert is_listing_source('https://www.joonsquare.com/', text)
    assert not is_listing_source('https://digitalcorsel.com/', 'Official website: https://digitalcorsel.com/')
    assert is_listing_source('https://unknown.test', 'Listing content. ' * 200 + 'Claim this business')


def test_missing_primary_key_still_allows_independent_search(monkeypatch):
    monkeypatch.delenv('TAVILY_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    async def run():
        engine = LeadSearchEngine(ProductionLeadPipeline(), search_budget=1)
        engine.html_fallback.search = AsyncMock(return_value={'results': []})
        result = await engine.run(SearchIntent('Accountants', 'London', 1))
        engine.html_fallback.search.assert_awaited_once()
        assert 'duckduckgo_html' in result['metadata']['providers_used']
    asyncio.run(run())


def test_deadline_preserves_finished_company_in_unfinished_batch():
    async def run():
        extractor = SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(return_value={'results': [
            {'url': 'https://fast.test'}, {'url': 'https://slow.test'}]})),
            _is_directory_or_noise_url=lambda _: False)
        # Assert deadline/checkpoint behavior without an 80ms scheduler race on
        # a busy Windows host; the unfinished peer still takes five seconds.
        engine = LeadSearchEngine(extractor, max_seconds=.4)
        async def enrich(item):
            if 'slow' in item['url']:
                await asyncio.sleep(5)
            return {'company_name': 'Fast', 'company_website': item['url'], 'usable': True, 'quality_score': 60}
        engine.enrich = enrich
        updates = []
        async def progress(snapshot):
            updates.append(len(snapshot['leads']))
        result = await engine.run(SearchIntent('Accounting', 'London', 2), on_progress=progress)
        assert len(result['leads']) == 1
        assert 1 in updates
        assert result['metadata']['stop_reason'] == 'time_budget_reached'
    asyncio.run(run())


def test_target_reached_stops_slow_peers_without_orphan_tasks():
    async def run():
        extractor = SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(return_value={'results': [
            {'url': 'https://fast.test'}, {'url': 'https://slow.test'}]})),
            _is_directory_or_noise_url=lambda _: False)
        engine = LeadSearchEngine(extractor, max_seconds=.2)
        stopped = asyncio.Event()
        async def enrich(item):
            if 'slow' in item['url']:
                try:
                    await asyncio.sleep(10)
                finally:
                    stopped.set()
            return {'company_name': 'Fast', 'company_website': item['url'], 'usable': True, 'quality_score': 60}
        engine.enrich = enrich
        result = await engine.run(SearchIntent('Accounting', 'London', 1))
        assert result['metadata']['stage'] == 'completed'
        assert result['metadata']['stop_reason'] == 'target_reached'
        assert stopped.is_set()
    asyncio.run(run())


def test_restart_repairs_snapshot_and_status_together(tmp_path):
    path = tmp_path / 'restart.sqlite3'
    jobs = LeadSearchJobs(path)
    jobs.start()
    with jobs.connect() as db:
        db.execute('INSERT INTO searches VALUES (?,?,?,?,?,?,?)', ('saved', 'key', '{}', 'enriching',
            json.dumps({'leads': [{'company_name': 'Saved'}], 'metadata': {'stage': 'enriching', 'completed': False}}), 1, 1))
    restored = LeadSearchJobs(path).get('saved')
    assert restored['status'] == restored['result']['metadata']['stage'] == 'interrupted'
    assert restored['result']['metadata']['completed'] is True
    assert restored['result']['metadata']['stop_reason'] == 'server_restarted'
    assert len(restored['result']['leads']) == 1


@pytest.mark.parametrize('first_status,expected_calls', [(503, 2), (429, 2), (404, 1)])
def test_page_fetch_retries_only_transient_errors(first_status, expected_calls):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.public_url = AsyncMock(return_value=True)
        calls = 0
        def handler(request):
            nonlocal calls
            calls += 1
            return httpx.Response(first_status if calls == 1 else 200,
                headers={'content-type': 'text/html', 'retry-after': '0'}, text='<p>Company contact</p>')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            engine.client = client
            result = await engine.fetch('https://company.test')
        assert calls == expected_calls
        assert bool(result) is (first_status != 404)
    asyncio.run(run())


def test_primary_search_retries_transient_failure():
    async def run():
        extractor = SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(side_effect=[
            httpx.ConnectError('temporary'), {'results': [{'url': 'https://company.test'}]}])))
        engine = LeadSearchEngine(extractor)
        engine.is_cancelled = lambda: False
        engine.html_fallback.search = AsyncMock(return_value={'results': []})
        result = await engine.search('accountants London')
        assert len(result) == 1
        assert extractor.tavily.search.await_count == 2
        engine.html_fallback.search.assert_not_awaited()
    asyncio.run(run())


def test_total_provider_outage_is_failed_not_empty_market():
    async def run():
        engine = LeadSearchEngine(SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(side_effect=RuntimeError('unavailable')))), search_budget=1)
        engine.html_fallback.search = AsyncMock(side_effect=RuntimeError('unavailable'))
        result = await engine.run(SearchIntent('Accountants', 'London', 1))
        assert result['metadata']['stage'] == 'failed'
        assert result['metadata']['stop_reason'] == 'provider_error'
        assert result['metadata']['warnings']
    asyncio.run(run())


def test_successful_empty_primary_is_not_reported_as_provider_outage():
    async def run():
        engine = LeadSearchEngine(SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(return_value={'results': []}))), search_budget=1)
        engine.html_fallback.search = AsyncMock(side_effect=RuntimeError('unavailable'))
        result = await engine.run(SearchIntent('Accountants', 'London', 1))
        assert result['metadata']['stage'] == 'partial'
        assert result['metadata']['stop_reason'] == 'search_budget_reached'
    asyncio.run(run())


def test_legacy_workflow_rejects_missing_search_fields_before_provider_calls(monkeypatch):
    from fastapi import HTTPException
    from api.routes import workflow
    monkeypatch.setattr(workflow, 'get_state', lambda: SimpleNamespace(workflow_engine=object()))
    monkeypatch.setattr(workflow, 'ProductionLeadPipeline', lambda: pytest.fail('Provider must not be initialized for invalid input'))
    async def run():
        with pytest.raises(HTTPException) as failure:
            await workflow.run_workflow(workflow.WorkflowRunRequest(workflow_id='lead_generation_directory_pipeline'))
        assert failure.value.status_code == 422
    asyncio.run(run())


def test_null_mx_is_not_a_mail_server(monkeypatch):
    import dns.resolver
    monkeypatch.setattr(dns.resolver, 'resolve', lambda *args, **kwargs: [SimpleNamespace(exchange='.')])
    async def run():
        result = await LeadSearchEngine(SimpleNamespace()).check_email('info@nomail.test')
        assert result['status'] == 'invalid'
        assert not result['mx_found']
    asyncio.run(run())


@pytest.mark.parametrize('dns_result,status', [('null', 'invalid'), ('timeout', 'unconfirmed'), ('nxdomain', 'invalid')])
def test_export_verifier_distinguishes_negative_dns_from_outage(monkeypatch, dns_result, status):
    import dns.exception
    import dns.resolver
    from core.utils import email_verify
    def resolve(*args):
        if dns_result == 'timeout':
            raise dns.exception.Timeout()
        if dns_result == 'nxdomain':
            raise dns.resolver.NXDOMAIN()
        return [SimpleNamespace(preference=0, exchange='.')], 'test'
    monkeypatch.setattr(email_verify, '_resolve_mx_records', resolve)
    monkeypatch.setattr(email_verify.smtplib, 'SMTP', lambda **kw: pytest.fail('No SMTP probe without a usable MX'))
    result = email_verify.verify_email_legitimacy('info@synthetic-company.com')
    assert result['status'] == status
    assert not result['mx_found'] and not result['smtp_verified']


@pytest.mark.parametrize('industry,location,activity,address', [
    ('Digital Marketing', 'Mumbai, India', 'digital marketing agency', 'Mumbai 400020 India'),
    ('Accountants', 'London, UK', 'accounting services', 'London EC1A 1BB United Kingdom'),
    ('SaaS Development', 'Delhi, India', 'SaaS application development services', 'Delhi 110001 India'),
    ('Van Upfitters / RV Builders', 'Hawaii, USA', 'custom van conversion and RV builders', 'Honolulu Hawaii HI 96813 USA'),
])
def test_api_pipeline_to_export_for_multiple_markets(tmp_path, monkeypatch, industry, location, activity, address):
    """Actual engine/fetch/extraction/scoring/job/API/export with controlled I/O."""
    import dns.resolver
    from fastapi import FastAPI
    from api.routes import lead_search, leads
    from core.services.lead_service import LeadService

    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setattr(dns.resolver, 'resolve', lambda *a, **kw: [SimpleNamespace(exchange='mail.company.test.')])
    monkeypatch.setattr(LeadSearchEngine, 'public_url', AsyncMock(return_value=True))
    real_client = httpx.AsyncClient
    markup = f'''<title>Orbit Company</title><p>We provide {activity}.</p>
        <address>Office: {address}</address><a href="/contact">Contact</a>
        <a href="mailto:hello@company.test">hello@company.test</a>'''
    def handler(request):
        return httpx.Response(200, headers={'content-type': 'text/html'}, text=markup)
    def client_factory(**kwargs):
        kwargs.setdefault('transport', httpx.MockTransport(handler))
        return real_client(**kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', client_factory)
    provider = SimpleNamespace(search=AsyncMock(return_value={'results': [
        {'url': 'https://www.company.test/contact', 'title': 'Orbit Company'},
        {'url': 'https://company.test/about', 'title': 'Duplicate'},
    ]}))
    jobs = LeadSearchJobs(tmp_path / 'matrix.sqlite3', pipeline_factory=lambda: ProductionLeadPipeline(tavily_client=provider))
    monkeypatch.setattr(lead_search, 'jobs', jobs)
    saved = []
    store = SimpleNamespace(ensure_store=AsyncMock(), list_leads=AsyncMock(side_effect=lambda: list(saved)),
        save_lead=AsyncMock(side_effect=lambda lead: saved.append(lead)))
    monkeypatch.setattr(leads, 'get_state', lambda: SimpleNamespace(todo_store=store))
    app = FastAPI()
    app.include_router(lead_search.router, prefix='/api/lead-searches')
    app.include_router(leads.router, prefix='/api/leads')

    async def run():
        async with real_client(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/lead-searches', json={
                'industry': industry, 'location': location, 'target_count': 1, 'request_key': 'multi-market-request-001'})
            assert response.status_code == 202
            run_id = response.json()['id']
            async with asyncio.timeout(5):
                while True:
                    row = (await client.get('/api/lead-searches/' + run_id)).json()
                    if row['status'] in {'completed', 'partial', 'failed'}:
                        break
                    await asyncio.sleep(.01)
            assert row['status'] == 'completed', row
            found = row['result']['leads']
            assert len(found) == 1
            assert found[0]['industry_match'] and found[0]['location_match']
            assert found[0]['contact_email'] == 'hello@company.test'
            assert found[0]['email_mx_found'] and not found[0]['email_smtp_verified']
            assert found[0]['contact_person_name'] == ''
            first = await client.post('/api/leads/export', json={'leads': found})
            assert first.status_code == 200 and first.json()['added'] == 1, first.text
            second = await client.post('/api/leads/export', json={'leads': found})
            assert second.json()['added'] == 0 and second.json()['duplicates_skipped'] == 1
            assert LeadService.summarize_leads(found)['verified_leads'] == 0
        await jobs.close()
    asyncio.run(run())


def test_dead_first_email_does_not_hide_second_published_inbox():
    from core.services.lead_search_engine import visible_text
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        markup = '''<title>Orbit Company</title><p>Digital marketing agency in Mumbai 400020</p>
            <a href="mailto:hello@company.test">hello@company.test</a>
            <a href="mailto:orbitoffice@gmail.com">orbitoffice@gmail.com</a>'''
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test/contact', 'html': markup, 'text': visible_text(markup)}])
        async def check(email):
            return {'status': 'invalid' if email.endswith('@company.test') else 'unconfirmed',
                    'mx_found': not email.endswith('@company.test'), 'smtp_verified': False}
        engine.check_email = check
        result = await engine.enrich({'url': 'https://company.test', 'title': 'Orbit Company'})
        assert result and result['usable']
        assert result['contact_email'] == 'orbitoffice@gmail.com'
    asyncio.run(run())


@pytest.mark.parametrize('mailto', ['%20orbitoffice%40gmail.com', 'orbitoffice@gmail.com?subject=Hello%20there'])
def test_mailto_uri_encoding_is_not_part_of_contact_email(mailto):
    from core.services.lead_search_engine import visible_text
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        markup = f'<title>Orbit Company</title><p>Digital marketing agency in Mumbai 400020</p><a href="mailto:{mailto}">Email us</a>'
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test/', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        result = await engine.enrich({'url': 'https://company.test', 'title': 'Orbit Company'})
        assert result and result['usable']
        assert result['contact_email'] == 'orbitoffice@gmail.com'
    asyncio.run(run())


def test_contact_form_remains_usable_through_export_gate():
    from core.services.lead_quality_gate import apply_quality_gate
    from core.services.lead_quality_service import rank_and_enrich_leads
    lead = {'company_name': 'Orbit', 'company_website': 'https://orbit.test',
        'industry': 'Digital Marketing', 'value_proposition': 'Digital marketing agency',
        'location': 'Mumbai', 'industry_match': True, 'location_match': True,
        'contact_page': 'https://orbit.test/contact', 'contact_form_found': True}
    gated, _ = apply_quality_gate([lead])
    ranked, _ = rank_and_enrich_leads(gated)
    assert len(ranked) == 1 and ranked[0]['usable']


def test_export_dedup_normalizes_website_aliases_independent_of_names():
    from core.services.lead_service import LeadService
    registry = LeadService._empty_key_registry()
    LeadService._register_keys(registry, {'company_name': 'Original Name', 'company_website': 'https://www.example-company.com/'})
    assert LeadService._find_duplicate_reason(registry, {
        'company_name': 'Changed Branding', 'company_website': 'example-company.com',
        'contact_email': 'new@example-company.com'}) == 'domain'


def test_fetch_never_follows_redirect_to_private_host():
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.public_url = AsyncMock(side_effect=lambda url: '127.0.0.1' not in url)
        requests = []
        def handler(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            engine.client = client
            assert await engine.fetch('https://company.test') is None
        assert requests == ['https://company.test']
    asyncio.run(run())
