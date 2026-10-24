"""Public company data from HTML and business-owned Schema.org records.

Executable scripts, article authors and other organizations' records are not
contact evidence. Every extracted record retains its source and office context.
"""
from __future__ import annotations

import html
import json
import re
from urllib.parse import unquote, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from core.services.lead_search_policy import domain_key, is_listing_source, is_editorial_source

BUSINESS_TYPES = {'Organization', 'LocalBusiness', 'Corporation', 'ProfessionalService',
    'AccountingService', 'Dentist', 'MedicalBusiness', 'MedicalClinic', 'LegalService',
    'Attorney', 'HomeAndConstructionBusiness', 'Electrician', 'Store', 'PetStore',
    'AutomotiveBusiness', 'AutoDealer', 'AnimalShelter', 'VeterinaryCare', 'OnlineStore'}
POSTAL = re.compile(r'\b\d{5,6}(?:-\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b|\b[A-Z]\d[A-Z]\s*\d[A-Z]\d\b', re.I)
CONTACT_PATH = re.compile(r'contact|about|location|team|office|enquir|get-in-touch|reach|staff|leadership|our-story', re.I)


def values(value):
    return value if isinstance(value, list) else [value] if value else []


def business_records(markup: str, url: str) -> list[dict]:
    soup = BeautifulSoup(markup, 'html.parser')
    result = []
    for script in soup.find_all('script', type=re.compile(r'^application/ld\+json$', re.I))[:30]:
        try:
            queue = values(json.loads(script.string or script.get_text()))
        except (ValueError, TypeError, RecursionError):
            continue
        processed = 0
        while queue and processed < 150:
            node = queue.pop(0)
            processed += 1
            if not isinstance(node, dict):
                continue
            queue.extend(values(node.get('@graph'))[:100])
            types = {str(t).rsplit('/', 1)[-1] for t in values(node.get('@type'))}
            if not types & BUSINESS_TYPES:
                continue
            identity_url = node.get('url') or str(node.get('@id') or '').split('#')[0]
            if isinstance(identity_url, str) and identity_url and domain_key(urljoin(url, identity_url)) != domain_key(url):
                continue
            result.append(node)
            # Only explicit branches of the site's organization may contribute.
            queue.extend(values(node.get('department')) + values(node.get('subOrganization')))
    return result


def address_text(address) -> str:
    if isinstance(address, str):
        return address[:500]
    if not isinstance(address, dict):
        return ''
    parts = [address.get(key) for key in ('streetAddress', 'addressLocality', 'addressRegion', 'postalCode', 'addressCountry')]
    return ', '.join(str(part.get('name', '') if isinstance(part, dict) else part) for part in parts if part)


