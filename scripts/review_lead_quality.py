"""Capture fresh official-source evidence for a saved lead-search matrix.

This audit checks published contacts independently of the pipeline's scores.
It does not probe mailboxes, send messages, or silently approve company fit.
"""
import argparse
import asyncio
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

import httpx
import phonenumbers

from core.services.lead_search_engine import LeadSearchEngine
from core.utils.phone_quality import phone_region_for_location
from core.services.lead_search_policy import domain_key
from core.services.production_lead_pipeline import ProductionLeadPipeline


class EvidenceHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links, self.logos, self.headings, self.addresses = [], [], [], [], []
        self.hidden = 0
        self.heading = None
        self.address = None
        self.title = ''
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'title':
            self.in_title = True
        if tag in {'h1', 'h2'}:
            self.heading = []
        if tag == 'address':
            self.address = []
        if tag in {'div', 'p', 'li', 'footer', 'address', 'br', 'h1', 'h2'}:
            self.parts.append('\n')
        if tag == 'a' and attrs.get('href'):
            self.links.append(html.unescape(unquote(attrs['href'])))
        if tag == 'img' and attrs.get('alt') and re.search(r'logo|brand', str(attrs), re.I):
            self.logos.append(attrs['alt'])

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag == 'title':
            self.in_title = False
        if tag in {'h1', 'h2'} and self.heading is not None:
            self.headings.append(' '.join(self.heading))
            self.heading = None
        if tag == 'address' and self.address is not None:
            self.addresses.append(' '.join(self.address))
            self.address = None
        if tag in {'div', 'p', 'li', 'footer', 'address', 'br', 'h1', 'h2'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if self.hidden:
            return
        self.parts.append(data)
        if self.in_title:
            self.title += data
        if self.heading is not None:
            self.heading.append(data.strip())
        if self.address is not None:
            self.address.append(data.strip())

    @property
    def text(self):
        return '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())


def decoded_cf_emails(markup):
    values = []
    for value in re.findall(r'data-cfemail=["\']([a-f0-9]+)', markup, re.I):
        try:
            blob = bytes.fromhex(value)
            values.append(''.join(chr(char ^ blob[0]) for char in blob[1:]))
        except (ValueError, IndexError):
            pass
    return values


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    sources = root / 'sources'
    sources.mkdir(exist_ok=True)
    engine = LeadSearchEngine(object.__new__(ProductionLeadPipeline))
    slots = asyncio.Semaphore(5)
    reports = []
    cases = []
    for path in Path(args.input).glob('*.json'):
        if args.case and path.stem not in args.case:
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        if 'result' in data and 'leads' in data['result']:
            cases.extend((path.stem, index + 1, lead) for index, lead in enumerate(data['result']['leads']))

    async def review(case, index, lead):
        async with slots:
            candidates = [lead.get('field_sources', {}).get('contact_email', ''), lead.get('location_source_url', ''),
                          lead.get('contact_page', ''), lead['company_website']] + [item['url'] for item in lead['source_details']]
            urls, seen = [], set()
            for url in candidates:
                if url.startswith(('https://', 'http://')) and url.rstrip('/') not in seen:
                    seen.add(url.rstrip('/'))
                    urls.append(url)
            # Recheck the most relevant sources without bursting six concurrent
            # requests against one company or downloading duplicate home URLs.
            pages = [await engine.fetch(url) for url in urls[:4]]
            evidence = []
            all_text, published_emails, published_phones = [], set(), set()
            region = phone_region_for_location(lead.get('location', case))
            for page in pages:
                if not page or domain_key(page['url']) != domain_key(lead['company_website']):
                    continue
                parsed = EvidenceHTML()
                parsed.feed(page['html'])
                text = parsed.text
                key = hashlib.sha256(page['url'].encode()).hexdigest()[:12]
                prefix = sources / (domain_key(page['url']) + '-' + key)
                Path(str(prefix) + '.html').write_text(page['html'], encoding='utf-8')
                Path(str(prefix) + '.txt').write_text(text, encoding='utf-8')
                mailtos = [link[7:].split('?', 1)[0].strip() for link in parsed.links if link.lower().startswith('mailto:')]
                published_emails.update(re.findall(r'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}', text.lower()))
                published_emails.update(value.lower() for value in mailtos + decoded_cf_emails(page['html']))
                tels = [link[4:].split('?', 1)[0].strip() for link in parsed.links if link.lower().startswith('tel:')]
                number_text = text + '\n' + '\n'.join(tels)
                for match in phonenumbers.PhoneNumberMatcher(number_text, region):
                    if phonenumbers.is_valid_number(match.number):
                        published_phones.add(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164))
                place = r'\b(?:' + '|'.join(re.escape(value.strip()) for value in lead.get('location', '').split(',') if value.strip()) + r')\b'
                if 'bengaluru' in lead.get('location', '').casefold():
                    place = r'\b(?:Bengaluru|Bangalore)\b'
                windows = [text[max(0, m.start()-100):m.end()+180] for m in re.finditer(place, text, re.I)]
                # Prioritize address-looking windows for human review, retaining
                # complete source snapshots so a heuristic is never the verdict.
                postal = {'GB': r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',
                    'IN': r'\b\d{6}\b', 'AU': r'\b\d{4}\b',
                    'CA': r'\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b', 'US': r'\b\d{5}\b'}.get(region, r'\b\d{4,6}\b')
                address_windows = [value for value in windows if re.search(postal, value, re.I)]
                evidence.append({'url': page['url'], 'title': parsed.title.strip(), 'headings': parsed.headings[:6],
                    'logos': parsed.logos[:8], 'addresses': parsed.addresses,
                    'location_windows': list(dict.fromkeys(address_windows + windows))[:8],
                    'mailto': mailtos, 'tel': tels, 'text_file': str(prefix) + '.txt'})
                all_text.append(text)
            email = lead.get('contact_email', '').lower()
            phone = lead.get('contact_phone', '')
            flags = []
            if not evidence:
                flags.append('sources_unavailable_on_recheck')
            if email and email not in published_emails:
                flags.append('email_not_reproduced_on_fresh_sources')
            if phone and phone not in published_phones:
                flags.append('phone_not_reproduced_in_visible_text_or_tel_links')
            if lead.get('location_basis') != 'address':
                flags.append('location_requires_manual_presence_review')
            if re.fullmatch(r'(?:chartered )?accountants?|reliable accounting services|find an accountant|regulated professions register', lead['company_name'], re.I):
                flags.append('generic_or_noncompany_identity')
            report = {'case': case, 'index': index, 'company': lead['company_name'], 'website': lead['company_website'],
                'email': email, 'phone': phone, 'email_reproduced': email in published_emails if email else None,
                'phone_reproduced': phone in published_phones if phone else None, 'published_phones': sorted(published_phones),
                'flags': flags, 'sources': evidence, 'manual_quality_verdict': 'pending'}
            (root / f'{case}-{index:02}.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
            reports.append(report)
            print(json.dumps({'case': case, 'index': index, 'company': lead['company_name'], 'flags': flags}), flush=True)

    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=4), follow_redirects=False,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}) as client:
        engine.client = client
        await asyncio.gather(*(review(*case) for case in cases))
    summary = [{'case': r['case'], 'index': r['index'], 'company': r['company'], 'website': r['website'],
        'flags': r['flags'], 'email_reproduced': r['email_reproduced'], 'phone_reproduced': r['phone_reproduced']} for r in sorted(reports, key=lambda x: (x['case'], x['index']))]
    (root / 'review-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps({'records_rechecked': len(reports), 'with_flags': sum(bool(r['flags']) for r in reports),
                      'human_review_required': True, 'output': str(root)}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
