"""Explicit live pipeline audit; configured providers may consume credits."""
import argparse
import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
import httpx

load_dotenv()
logging.disable(logging.CRITICAL)

from core.services.production_lead_pipeline import ProductionLeadPipeline


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry", default="Digital Marketing")
    parser.add_argument("--location", default="Mumbai")
    parser.add_argument("--count", type=int, default=15)
    parser.add_argument("--api", action="store_true", help="Exercise the running localhost API and persisted job instead of calling the engine directly")
    args = parser.parse_args()
    out = Path("exports/platform-audit")
    out.mkdir(parents=True, exist_ok=True)
    last_count = -1
    async def progress(result):
        nonlocal last_count
        meta = result["metadata"]
        count = len(result["leads"])
        if count != last_count or meta["stage"] in {"expanding", "partial", "completed"}:
            print(json.dumps({"stage": meta["stage"], "leads": count, "checked": meta["checked_targets"], "queries": len(meta["queries_used"]), "seconds": meta["elapsed_seconds"]}), flush=True)
            last_count = count
    if args.api:
        headers = {'X-API-Key': os.getenv('AGENTIC_CORE_API_KEY', '')}
        async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', headers=headers, timeout=20) as client:
            response = await client.post('/api/lead-searches', json={'industry': args.industry, 'location': args.location, 'target_count': args.count, 'request_key': str(uuid.uuid4())})
            response.raise_for_status()
            job = response.json()
            async with asyncio.timeout(420):
                while job['status'] not in {'completed', 'partial', 'cancelled', 'failed', 'interrupted'}:
                    await asyncio.sleep(2)
                    response = await client.get('/api/lead-searches/' + job['id'])
                    response.raise_for_status()
                    job = response.json()
                    if 'checked_targets' in job['result'].get('metadata', {}):
                        await progress(job['result'])
            result = job['result']
            result['search_id'] = job['id']
    else:
        result = await ProductionLeadPipeline().run(industry=args.industry, location=args.location, target_count=args.count, on_progress=progress)
    filename = (args.industry + "-" + args.location).lower().replace(" ", "-").replace("/", "-")
    (out / (filename + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"metadata": result["metadata"], "leads": [{key: lead.get(key) for key in ("company_name", "company_website", "contact_email", "contact_phone", "location", "quality_score", "email_mx_found")} for lead in result["leads"]]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
