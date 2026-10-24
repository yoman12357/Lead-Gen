"""Optional real-browser check: LEAD_TEST_BROWSER=1 pytest this file."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import time
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import httpx
import pytest

from core.services.lead_search_engine import LeadSearchEngine
from core.services.lead_search_policy import SearchIntent
from core.services.production_lead_pipeline import ProductionLeadPipeline


@pytest.mark.skipif(os.getenv('LEAD_TEST_BROWSER') != '1', reason='Opt-in installed browser integration')
def test_javascript_shell_becomes_sourced_company_data(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == '/' else 404)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            if self.path == '/':
                self.wfile.write(b'''<title>Actual Builder</title><main id="app">Loading</main><script>
                document.getElementById('app').innerHTML = '<h1>Actual Builder</h1><p>Custom van conversions built by our team. We build camper vans with custom interiors, storage, seating and full electrical systems for adventures and work.</p><address>9805 Gray Blvd, Austin, TX 78758</address><a href="mailto:texas@builder.test">Email</a><a href="tel:+15128354409">Call</a>';
                </script>''')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv('LEAD_RENDER_JS', 'true')
    monkeypatch.setenv('LEAD_BROWSER_CHANNEL', 'msedge' if os.name == 'nt' else '')

    async def run():
        engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
        engine.intent = SearchIntent('Van Upfitters / RV Builders', 'Texas')
        engine.started = time.monotonic()
        engine.is_cancelled = lambda: False
        # Only this explicitly controlled loopback fixture is authorized in test.
        engine.public_url = AsyncMock(side_effect=lambda url: urlparse(url).hostname == '127.0.0.1')
        engine.check_email = AsyncMock(return_value={'status': 'unconfirmed', 'mx_found': True, 'smtp_verified': False})
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            engine.client = client
            lead = await engine.enrich({'url': f'http://127.0.0.1:{server.server_port}/', 'title': 'Actual Builder'})
        assert lead and lead['contact_phone'] == '+15128354409'
        assert engine.scrape_stats['rendered_pages'] == 1
        assert any(source['retrieval_method'] == 'rendered' for source in lead['source_details'])
        assert not lead['email_smtp_verified']

    try:
        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
