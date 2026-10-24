"""Browser contract test with synthetic jobs; does not spend provider credits."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright, expect


def main():
    output = Path('exports/platform-audit')
    output.mkdir(parents=True, exist_ok=True)
    leads = [{
        'company_name': f'Example Agency {i}', 'company_website': f'https://agency{i}.test',
        'industry': 'Digital Marketing', 'location': 'Mumbai', 'location_match': True,
        'contact_email': f'hello@agency{i}.test', 'contact_phone': '+919819988640',
        'contact_person_name': '', 'quality_score': 69, 'usable': True, 'rejected': False,
        'email_smtp_verified': False, 'email_mx_found': True, 'verification_status': 'unconfirmed',
        'industry_evidence': 'Digital marketing agency.', 'location_evidence': 'Office: Mumbai 400020',
        'source_details': [{'url': f'https://agency{i}.test/contact'}, {'url': 'javascript:alert(1)'}],
        'checked_at': '2026-10-22T10:00:00Z',
    } for i in range(15)]
    jobs, polls, errors, writes, workflow_requests = {}, {}, [], [], []
    request_count = 0

    def route_api(route):
        nonlocal request_count
        path = urlparse(route.request.url).path
        method = route.request.method
        if method == 'POST':
            writes.append(path)
        if path == '/api/lead-searches' and method == 'POST':
            request_count += 1
            request = route.request.post_data_json
            job_id = f'synthetic-search-{request_count}'
            jobs[job_id] = {'id': job_id, 'request': request, 'status': 'queued', 'result': {'leads': [], 'metadata': {'shortfall': 15}, 'steps': []}}
            polls[job_id] = 0
            route.fulfill(status=202, json=jobs[job_id])
        elif path == '/api/workflow/run' and method == 'POST':
            request = route.request.post_data_json
            workflow_requests.append(request)
            route.fulfill(json={'success': True, 'workflow_id': request['workflow_id'],
                'state': {'outputs': {'enriched_leads': leads[:1]}},
                'metadata': {'completed': True, 'stage': 'completed'}})
        elif path.startswith('/api/lead-searches/'):
            job_id = path.split('/')[3]
            job = jobs[job_id]
            if path.endswith('/cancel'):
                job['status'] = 'cancelled'
                job['result']['metadata'].update(stop_reason='cancelled', shortfall=14)
            elif job['status'] not in {'completed', 'cancelled'}:
                polls[job_id] += 1
                count = (7 if polls[job_id] == 1 else 15) if job_id.endswith('-1') else 1
                job['status'] = 'completed' if count == 15 or job['request'].get('mode') == 'velit' else 'enriching'
                job['result'] = {'leads': leads[:count], 'steps': [{'message': 'Checking official websites.'}], 'metadata': {
                    'requested_count': 15, 'returned_count': count, 'shortfall': 15-count,
                    'checked_targets': 20, 'queries_used': ['Synthetic search'], 'elapsed_seconds': 42,
                    'stop_reason': 'target_reached' if count == 15 else '', 'rejection_reasons': {'directory_or_article': 4},
                }}
            route.fulfill(json=job)
        elif path == '/api/vento/batch':
            route.fulfill(json={'leads': [{'business_name': 'Sample Pet Shop', 'website': 'https://pets.test', 'email': 'hello@pets.test', 'phone': '+12065551212', 'location': 'Seattle, WA', 'category': 'pet_shops', 'relevance_score': 8}],
                'category': 'pet_shops', 'shortfall': 0, 'metrics': {'usable': 1}, 'storage_status': 'not_configured'})
        else:
            route.fulfill(json={'leads': [], 'agents': [], 'workflows': []})

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(accept_downloads=True, viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/**', route_api)
        page.goto(os.getenv('LEAD_UI_BASE_URL', 'http://127.0.0.1:8000') + '/leads', wait_until='networkidle')
        page.locator('#industry-input').fill('Digital Marketing')
        page.locator('#location-input').fill('Mumbai')
        page.locator('#lead-count-input').fill('15')
        page.locator('#start-btn').click()
        expect(page.locator('.client-lead-row')).to_have_count(15, timeout=15000)
        expect(page.locator('#search-status-title')).to_have_text('15 company leads ready.')
        assert page.evaluate('verifiedCount.textContent') == '0'
        assert page.locator('a[href^="javascript:"]').count() == 0
        with page.expect_download() as download:
            page.locator('#export-xlsx-btn').click()
        xlsx = output / 'client-flow-export.xlsx'
        download.value.save_as(xlsx)
        rows = list(load_workbook(xlsx).active.values)
        assert len(rows) == 16, len(rows)
        assert 'Company Name' in rows[0]
        assert '/api/leads/verify' not in writes
        page.reload(wait_until='networkidle')
        expect(page.locator('.client-lead-row')).to_have_count(15)
        page.screenshot(path=str(output / 'client-desktop.png'), full_page=True)
        for width in (375, 768, 1024, 1440):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2'), width
        page.set_viewport_size({'width': 375, 'height': 812})
        page.screenshot(path=str(output / 'client-mobile.png'), full_page=True)
        page.locator('#start-btn').click()
        expect(page.locator('.client-lead-row')).to_have_count(1)
        page.locator('#cancel-search').click()
        expect(page.locator('#search-status-copy')).to_contain_text('Search stopped')
        expect(page.locator('#start-btn')).to_be_enabled()
        page.reload(wait_until='networkidle')
        expect(page.locator('.client-lead-row')).to_have_count(1)
        expect(page.locator('#search-status-copy')).to_contain_text('Search stopped')
        assert writes.count('/api/lead-searches') == 2, writes
        assert '/api/workflow/run' not in writes
        # Keyboard and click submissions must select the same pipeline.
        page.locator('#location-input').press('Enter')
        expect(page.locator('#cancel-search')).to_be_visible()
        page.wait_for_function('state.leads.length === 1')
        page.locator('#cancel-search').click()
        expect(page.locator('#start-btn')).to_be_enabled()
        assert writes.count('/api/lead-searches') == 3, writes
        page.evaluate("setMode('velit')")
        assert page.locator('#lead-count-input').get_attribute('max') == '100'
        page.locator('#start-btn').click()
        page.wait_for_function('!state.running && state.leads.length === 1')
        assert writes.count('/api/lead-searches') == 4, writes
        assert list(jobs.values())[-1]['request']['mode'] == 'velit'
        page.locator('#location-input').press('Enter')
        page.wait_for_function('!state.running && state.leads.length === 1')
        assert writes.count('/api/lead-searches') == 5, writes
        assert not workflow_requests, writes
        page.reload(wait_until='networkidle')
        page.wait_for_function("state.mode === 'velit' && state.leads.length === 1")
        page.evaluate("setMode('vento')")
        assert page.locator('#lead-count-input').get_attribute('max') == '200'
        expect(page.locator('.search-status-panel')).to_be_hidden()
        page.locator('#vento-category').select_option('pet_shops')
        page.locator('#location-input').fill('Seattle, WA')
        page.locator('#lead-count-input').fill('1')
        page.locator('#start-btn').click()
        page.wait_for_function("!state.running && state.leads.length === 1 && state.leads[0].company_name === 'Sample Pet Shop'")
        assert '/api/vento/batch' in writes, writes
        assert not errors, errors
        browser.close()
    print(json.dumps({'jobs': 'passed', 'refresh': 'passed', 'cancel': 'passed', 'xlsx_rows': 15,
        'responsive': 'passed', 'click_enter_routing': 'passed', 'velit_saved_jobs': 'passed', 'vento_tab': 'passed', 'page_errors': errors}))


if __name__ == '__main__':
    main()