def public_page(markup: str, url: str) -> dict:
    """Add readable business data without interpreting arbitrary script contents."""
    records = business_records(markup, url)
    supplements, addresses, people = [], [], []
    for record in records:
        own_addresses = values(record.get('address'))
        for address in own_addresses:
            if isinstance(address, dict) and address.get('streetAddress'):
                addresses.append({**address, 'source_url': url})
        context = '\n'.join(address_text(address) for address in own_addresses)
        contacts = [record] + [item for item in values(record.get('contactPoint')) if isinstance(item, dict)]
        for contact in contacts:
            lines = ['<section>', '<address>' + html.escape(context) + '</address>']
            for key, scheme in [('email', 'mailto'), ('telephone', 'tel')]:
                for value in values(contact.get(key)):
                    if isinstance(value, str):
                        value = unquote(value).removeprefix(scheme + ':').strip()
                        lines.append('<a href="' + scheme + ':' + html.escape(value, quote=True) + '">' + html.escape(value) + '</a>')
            lines.append('</section>')
            supplements.append(''.join(lines))
        for key in ('founder', 'employee'):
            for person in values(record.get(key)):
                if not isinstance(person, dict):
                    continue
                name = str(person.get('name') or '').strip()
                if not re.fullmatch(r"[^\W\d_][\w.'’-]+(?:\s+[^\W\d_][\w.'’-]+){1,5}", name, re.UNICODE):
                    continue
                people.append({'name': name, 'title': str(person.get('jobTitle') or ('Founder' if key == 'founder' else ''))[:100],
                               'email': str(person.get('email') or ''), 'source_url': url})
    combined = markup + '\n' + '\n'.join(supplements)
    soup = BeautifulSoup(combined, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'svg']):
        tag.decompose()
    if re.search(r'/(?:about|team|our-team|leadership|people|staff)(?:[-/]|$)', urlparse(url).path, re.I):
        for card in soup.select('.team-member, .team-card, [itemtype*="schema.org/Person"], article')[:30]:
            name_tag = card.select_one('[itemprop="name"], h2, h3, h4')
            if not name_tag:
                continue
            name = name_tag.get_text(' ', strip=True)
            body = card.get_text(' ', strip=True)
            title_tag = card.select_one('[itemprop="jobTitle"], .job-title, .position, .role')
            title = title_tag.get_text(' ', strip=True) if title_tag else ''
            if not title:
                match = re.search(r'\b(?:Co[- ]?Founder|Founder|CEO|Chief Executive Officer|Managing Director|Partner|Owner|Director|President)\b', body, re.I)
                title = match[0] if match else ''
            if title and re.fullmatch(r"[^\W\d_][\w.'’-]+(?:\s+[^\W\d_][\w.'’-]+){1,5}", name, re.UNICODE):
                people.append({'name': name, 'title': title[:100], 'source_url': url, 'email': ''})
    text = '\n'.join(' '.join(line.split()) for line in soup.get_text('\n').splitlines() if line.strip())
    # Use the DOM to retain the smallest address/contact card, not an arbitrary
    # character window that can join adjacent offices.
    contexts = {}
    for tag in soup.find_all(['a', 'span', 'p', 'div']):
        href = unquote(str(tag.get('href') or '')).split('?', 1)[0]
        tokens = []
        if href.lower().startswith(('mailto:', 'tel:')):
            tokens.append(href.split(':', 1)[1].strip())
        if tag.name != 'a' and tag.find(['p', 'div', 'span', 'a']):
            continue
        tokens += re.findall(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}', tag.get_text(' '), re.I)
        for token in tokens:
            selected = ''
            for parent in [tag] + list(tag.parents)[:7]:
                if not getattr(parent, 'get_text', None):
                    continue
                block = parent.get_text('\n', strip=True)
                if len(block) > 1400:
                    break
                postals = POSTAL.findall(re.sub(r'\+?\d[\d(). -]{7,}\d', ' ', block))
                if (parent.find('address') or postals) and len(set(postals)) <= 1:
                    selected = block
                    break
            if selected:
                contexts.setdefault(token.casefold(), selected)
    whatsapp = []
    socials = []
    for tag in soup.find_all('a', href=True):
        href = html.unescape(str(tag['href']))
        host = domain_key(href)
        if host in {'wa.me', 'api.whatsapp.com', 'web.whatsapp.com'}:
            whatsapp.append(href)
        if any(host == name or host.endswith('.' + name) for name in ('linkedin.com', 'instagram.com', 'facebook.com', 'tiktok.com')):
            socials.append(href)
    # Navigation labels such as "Motorhome Manufacturers" describe links,
    # not the site's own service. Addresses/contacts still use the full text.
    for tag in soup.select('nav, header, footer, [role="navigation"], .menu, .navigation, .breadcrumbs, .related-posts'):
        if tag.parent is not None:
            tag.decompose()
    activity = '\n'.join(' '.join(line.split()) for line in soup.get_text('\n').splitlines() if line.strip())
    return {'url': url, 'html': combined, 'text': text, 'addresses': addresses, 'people': people,
            'activity_text': activity,
            'contact_contexts': contexts, 'whatsapp_urls': list(dict.fromkeys(whatsapp)),
            'social_urls': list(dict.fromkeys(socials))}


def contact_context(page: dict, token: str) -> str:
    contexts = page.get('contact_contexts', {})
    if token.casefold() in contexts:
        return contexts[token.casefold()]
    digits = re.sub(r'\D', '', token)
    if len(digits) >= 10:
        for value, context in contexts.items():
            if re.sub(r'\D', '', value).endswith(digits[-10:]):
                return context
    body = page['text']
    position = body.casefold().find(token.casefold())
    if position < 0:
        return ''
    return body[max(0, position - 240):position + len(token) + 40]


def office_key(context: str) -> str:
    # Phone strings must not become postal-code identities.
    context = re.sub(r'\+?\d[\d(). -]{7,}\d', ' ', context)
    matches = POSTAL.findall(context)
    return re.sub(r'\W', '', matches[-1]).casefold() if matches else ''


