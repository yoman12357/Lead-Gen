import asyncio
import json
from unittest.mock import AsyncMock
import httpx
import pytest

from core.services.lead_search_engine import LeadSearchEngine, visible_text
from core.services.lead_search_policy import SearchIntent, location_evidence, is_editorial_source
from core.services.production_lead_pipeline import ProductionLeadPipeline


def test_city_description_is_not_company_presence():
    assert not location_evidence('Locations Served / Dallas, TX. Dallas, located in North Texas, is a thriving cultural hub.', 'Texas')['matched']
    assert not location_evidence('Austin is based in Texas. Our office is in Fresno, CA 93725.', 'Texas')['matched']
    assert location_evidence('Sportsmobile Texas Production, Service & Sales 9805 Gray Blvd Austin, TX 78758', 'Texas')['matched']


def test_press_release_host_and_publisher_are_not_official_company_sources():
    assert is_editorial_source('https://news.marketersmedia.com/texas-van-interiors/89201439')
    assert is_editorial_source('https://publisher.test/', 'MarketersMEDIA Press Release Distribution. Custom van conversion in Texas 76040.')
    assert not is_editorial_source('https://builder.test/', 'Our custom van conversion business in Texas. Read our latest press release.')


def test_licensing_portal_does_not_become_an_rv_manufacturer():
    from core.services.lead_search_policy import is_information_portal
    assert is_information_portal('https://texasdmv.my.salesforce-sites.com/', 'Texas Department of Motor Vehicles manufacturer licensing')
    assert is_information_portal('https://agency.texas.gov/', 'RV manufacturers in Texas')
    assert not is_information_portal('https://builder.test/', 'We are a custom RV manufacturer with our own factory in Texas.')


def test_dealer_navigation_does_not_establish_manufacturing_activity():
    assert enriched('''<title>Example Dealership</title><nav><a>Motorhome Manufacturers</a></nav>
    <main>We sell preowned vehicles and offer storage.</main><address>Austin, TX 78758</address>
    <a href="tel:+15128354409">Call</a>''') is None


def test_indexed_menu_links_also_cannot_establish_business_activity():
    from core.services.lead_search_engine import indexed_activity
    from core.services.lead_search_policy import industry_evidence
    text = '+ [Motorhome Manufacturers](/manufacturers)\nWe sell preowned vehicles and storage.'
    assert not industry_evidence(indexed_activity(text), 'RV Builders')['matched']
    assert industry_evidence(indexed_activity(text + '\nWe provide custom van conversions in our shop.'), 'RV Builders')['matched']


def enriched(markup, industry='Van Upfitters / RV Builders', location='Texas'):
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent(industry, location)
        engine.is_cancelled = lambda: False
        engine.site_pages = AsyncMock(return_value=[{'url': 'https://builder.test/contact', 'html': markup, 'text': visible_text(markup)}])
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        engine.extract_fallback = AsyncMock(return_value=[])
        engine.hunter_fallback = AsyncMock(return_value='')
        return await engine.enrich({'url': 'https://builder.test/', 'title': 'Actual Builder'})
    return asyncio.run(run())


def test_texas_branch_email_and_phone_are_selected_together():
    row = enriched('''<title>Actual Builder</title><p>Custom van conversions</p>
      <section><h2>North</h2><address>250 Court St Huntington, IN 46750</address>
      <a href="tel:2603565435">Call</a><a href="mailto:north@builder.test">Email</a></section>
      <section><h2>Texas</h2><address>9805 Gray Blvd Austin, TX 78758</address>
      <a href="tel:5128354409">Call</a><a href="mailto:texas@builder.test">Email</a></section>''')
    assert row['contact_email'] == 'texas@builder.test'
    assert row['contact_phone'] == '+15128354409'


