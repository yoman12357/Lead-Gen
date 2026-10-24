import asyncio

import httpx
import pytest

from api.routes.leads import _verify_export_lead, _has_verification
from core.services.lead_quality_gate import apply_quality_gate, normalize_and_score_lead
from core.services.lead_quality_service import score_lead
from core.services.production_lead_pipeline import ProductionLeadPipeline, VerifiedTarget
from core.utils.phone_quality import extract_phone_candidates, normalize_phone_candidate, phone_summary_from_text, prefer_phone_region


@pytest.mark.parametrize("raw,region,expected", [
    ("+91 96 5467 5467", "US", "+919654675467"),
    ("9654675467", "IN", "+919654675467"),
    ("+44 20 7946 0958", "US", "+442079460958"),
    ("020 7946 0958", "GB", "+442079460958"),
    ("+1 917 905 4240", "IN", "+19179054240"),
    ("+91 11 4756 7702", "IN", "+911147567702"),
])
def test_international_phone_prefixes(raw, region, expected):
    assert normalize_phone_candidate(raw, region=region)["e164"] == expected


def test_nethues_multiple_offices_never_invent_us_prefix():
    phones = extract_phone_candidates("India Sales +91 96 5467 5467. USA Phone +1 917 905 4240.", region="IN")
    assert {p["e164"] for p in phones} == {"+919654675467", "+19179054240"}
    assert normalize_phone_candidate("+19654675467") is None


def test_multi_office_phones_prefer_requested_country():
    summary = phone_summary_from_text("USA Phone +1 917 905 4240. India Sales +91 9654675467.", region="IN")
    assert prefer_phone_region(summary, "IN")["contact_phone"] == "+919654675467"


def test_perfect_looking_unverified_row_is_not_strong():
    row = company(contact_person_name="Aryan Bokolia", contact_person_title="Founder",
                  linkedin_url="https://linkedin.com/in/aryan", contact_page="https://nethues.com/contact")
    assert score_lead(row)["quality_status"] == "Needs_Review"
    verified = score_lead(row, {"status": "valid", "smtp_verified": True})
    assert verified["quality_status"] == "Strong"
    assert verified["quality_score"] <= 100


def company(**kwargs):
    return {"company_name": "Nethues", "company_website": "https://nethues.com",
            "industry": "SaaS Development", "location": "Delhi", "location_match": True,
            "contact_email": "info@nethues.com", "contact_phone": "+919654675467",
            "value_proposition": "SaaS development services", **kwargs}


def test_timeout_cannot_produce_strong_lead_or_inconsistent_score():
    lead = company(email_verification={"status": "risky", "smtp_verified": False, "mx_found": True})
    result = normalize_and_score_lead(lead)
    assert result["quality_status"] == "Needs_Review"
    assert result["quality_score"] <= 69
    assert f"{result['quality_score']}/100" in result["acceptance_reason"]
    assert result["contact_email"] == "info@nethues.com"
    assert result["contact_phone"] == "+919654675467"


def test_website_alone_is_not_a_contactable_lead():
    result = score_lead(company(contact_email="", contact_phone="", contact_page="https://nethues.com"))
    assert result["rejected"] is True


def test_website_status_is_not_email_verification():
    assert not _has_verification(company(verification_status="valid", site_status="reachable"))


def test_export_without_email_finishes_and_rescores():
    result = asyncio.run(_verify_export_lead(
        company(contact_email="", contact_phone="", verifying=True, quality_score=97),
        skip_already_verified=False, semaphore=asyncio.Semaphore(1),
    ))
    assert result["verifying"] is False
    assert result["rejected"] is True
    assert result["verification_status"] == "no_email_found"
    assert "97/100" not in result["acceptance_reason"]


def test_delhi_does_not_get_miami_city():
    found = ProductionLeadPipeline._extract_city_state(text="New Delhi 110085. Miami, FL 33130", location="Delhi")
    assert found["city"] == "Delhi"
    assert found["state"] != "FL"


def test_saas_products_and_services_are_distinct():
    match = ProductionLeadPipeline._matches_target_industry
    assert not match("We are a SaaS development agency providing outsourcing services.", "SaaS")
    assert match("Our SaaS software has a free trial and pricing plans.", "SaaS")
    assert match("We offer SaaS development services.", "SaaS Development")
    assert not ProductionLeadPipeline._matches_target_location("Miami Florida", "Delhi")


def test_listicles_and_professional_bodies_are_not_prospects():
    assert ProductionLeadPipeline._is_directory_or_noise_url("https://mocal.ai/en/top-10-marketing-agencies-mumbai")
    assert not ProductionLeadPipeline._matches_target_industry("The professional body for chartered accountants. Membership body", "Accountants")
    assert ProductionLeadPipeline._matches_target_industry("Our London office provides accountancy services and tax returns.", "Accountants")


def test_sentence_fragments_are_not_people():
    assert not ProductionLeadPipeline._looks_like_person_name("depth interviews with business")
    assert not ProductionLeadPipeline._looks_like_person_name("businesses supported From")
    assert ProductionLeadPipeline._looks_like_person_name("Aryan Bokolia")


def test_contactless_best_candidate_does_not_displace_good_candidate():
    rows, _ = apply_quality_gate([company(contact_email="", contact_phone="", quality_score=99), company()])
    assert len(rows) == 1
    assert rows[0]["contact_email"]


def test_soft_404_recovers_homepage():
    async def run():
        calls = []
        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200, text="<h1>Page not found</h1>" if request.url.path != "/" else "<h1>Actual business</h1>")
        pipeline = ProductionLeadPipeline.__new__(ProductionLeadPipeline)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            target = await pipeline._verify_one(client, {"url": "https://company.test/old"})
        assert target.url == "https://company.test/"
        assert calls == ["/old", "/"]
    asyncio.run(run())


def test_contact_scraper_follows_real_html_contact_link():
    async def run():
        pipeline = ProductionLeadPipeline.__new__(ProductionLeadPipeline)
        pipeline._target_location = "Delhi"
        def handler(request):
            if request.url.path == "/":
                return httpx.Response(200, text='<a href="/contact-us.html">Contact</a>')
            if request.url.path == "/contact-us.html":
                return httpx.Response(200, text='Delhi office <a href="mailto:info@company.test">Email</a> Phone +91 9654675467')
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            signals = await pipeline._scrape_contact_pages_for_target(client, VerifiedTarget(url="https://company.test/", title="Company", content="", status_code=200))
        assert "info@company.test" in signals["emails"]
        assert "+919654675467" in signals["phones"]
    asyncio.run(run())


def test_long_landing_page_does_not_hide_contact_footer_evidence():
    async def run():
        pipeline = ProductionLeadPipeline.__new__(ProductionLeadPipeline)
        row = await pipeline._score_one({
            "url": "https://nethues.com/", "title": "Nethues SaaS Development",
            "company_name": "Nethues", "content": "SaaS development services. " + "Software services. " * 2200,
            "contact_signals": {"text": "Contact Nethues in New Delhi. Email info@nethues.com. Phone +91 9654675467.",
                "emails": ["info@nethues.com"], "phones": ["+919654675467"]},
        }, industry="SaaS Development", location="Delhi", use_gemini=False,
            gemini_data={"contact_person_name": "Invented Person", "contact_email": "fake@nethues.com"})
        assert row["location_match"] is True
        assert row["contact_person_name"] == ""
        assert row["contact_email"] == "info@nethues.com"
        assert row["contact_phone"] == "+919654675467"
        assert not row["rejected"]
    asyncio.run(run())
