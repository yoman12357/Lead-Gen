import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.services.lead_search_engine import LeadSearchEngine, company_identity, visible_text
from core.services.lead_search_policy import SearchIntent, is_listing_source, location_evidence
from core.services.production_lead_pipeline import ProductionLeadPipeline


@pytest.mark.parametrize('url,text', [
    ('https://ifa.org.uk/find-an-accountant?pg=7', 'Find an Accountant\nM&S Accountants London Ltd. London E1 7DA. mdaparvez@yahoo.com'),
    ('https://regulated-professions.service.gov.uk/professions/chartered-accountant', 'Chartered Accountant\nRegulatory or professional bodies\nRegulatory authority\nLondon EC2R 6EA'),
    ('https://institute.test/', 'Institute of Financial Accountants\nIFA membership\nFind an accountant'),
    ('https://americaninbritain.co.uk/useful-numbers', 'Useful Numbers\nACCOUNTANCY & TAX PREPARATION\nBUZZACOTT LLP\n130 Wood Street, London EC2V 6DL\nWebsite: www.buzzacott.co.uk'),
    ('https://magazine.test?p=useful.numbers', '# Useful Numbers\nAccounting firms in London'),
    ('https://unknown.test/advisers', 'Accounting firms\nWebsite: www.first-firm.com\nWebsite: www.second-firm.co.uk'),
])
def test_member_directories_and_regulators_are_not_operating_companies(url, text):
    assert is_listing_source(url, text)


def test_directory_badge_does_not_turn_an_operating_firm_into_a_directory():
    text = 'US & UK Tax Accountants | Xerxes Associates LLP\nUK Business Directory\nPhone: +44 2074119026\nAddress: Warnford Court, London EC2N 2AT'
    assert not is_listing_source('https://xerxesllp.com/', text)
    assert is_listing_source('https://unknown.test/directory/', text)


@pytest.mark.parametrize('text,location,expected', [
    ('Digital Marketing Agency in Mumbai. Contact: 444 Mathura Rd, New Delhi 110001.', 'Mumbai', False),
    ('Based in Worli, Mumbai. Digital marketing agency.', 'Mumbai', True),
    ('Office: 12 London Road, Braintree CM7 2AA United Kingdom', 'London, UK', False),
    ('Office: 3 London Square, Cross Lanes, Guildford GU1 1UJ UK', 'London, UK', False),
    ('Office: 178 Merton High Street, London SW19 1AY', 'London, UK', True),
])
def test_office_evidence_is_not_a_city_landing_page_or_street_name(text, location, expected):
    assert location_evidence(text, location)['matched'] is expected


def test_generic_meta_name_does_not_override_copyright_brand():
    pages = [{'html': '<meta property="og:site_name" content="Reliable Accounting Services"><footer>©2026 London Accounting Firm | All rights reserved.</footer>'}]
    assert company_identity(pages, 'londonaccountingfirm.co.uk') == 'London Accounting Firm'


def test_unresolved_template_name_and_copyright_year_are_not_company_names():
    pages = [{'html': '<script type="application/ld+json">{"@type":"Organization","name":"#site_title"}</script><footer>Copyright © The Accountancy Partnership 2026</footer>'}]
    assert company_identity(pages, 'theaccountancy.co.uk') == 'The Accountancy Partnership'


def test_domain_as_metadata_name_uses_a_published_logo_brand():
    pages = [{'html': '<meta property="og:site_name" content="911marketingagency.com"><img class="logo" alt="911 Marketing Agency Logo" src="/logo.png">'}]
    assert company_identity(pages, '911marketingagency.com') == '911 Marketing Agency'


def test_contact_links_from_homepage_outrank_unrelated_team_links():
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        home = '<title>Company</title>' + ''.join(f'<a href="/team/{i}">Team</a>' for i in range(6)) + '<a href="/get-in-touch/">Contact us</a>'
        pages = {
            'https://company.test/services/marketing/': '<p>Marketing services</p>',
            'https://company.test/': home,
            'https://company.test/get-in-touch/': '<p>Office Mumbai 400020</p><a href="mailto:solutions@company.test">Email</a>',
        }
        async def fetch(url):
            return {'url': url, 'html': pages[url], 'text': visible_text(pages[url])} if url in pages else None
        engine.fetch = AsyncMock(side_effect=fetch)
        result = await engine.site_pages({'url': 'https://company.test/services/marketing/'})
        assert any(page['url'].endswith('/get-in-touch/') for page in result)
        assert len(result) <= 6
    asyncio.run(run())


def test_plain_phone_next_to_a_tel_link_is_preserved():
    from core.services.lead_search_engine import contact_material
    from core.utils.phone_quality import extract_phone_candidates
    markup = '<p>Call us +91 91521 91510</p><a href="tel:+919152191510">Call us</a>'
    _, text = contact_material({'html': markup, 'text': visible_text(markup)})
    assert any(row['e164'] == '+919152191510' for row in extract_phone_candidates(text, region='IN'))


def test_indexed_markdown_tel_parentheses_do_not_duplicate_or_truncate_phone():
    from core.services.lead_search_engine import indexed_text, contact_material
    from core.utils.phone_quality import extract_phone_candidates
    markdown = 'Tel: [+44 (0)20 7382 1820](tel:+44 (0)20 7382 1820)'
    cleaned = indexed_text(markdown)
    assert cleaned == 'Tel: +44 (0)20 7382 1820'
    _, text = contact_material({'html': markdown, 'text': cleaned})
    assert any(row['e164'] == '+442073821820' for row in extract_phone_candidates(text, region='GB'))