def test_structured_business_contacts_and_founder_preserve_sources():
    row = enriched('''<title>Actual Builder</title><p>Custom van conversions</p>
    <script type="application/ld+json">{"@type":"LocalBusiness","url":"https://builder.test/","name":"Actual Builder",
    "address":{"@type":"PostalAddress","streetAddress":"11214 S Pipeline Rd","addressLocality":"Euless","addressRegion":"TX","postalCode":"76040","addressCountry":"US"},
    "telephone":"+18173998267","email":"sales@builder.test",
    "founder":{"@type":"Person","name":"Jane Smith","jobTitle":"Founder"}}</script>''')
    assert row and row['company_name'] == 'Actual Builder'
    assert row['contact_email'] == 'sales@builder.test'
    assert row['contact_phone'] == '+18173998267'
    assert row['city'] == 'Euless' and row['state'] == 'TX' and row['zip_code'] == '76040'
    assert row['contact_person_name'] == 'Jane Smith'
    assert row['field_sources']['contact_person_name'] == 'https://builder.test/contact'
    assert not row['email_smtp_verified']


def test_article_author_and_foreign_organization_are_not_company_people():
    row = enriched('''<title>Actual Builder</title><p>Custom van conversions</p><address>Austin, TX 78758</address>
    <a href="tel:+15128354409">Call</a>
    <script type="application/ld+json">{"@type":"Article","author":{"@type":"Person","name":"Wrong Author"}}</script>
    <script type="application/ld+json">{"@type":"LocalBusiness","url":"https://other.test/","email":"wrong@other.test","founder":{"name":"Wrong Founder"}}</script>''')
    assert row and not row['contact_person_name']
    assert row['contact_phone'] == '+15128354409'


def test_nested_graph_branch_data_is_read_but_area_served_is_not_an_address():
    from core.services.public_site_data import public_page
    data = {'@graph': [{'@type': 'Organization', 'url': 'https://builder.test/',
        'areaServed': {'name': 'Texas'}, 'department': {'@type': 'LocalBusiness',
        'address': {'streetAddress': '9805 Gray Blvd', 'addressLocality': 'Austin', 'addressRegion': 'TX', 'postalCode': '78758'},
        'telephone': '+15128354409'}}]}
    page = public_page('<script type="application/ld+json">'+json.dumps(data)+'</script>', 'https://builder.test/')
    assert len(page['addresses']) == 1
    assert '78758' in page['text']
    assert 'areaServed' not in page['text']


def test_discovery_article_resolves_the_business_without_its_publisher_contacts():
    from core.services.public_site_data import public_page, business_website_links
    page = public_page('''<header><a href="https://ads.test">Ads</a></header>
    <article>Texas Van Interiors: <a href="https://texasvaninteriors.com/">Visit official website</a></article>
    <footer><a href="https://publisher.test/contact">Publisher</a></footer>''', 'https://news.publisher.test/story')
    assert business_website_links(page) == ['https://texasvaninteriors.com/']


def test_directory_resolution_uses_requested_state_and_resolves_named_businesses():
    from core.services.public_site_data import public_page, business_website_links, business_names_from_listing
    page = public_page('''<h1>Custom Van Builders Directory</h1><h2>Arizona</h2>
    <p>Desert Builder<br>100 Street, Arizona</p><a href="https://desert.test/">Official website</a>
    <h2>Texas</h2><p>Lone Star Vans<br>9805 Gray Blvd<br>Austin, TX 78758</p>
    <a href="https://lonestar.test/">Official website</a><h2>Utah</h2><p>Utah Builder</p>''', 'https://directory.test/builders')
    assert business_website_links(page, 'Texas') == ['https://lonestar.test/']
    assert business_names_from_listing(page, 'Texas') == ['Lone Star Vans']


def test_named_business_searches_share_the_run_query_and_credit_budget():
    from core.services.public_site_data import public_page
    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline), search_budget=4)
        engine.intent = SearchIntent('Van Upfitters / RV Builders', 'Texas')
        engine.is_cancelled = lambda: False
        page = public_page('<h1>Van conversion builders</h1><h2>Texas</h2><p>Lone Star Vans<br>Austin, TX 78758</p>', 'https://directory.test/builders')
        engine.fetch = AsyncMock(return_value=page)
        engine.search = AsyncMock(return_value=[{'url': 'https://lonestar.test/'}])
        result = await engine.resolve_business_sites([{'url': page['url'], 'title': 'Van conversion builders directory Texas'}], resolve_names=True)
        assert result == [{'url': 'https://lonestar.test/'}]
        assert 'Lone Star Vans' in engine.search.call_args.args[0]
        assert engine.scrape_stats['business_names_resolved'] == 1
    asyncio.run(run())


