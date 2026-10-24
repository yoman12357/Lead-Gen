import asyncio
import json

import httpx
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.services.lead_search_policy import SearchIntent, industry_evidence, location_evidence
from core.services.lead_search_policy import is_listing_source
from core.services.lead_search_engine import company_identity, contact_material, visible_text
from core.services.lead_search_engine import LeadSearchEngine
from core.services.production_lead_pipeline import ProductionLeadPipeline
from core.utils.phone_quality import extract_phone_candidates
from core.tools.external.tavily_client import TavilyClient


@pytest.mark.parametrize('industry,text', [
    ('Dentists', 'Our dentist offers dental care.'),
    ('Law Firms', 'We are a law firm providing legal services.'),
    ('Architects', 'An architecture studio providing architectural design.'),
    ('Solar Installers', 'Solar panel installation and maintenance.'),
])
def test_profession_variants(industry, text):
    assert industry_evidence(text, industry)['matched']
    assert len(SearchIntent(industry, 'City').terms) >= 3


@pytest.mark.parametrize('industry,text', [
    ('Dentists', 'We sell office equipment.'),
    ('Law Firms', 'An architectural firm offering design services.'),
    ('Architects', 'A dental care clinic.'),
    ('Solar Installers', 'Software installation services and astronomy research.'),
])
def test_other_professions_do_not_match(industry, text):
    assert not industry_evidence(text, industry)['matched']


@pytest.mark.parametrize('location,address', [
    ('Sydney', 'Contact: 10 George Street, Sydney NSW 2000'),
    ('Toronto', 'Address: 123 King Street, Toronto ON M5H 1J9'),
    ('Bengaluru', 'Office: 4 MG Road, Bangalore 560001'),
    ('Austin, Texas', 'Address: 10 Congress Avenue, Austin TX 78701'),
])
def test_local_postcodes(location, address):
    assert location_evidence(address, location)['basis'] == 'address'


@pytest.mark.parametrize('url,text', [
    ('https://prospeo.io/c/a-dental-clinic', 'Dental Clinic Overview'),
    ('https://unknown.test/profile/company', 'Clinic Email Formats\nCompany overview NAICS 6212'),
    ('https://starleads.in/list', 'Architects contact number list'),
    ('https://unknown.test/list', 'Architects Contact Number List\nBuild your own list\nBulk data'),
    ('https://directory.unknown.test/clinic', 'Sydney Dental Hospital'),
    ('https://unknown.test/ecodentistry-members/', 'Eco Dentistry Association'),
    ('https://unknown.test/member', 'WayAhead Directory\nSydney dental clinic'),
    ('https://unknown.test/BusinessListings.aspx', 'Architects'),
    ('https://unknown.test/', 'Find providers\nList your Business'),
    ('https://unknown.test/installers/TX/austin', 'Best Companies for Solar Panels in Austin'),
    ('https://unknown.test/', 'View Listing\nSend Message\nSee Phone Number'),
    ('https://unknown.test/', 'Your Dentist is a comprehensive directory of dentists. No dentists work at our offices.'),
])
def test_company_databases_are_not_official_businesses(url, text):
    assert is_listing_source(url, text)


def test_company_home_brand_takes_priority_over_office_page_name():
    pages = [{'url': 'https://brand.test/offices/toronto', 'html': '<meta property="og:site_name" content="Toronto">'},
             {'url': 'https://brand.test/', 'html': '<meta property="og:site_name" content="Brand Law">'}]
    assert company_identity(pages, 'brand.test', excluded_names=['Toronto']) == 'Brand Law'


def test_fax_label_is_specific_to_number_even_when_phone_is_nearby():
    numbers = extract_phone_candidates('Toronto office\nPhone: 416.863.1200\nF: 416.863.1716', region='CA')
    assert [number['e164'] for number in numbers] == ['+14168631200']


def test_fax_svg_label_survives_contact_text_sanitization():
    markup = '<div>416.863.1200</div><svg><g id="Fax"><path/></g></svg><div>416.863.1716</div>'
    _, text = contact_material({'html': markup, 'text': visible_text(markup)})
    assert [number['e164'] for number in extract_phone_candidates(text, region='CA')] == ['+14168631200']


def test_service_area_does_not_borrow_another_city_postcode():
    assert not location_evidence('3998 Highway 290 Dripping Springs TX 78620\nAreas served: Austin, Texas and Dallas', 'Austin, Texas')['matched']
    assert not location_evidence('4000 Sunrise Rd, Round Rock TX 78665\nLocations: Austin\nSan Antonio\nRound Rock', 'Austin, Texas')['matched']
    assert not location_evidence('Wipro House, Bengaluru. This client headquarters in Bangalore is designed by us.', 'Bengaluru')['matched']
    numbers = extract_phone_candidates('Phone: 416.863.1200\nFax: 416.863.1716', region='CA')
    assert [number['e164'] for number in numbers] == ['+14168631200']


