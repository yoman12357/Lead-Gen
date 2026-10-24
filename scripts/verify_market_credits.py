"""Run selected markets sequentially with before/after provider usage snapshots."""
import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from scripts.verify_pipeline_matrix import audit

MARKETS = ['dentists-sydney', 'lawyers-toronto', 'architects-bengaluru', 'solar-austin']


async def usage_snapshot():
    result = {'at': datetime.now(timezone.utc).isoformat()}
    async with httpx.AsyncClient(timeout=20) as client:
        for provider in ('tavily', 'hunter'):
            key = os.getenv(provider.upper() + '_API_KEY')
            if not key:
                result[provider] = {'status': 'unconfigured'}
                continue
            try:
                if provider == 'tavily':
                    response = await client.get('https://api.tavily.com/usage', headers={'Authorization': 'Bearer ' + key})
                else:
                    response = await client.get('https://api.hunter.io/v2/usage', params={'api_key': key})
                if response.status_code != 200:
                    result[provider] = {'status': 'unavailable', 'http_status': response.status_code}
                    continue
                data = response.json()
                # Whitelist quota fields only, excluding account identity/secrets.
                result[provider] = ({'status': 'ok', 'key': data.get('key', {}), 'account': data.get('account', {})}
                    if provider == 'tavily' else {'status': 'ok', 'requests': data.get('data', {}).get('requests', {})})
            except Exception as exc:
                result[provider] = {'status': 'unavailable', 'error_type': type(exc).__name__}
    return result


def deltas(before, after):
    result = {}
    for provider in ('tavily', 'hunter'):
        a, b = before[provider], after[provider]
        if a['status'] != 'ok' or b['status'] != 'ok':
            result[provider] = None
            continue
        if provider == 'tavily':
            result[provider] = {key: b['key'][key] - value for key, value in a['key'].items()
                if key in b['key'] and (key == 'usage' or key.endswith('_usage')) and type(value) in (int, float)}
        else:
            result[provider] = {key: value['used'] - a['requests'][key]['used'] for key, value in b['requests'].items()
                if key in a['requests'] and 'used' in value and 'used' in a['requests'][key]}
    return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='exports/market-10')
    parser.add_argument('--base-url', default='http://127.0.0.1:8001')
    parser.add_argument('--case', action='append', choices=MARKETS)
    args = parser.parse_args()
    load_dotenv()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=25,
            headers={'X-API-Key': os.getenv('AGENTIC_CORE_API_KEY', '')}) as client:
        for case in (args.case or MARKETS):
            # Never silently repeat a paid run when rebuilding reports.
            if (output / (case + '.json')).exists():
                raise RuntimeError('Existing run: choose a new output or replay the saved results: ' + case)
            before = await usage_snapshot()
            (output / (case + '-usage-before.json')).write_text(json.dumps(before, indent=2), encoding='utf-8')
            summary, _ = await audit(client, case, 10, output)
            after = await usage_snapshot()
            job = json.loads((output / (case + '.json')).read_text(encoding='utf-8'))
            report = {'case': case, 'job_id': job['id'], 'summary': summary, 'before': before, 'after': after,
                'account_delta': deltas(before, after), 'request_usage': job['result']['metadata'].get('provider_usage'),
                'attribution_note': 'Sequential local audit runs. Account deltas can include other activity on the same provider account.'}
            (output / (case + '-credits.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({'case': case, 'account_delta': report['account_delta'], 'request_usage': report['request_usage']}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