def test_generic_article_headings_never_become_business_name_queries():
    from core.services.public_site_data import public_page, business_names_from_listing
    page = public_page('<h1>Van Conversions Texas</h1><h2>Key Takeaways</h2><h3>Backed by</h3><p>Our Texas workshop</p>', 'https://builder.test/blog/guide')
    assert business_names_from_listing(page, 'Texas') == []


def test_whatsapp_is_only_reported_when_explicitly_published():
    from core.services.public_site_data import public_page
    page = public_page('<a href="https://wa.me/15128354409">WhatsApp</a><p>5128354409</p>', 'https://builder.test/')
    assert page['whatsapp_urls'] == ['https://wa.me/15128354409']
    assert public_page('<p>5128354409</p>', 'https://builder.test/')['whatsapp_urls'] == []


def test_public_team_card_has_a_name_role_and_source_without_guessing_an_email():
    from core.services.public_site_data import public_page
    markup = '<article class="team-member"><h3>Jane Smith</h3><p class="position">Founder</p></article>'
    page = public_page(markup, 'https://builder.test/about/')
    assert page['people'] == [{'name': 'Jane Smith', 'title': 'Founder', 'source_url': 'https://builder.test/about/', 'email': ''}]
    assert not public_page(markup, 'https://builder.test/blog/interview')['people']


def test_location_only_logo_does_not_hide_published_company_brand():
    from core.services.lead_search_engine import company_identity
    pages = [{'url': 'https://texastt.test/', 'html': '<img alt="Texas Logo"><footer>©2025 Texas Truck &amp; Trailer® – All rights reserved.</footer>'}]
    assert company_identity(pages, 'texastt.test', excluded_names=['Texas']) == 'Texas Truck & Trailer'


def test_vento_never_parses_profile_urls_or_handles_as_email_addresses():
    from core.services.vento.discovery import extract_emails
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    text = 'https://www.tiktok.com/@apple.girl.kait www.tiktok.com/@dog.mom Email: collabs@realpet.com'
    assert extract_emails(text) == ['collabs@realpet.com']
    assert not VentoLeadPipeline._normalize_email('//www.tiktok.com/@apple.girl.kait')


def test_creator_fit_requires_pet_niche_and_location_without_tour_destination():
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    assert VentoLeadPipeline._creator_fit({'evidence': 'Seattle, WA dog mom pet creator'}, 'Seattle, WA') == (True, True)
    assert VentoLeadPipeline._creator_fit({'evidence': 'Comedian on tour in Seattle, tickets for my dog story'}, 'Seattle, WA') == (False, False)
    assert VentoLeadPipeline._creator_fit({'evidence': 'Denver dog mom creator'}, 'Seattle, WA') == (False, True)


def test_vento_scrapes_several_contact_pages_and_retains_public_sources():
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    async def run():
        pipeline = VentoLeadPipeline(gemini_api_key='')
        pipeline._safe_public_url = AsyncMock(return_value=True)
        bodies = {
            'https://pets.test/': '<p>Pet grooming in Austin, TX 78758</p><a href="/contact">Contact</a><a href="/about">About</a>',
            'https://pets.test/contact': '<a href="mailto:paws@gmail.com">Email</a><a href="tel:+15128354409">Call</a>',
            'https://pets.test/about': '<a href="https://instagram.com/actualpets">Instagram</a><script>var unrelated="wrong@ads.test";</script>',
        }
        async def fetch(client, url):
            return (url, bodies[url]) if url in bodies else None
        pipeline._fetch_html = AsyncMock(side_effect=fetch)
        result = await pipeline._scrape_candidate_website('https://pets.test/')
        assert result['verified']
        assert result['emails'] == ['paws@gmail.com']
        assert len(result['urls']) == 3
        assert result['contact_sources'][0]['source_url'] == 'https://pets.test/contact'
        assert result['socials']['instagram'] == ['actualpets']
    asyncio.run(run())


