"""Local browser regression check for lead normalization and the real Excel export."""
import json
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright


def main():
    fixture = {
        "company_name": "Sample Software", "company_website": "https://sample.test",
        "qualification_score": 7, "quality_score": 55, "quality_status": "Needs_Review",
        "phone_confidence": 98, "confidence": "medium", "contact_person_name": "",
        "contact_email": "info@sample.test", "contact_phone": "+919654675467",
        "company_linkedin_url": "https://linkedin.com/company/sample", "linkedin_url": "",
        "location": "Delhi", "location_match": True, "city": "Delhi", "state": "", "zip_code": "",
        "source": "official_website", "usable": True, "rejected": False,
        "acceptance_reason": "Sample Software: Needs_Review. Quality score: 55/100.",
        "verification_status": "risky", "verifying": False,
    }
    out = Path("exports/quality-audit")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", lambda route: route.fulfill(json={"leads": [], "agents": [], "workflows": []}))
        page.goto("http://127.0.0.1:8000/leads", wait_until="networkidle")
        result = page.evaluate("lead => normalizeLead(lead)", fixture)
        for key in ("quality_score", "confidence", "contact_email", "contact_phone", "location", "city", "source", "contact_person_name", "linkedin_url"):
            assert result[key] == fixture[key], (key, result.get(key))
        with page.expect_download() as download:
            page.evaluate("lead => exportLeadsAsCrmXlsx([normalizeLead(lead)], 'ui-export-regression.xlsx')", fixture)
        path = out / "ui-export-regression.xlsx"
        download.value.save_as(path)
        rows = list(load_workbook(path).active.values)
        record = dict(zip(rows[0], rows[1]))
        assert record["Contact Person"] is None
        assert str(record["Quality Score"]) == "55"
        assert "Verifying" not in record
        assert record["City"] == "Delhi"
        assert record["Company Name"] == "Sample Software"
        assert not errors, errors
        print(json.dumps({"browser": "passed", "normalization": "passed", "excel_export": "passed", "console_errors": errors}))
        browser.close()


if __name__ == "__main__":
    main()