@pytest.mark.parametrize('text', [
    'Solar Solutions. As a department of the City of Austin we offer solar installation incentives.',
    'Solar Panel Installation Permits in Austin County, Texas',
    'Free Texas Solar Incentives: Register for Solar Credit Program (Open Enrollment). Solar installation information.',
])
def test_solar_information_sources_are_not_installation_companies(text):
    assert not industry_evidence(text, 'Solar Installers')['matched']


def test_expansion_excludes_discovered_domains_to_find_new_businesses():
    async def run():
        search = AsyncMock(return_value={'results': [{'url': 'https://new-company.test'}]})
        engine = LeadSearchEngine(SimpleNamespace(tavily=SimpleNamespace(search=search)))
        engine.is_cancelled = lambda: False
        engine.discovered = {'old-company.test', 'directory.test'}
        result = await engine.search('another local company')
        assert result[0]['url'] == 'https://new-company.test'
        assert search.call_args.args[0]['exclude_domains'] == ['directory.test', 'old-company.test']
    asyncio.run(run())


def test_domain_enrichment_does_not_select_unrelated_office_person(monkeypatch):
    monkeypatch.setenv('HUNTER_API_KEY', 'synthetic')
    client_type = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, json={'data': {'emails': [
            {'value': 'susan@company.test', 'sources': [{'uri': 'https://company.test/people/susan-leeds'}]},
            {'value': 'info@company.test', 'sources': [{'uri': 'https://company.test/contact'}]},
        ]}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    async def run():
        engine = LeadSearchEngine(SimpleNamespace())
        assert await engine.hunter_fallback('company.test') == 'info@company.test'
    asyncio.run(run())


@pytest.mark.parametrize('name,reason', [('NSW Government', 'government_information_portal'),
    ('Main Street Publishing Pty Ltd', 'information_or_membership_organization'),
    ('Texas Solar Energy Society', 'information_or_membership_organization'),
    ('Travis County', 'information_or_membership_organization')])
def test_government_portal_is_not_qualified_from_unrelated_dental_information(name, reason):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Dentists', 'Sydney')
        engine.is_cancelled = lambda: False
        markup = f'<meta property="og:site_name" content="{name}"><p>Information on dental care.</p><address>Premier contact office Sydney NSW 2001</address><a href="tel:+61292285871">Call</a>'
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://gov.test/', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'no_email_found', 'mx_found': False, 'smtp_verified': False})
        assert await engine.enrich({'url': 'https://gov.test/', 'title': 'NSW Government'}) is None
        assert engine.rejections[reason] == 1
    asyncio.run(run())


def test_multi_office_domestic_phone_keeps_published_country():
    numbers = extract_phone_candidates('250 Hudson St, New York, NY, USA 10013\n212 620 0996\nNew York City', region='IN')
    assert [number['e164'] for number in numbers] == ['+12126200996']
    numbers = extract_phone_candidates('Bengaluru, Karnataka, India 560034\n+91 80 25522952', region='IN')
    assert [number['e164'] for number in numbers] == ['+918025522952']


def test_request_credit_records_include_zero_unknown_errors_and_cancellation(monkeypatch):
    responses = iter([
        httpx.Response(200, json={'usage': {'credits': 1}, 'request_id': 'a'}),
        httpx.Response(200, json={'usage': {'credits': 0}}),
        httpx.Response(429, json={'detail': 'busy'}),
        asyncio.CancelledError(),
    ])
    class FakeClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json):
            assert json['include_usage'] is True
            value = next(responses)
            if isinstance(value, BaseException):
                raise value
            return value
    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)
    async def run():
        client = TavilyClient('secret-test')
        payload = client._sanitize_search_payload({'query': 'company'})
        for _ in range(3):
            await client._post('search', {'api_key': 'secret-test', **payload}, 1)
        with pytest.raises(asyncio.CancelledError):
            await client._post('extract', client._sanitize_extract_payload({'urls': ['https://example.com']}), 1)
        report = client.usage_report()
        assert report['reported_credits'] == 1
        assert report['attempts'] == 4 and report['unreported_attempts'] == 2
        assert report['complete'] is False
        assert 'secret-test' not in json.dumps(report)
        assert TavilyClient('other-key').usage_report()['attempts'] == 0
    asyncio.run(run())