def test_vento_redirect_is_validated_before_private_destination_is_requested():
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    async def run():
        pipeline = VentoLeadPipeline(gemini_api_key='')
        pipeline._safe_public_url = AsyncMock(side_effect=lambda url: '127.0.0.1' not in url)
        requested = []
        def respond(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/admin'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            assert await pipeline._fetch_html(client, 'https://pets.test/') is None
        assert requested == ['https://pets.test/']
    asyncio.run(run())


def test_vento_business_gate_rejects_unverified_site_or_wrong_location():
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    pipeline = VentoLeadPipeline(gemini_api_key='')
    base = {'business_name': 'Happy Paws', 'website': 'https://pets.test', 'evidence': 'Pet grooming'}
    for fields, expected in [({'official_site_verified': False}, 'official_site_unavailable'), ({'location_match': False}, 'location_unconfirmed'), ({'industry_match': False}, 'industry_mismatch')]:
        accepted, rejected = pipeline._quality_gate([{**base, **fields}], 'pet_grooming')
        assert not accepted and rejected[0]['rejection_reason'] == expected


def test_production_vento_business_cannot_pass_on_a_snippet_without_an_official_site():
    from core.services.vento.vento_lead_pipeline import VentoLeadPipeline
    pipeline = VentoLeadPipeline(gemini_api_key='')
    pipeline._target_location = 'Seattle, WA'
    usable, rejected = pipeline._quality_gate([{'business_name': 'Happy Paws', 'email': 'hello@realpet.com', 'evidence': 'Seattle pet shop'}], 'pet_shops')
    assert not usable and rejected[0]['rejection_reason'] == 'official_site_unavailable'


def test_specialized_api_count_limits_are_explicit():
    from api.routes.lead_search import SearchRequest
    request = {'industry': 'Van Upfitters', 'location': 'Texas', 'target_count': 100, 'request_key': 'specialized-search-request'}
    assert SearchRequest(**request, mode='velit').target_count == 100
    with pytest.raises(ValueError):
        SearchRequest(**request, mode='generic')


def test_velit_reuses_incremental_engine_and_retains_scheduler_partial_results(monkeypatch):
    from core.services.velit.velit_lead_pipeline import VelitLeadPipeline
    async def fake_run(engine, intent, **kwargs):
        result = {'leads': [{'company_name': 'Actual Builder'}], 'metadata': {'stage': 'partial'}}
        await kwargs['on_progress'](result)
        return result
    monkeypatch.setattr(LeadSearchEngine, 'run', fake_run)
    pipeline = VelitLeadPipeline()
    result = asyncio.run(pipeline.run(industry='Van Upfitters', location='Texas', target_count=15))
    assert result['metadata']['mode'] == 'velit'
    assert pipeline.get_partial_result()['leads'][0]['company_name'] == 'Actual Builder'


def test_stalled_search_preserves_completed_lead_and_stops_slow_peers():
    from types import SimpleNamespace
    async def run():
        extractor = SimpleNamespace(tavily=SimpleNamespace(search=AsyncMock(return_value={'results': [{'url': 'https://fast.test/'}, {'url': 'https://slow.test/'}]})), _is_directory_or_noise_url=lambda _: False)
        engine = LeadSearchEngine(extractor, max_seconds=10)
        engine.idle_seconds = .2
        async def enrich(item):
            if 'slow' in item['url']:
                await asyncio.sleep(5)
            return {'company_name': 'Actual Builder', 'company_website': item['url'], 'usable': True}
        engine.enrich = enrich
        result = await engine.run(SearchIntent('Van Upfitters', 'Texas', 2))
        assert len(result['leads']) == 1
        assert result['metadata']['stop_reason'] == 'no_recent_verified_businesses'
        assert result['metadata']['elapsed_seconds'] < 2
    asyncio.run(run())