def test_demo_site_with_placeholder_testimonials_does_not_fill_target():
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        markup = '<p>Digital marketing agency based in Mumbai. Lorem ipsum demo. Lorem ipsum portfolio. Blind texts from the far World of Grammar. Founder of XpeedStudio.</p>'
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test', 'html': markup, 'text': visible_text(markup)}])
        assert await engine.enrich({'url': 'https://company.test'}) is None
        assert engine.rejections['unfinished_template_site'] == 1
    asyncio.run(run())


@pytest.mark.parametrize('own_address,expected', [('Office New Delhi 110001 India', False), ('Office Mumbai 400020 India', True)])
def test_competitors_in_a_company_blog_are_not_its_location_evidence(own_address, expected):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        article = '<title>Top Social Media Marketing Agencies in Mumbai</title><p>Competitor Gozoop, Skyline Icon, Mumbai 400059. contact@gozoop.com</p>'
        home = f'<title>Own Company</title><p>Digital marketing services</p><address>{own_address}</address><a href="mailto:info@company.test">Email</a>'
        pages = [{'url': 'https://company.test/top-10-social-media-marketing-agencies-mumbai', 'html': article, 'text': visible_text(article)},
                 {'url': 'https://company.test/contact', 'html': home, 'text': visible_text(home)}]
        engine.site_pages = AsyncMock(return_value=pages)
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        row = await engine.enrich({'url': pages[0]['url']})
        assert bool(row) is expected
        if row:
            assert 'Gozoop' not in row['location_evidence']
            assert row['location_source_url'] == 'https://company.test/contact'
    asyncio.run(run())


def test_generic_meta_name_does_not_override_published_brand_statement():
    pages = [{'html': '<meta property="og:site_name" content="Chartered Accountants"><p>Welcome to ASK Accountants. We provide tax advice.</p>'}]
    assert company_identity(pages, 'askaccountantsukltd.co.uk') == 'ASK Accountants'


@pytest.mark.parametrize('extra,expected_email,expected_phone', [
    ('<script>const id=1768642710; const profile="christian@company.test";</script><a href="tel:+442079460958">Call</a>', '', '+442079460958'),
    ('<a href="mailto:contact@company.in">Contact</a><a href="tel:+442079460958">Call</a>', 'contact@company.in', '+442079460958'),
])
def test_only_published_contacts_are_used_and_same_brand_domains_work(extra, expected_email, expected_phone):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Accountants', 'London, UK')
        engine.is_cancelled = lambda: False
        markup = '<title>Company</title><p>Accounting services</p><address>Office: London SW19 1AY United Kingdom</address>' + extra
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test/contact', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        engine.extract_fallback = AsyncMock(return_value=[])
        engine.hunter_fallback = AsyncMock(return_value='')
        row = await engine.enrich({'url': 'https://company.test/contact', 'title': 'Company'})
        assert row and row['contact_email'] == expected_email
        assert row['contact_phone'] == expected_phone
    asyncio.run(run())


def test_phone_in_script_is_never_selected_over_a_published_phone():
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Digital Marketing', 'Mumbai')
        engine.is_cancelled = lambda: False
        markup = '''<title>Company</title><p>Digital marketing agency based in Mumbai 400018</p>
            <script>const analyticsId=1768642710;</script><p>Call +91 99207 42700</p>
            <a href="mailto:info@company.test">Email</a>'''
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test/contact', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        row = await engine.enrich({'url': 'https://company.test', 'title': 'Company'})
        assert row['contact_phone'] == '+919920742700'
    asyncio.run(run())


def test_requested_office_ranks_above_other_offices_when_confidence_is_capped():
    from core.utils.phone_quality import build_phone_summary
    general = {'e164': '+441376326266', 'display': '+441376326266', 'confidence': 99, 'validation_status': 'valid'}
    local = {'e164': '+442071480872', 'display': '+442071480872', 'confidence': 99, 'validation_status': 'valid', 'requested_office_match': True}
    summary = build_phone_summary([general, local])
    assert summary['contact_phone'] == local['e164']


def test_hunter_fallback_keeps_public_source_urls_and_ignores_removed_sources(monkeypatch):
    import httpx
    monkeypatch.setenv('HUNTER_API_KEY', 'synthetic-test-key')
    real_client = httpx.AsyncClient
    def handler(request):
        return httpx.Response(200, json={'data': {'emails': [
            {'value': 'old@company.test', 'sources': [{'uri': 'https://company.test/old', 'still_on_page': False}]},
            {'value': 'info@company.test', 'sources': [{'uri': 'https://company.test/contact', 'still_on_page': True, 'last_seen_on': '2026-10-22'}]},
        ]}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    async def run():
        engine = LeadSearchEngine(SimpleNamespace())
        email = await engine.hunter_fallback('company.test')
        assert email == 'info@company.test'
        assert engine.hunter_email_sources[email][0]['url'] == 'https://company.test/contact'
    asyncio.run(run())


def test_unrelated_corporate_email_is_not_accepted_from_footer():
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Accountants', 'London, UK')
        engine.is_cancelled = lambda: False
        markup = '<title>Firm</title><p>Accounting services</p><address>Office London SW19 1AY UK</address><a href="mailto:designer@unrelated.test">Website designer</a><a href="tel:+442079460958">Call</a>'
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://company.test/contact', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'no_email_found', 'mx_found': False, 'smtp_verified': False})
        row = await engine.enrich({'url': 'https://company.test', 'title': 'Firm'})
        assert row and row['contact_email'] == ''
    asyncio.run(run())