def contact_links(page: dict, location: str = '') -> list[str]:
    soup = BeautifulSoup(page['html'], 'html.parser')
    links = []
    for tag in soup.find_all('a', href=True):
        url = urljoin(page['url'], html.unescape(str(tag['href'])))
        parsed = urlparse(url)
        if parsed.scheme not in {'http', 'https'} or domain_key(url) != domain_key(page['url']):
            continue
        if parsed.query or re.search(r'\.(pdf|jpg|png|zip|xlsx)$', parsed.path, re.I):
            continue
        if CONTACT_PATH.search(parsed.path + ' ' + tag.get_text(' ')):
            links.append(urlunparse(parsed._replace(fragment='')))
    place_tokens = [x for x in re.findall(r'[a-z]{3,}', location.casefold()) if x not in {'united', 'states'}]
    return sorted(dict.fromkeys(links), key=lambda u: (
        not any(t in u.casefold() for t in place_tokens),
        not bool(re.search(r'contact|enquir|get-in-touch|reach', urlparse(u).path, re.I)),
        not bool(re.search(r'location|office', urlparse(u).path, re.I)), len(u)))


def discovery_scope(page: dict, location: str):
    """Keep a directory's requested city/state section, not its first state."""
    soup = BeautifulSoup(page['html'], 'html.parser')
    for tag in soup(['header', 'footer', 'nav', 'script', 'style']):
        tag.decompose()
    place = location.split(',')[0].casefold().strip()
    for heading in soup.find_all(re.compile(r'^h[1-4]$')):
        label = re.sub(r'[^\w\s-]', '', heading.get_text(' ', strip=True).casefold()).strip()
        if label != place:
            continue
        level = int(heading.name[1])
        section = BeautifulSoup('', 'html.parser')
        chunks = []
        for sibling in heading.next_siblings:
            if getattr(sibling, 'name', '') and re.fullmatch(r'h[1-6]', sibling.name) and int(sibling.name[1]) <= level:
                break
            chunks.append(str(sibling))
        return BeautifulSoup(''.join(chunks), 'html.parser'), True
    return soup, False


def business_names_from_listing(page: dict, location: str) -> list[str]:
    soup, scoped = discovery_scope(page, location)
    if not scoped and not is_listing_source(page['url'], page.get('text', '')):
        return []
    names = []
    place = location.split(',')[0].strip()
    for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'strong', 'b', 'p']):
        if not scoped and not re.search(r'\b'+re.escape(place)+r'\b', element.parent.get_text(' ', strip=True)[:1200], re.I):
            continue
        # Paragraphs with line breaks commonly put name, then street, then city.
        label = element.get_text('\n', strip=True).split('\n')[0].strip()
        details = element.get_text('\n', strip=True)
        sibling = element.find_next_sibling()
        if sibling is not None:
            details += '\n' + sibling.get_text(' ', strip=True)[:300]
        if not POSTAL.search(details):
            continue
        if not re.fullmatch(r"[A-Z][A-Za-z0-9&'’(). -]{3,65}", label) or len(label.split()) > 6:
            continue
        if re.search(r'^(?:get |visit |contact|learn |read |view |find |about|services|company info|builders|custom camper van builders|see all|our |home|call |email|top |best |key |backed |conversion types|upholstery division)', label, re.I):
            continue
        if re.fullmatch(r'(?:Texas|California|Hawaii|United States|United Kingdom|Canada|India)', label, re.I):
            continue
        names.append(label)
    return list(dict.fromkeys(names))[:12]


def business_website_links(page: dict, location: str = '') -> list[str]:
    """Directory/news links are discovery hints, never contact/fit evidence."""
    soup, scoped = discovery_scope(page, location)
    links = []
    ignored = {'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com',
               'youtube.com', 'google.com', 'tiktok.com', 'schema.org', 'w3.org'}
    for tag in soup.find_all('a', href=True):
        url = urljoin(page['url'], str(tag['href']))
        host = domain_key(url)
        if urlparse(url).scheme not in {'http', 'https'} or not host or host == domain_key(page['url']):
            continue
        if any(host == name or host.endswith('.' + name) for name in ignored):
            continue
        if is_listing_source(url) or is_editorial_source(url):
            continue
        label = tag.get_text(' ', strip=True)
        context = tag.parent.get_text(' ', strip=True)[:1000]
        if not scoped and location and not re.search(r'\b' + re.escape(location.split(',')[0].strip()) + r'\b', context, re.I):
            continue
        root = host.split('.')[0].replace('-', '')
        if re.search(r'website|official site|visit (?:us|our|the)|learn more|https?://', label + ' ' + context, re.I) or (len(root) > 4 and root in re.sub(r'\W', '', context.casefold())):
            links.append(url.split('#')[0])
    return list(dict.fromkeys(links))[:8]
