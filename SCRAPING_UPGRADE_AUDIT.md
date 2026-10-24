# Official-site discovery and scraping upgrade — 24 October 2026

## Architecture and implementation plan

Discovery currently finds candidate URLs with Tavily (HTML search fallback), then the generic engine checks official home/contact pages. SQLite stores incremental generic jobs. Velit uses an older independent pipeline and scheduler. Vento discovers pet businesses and creators, enriches with a second identity-matched search, and visits only one contact page. Its social/follower qualification must remain separate from company qualification.

Confirmed priority issues from the saved Texas run:

1. A press-release publisher inherited the industry/address of a business in its article.
2. A Dallas service-area page's description of the city was accepted as a company office.
3. Sportsmobile's Indiana inbox/phone were selected despite an Austin branch; another lead mixed two branches.
4. Structured business addresses, branch contact data and publicly named people are not used by generic extraction.
5. Vento fetches secondary pages sequentially and can follow redirects before checking their destination.
6. Generic and specialized tabs have different progress/recovery and scraping behavior.

Implementation sequence:

- [x] Add failing regressions for the Texas defects, structured contacts, crawl recovery and specialized routing.
- [x] Add shared HTML/structured-data extraction, bounded link discovery and official-site resolution.
- [x] Correct business/location qualification and office contact pairing.
- [x] Reuse extraction in Velit and Vento, retaining follower checks and correcting creator relevance/email bugs exposed by live tests.
- [x] Verify automated tests, browser flows, exports and fresh live searches; measure time/credits and review sources.
- [x] Review repository contents for secrets and preserve existing workspace changes.
- [ ] Commit and push the verified project.

No test or completion claim is made by this initial plan. Website publication, mailbox delivery and telephone reachability are different checks. Blocked/private sites will remain explicit failures rather than having contacts invented.

## Implemented architecture

Generic/Velit: discovery queries → deduplicated business candidates → relevant directory/news links or address-backed business-name lookups → official website → bounded contact/location/team crawl → public business schema/team records → activity/location qualification → matched office contacts → MX/phone-format checks → persisted incremental results and exports.

`public_site_data.py` shares HTML/structured-data extraction with Vento. It only follows organization/branch/person relationships; article authors, arbitrary scripts and foreign organization records do not establish a company's contacts. Service-area city descriptions do not establish offices. Direct HTML navigation and indexed Markdown menu links cannot establish manufacturing activity. Licensing portals are rejected. Public WhatsApp links are preserved without assuming that every phone supports WhatsApp. People require a published name/role/source; employee inboxes are not generated.

The crawler limits pages, bytes, redirects, retries, concurrency, browser renders and overall time. An additional 90-second idle window stops an unproductive tail after verified businesses begin arriving. New accepted businesses extend that window within the original total cap. Completed results survive deadlines/cancellation. Per-request provider usage preserves unknown/interrupted billing rather than silently recording zero.

Velit uses the company engine in its tab, workflow compatibility route and scheduler, including partial snapshots. Its tab now uses persisted jobs for click/Enter, cancellation and refresh recovery. Vento keeps its existing uploads, multi-location batches and social enrichment. Its company scraper checks several pages concurrently and validates redirect destinations before fetching them. Its creator path now rejects URL-shaped emails and requires sourced pet-niche/locality evidence independently of follower count. The shared company status panel is hidden while Vento uses its own summary.

## Additional confirmed issues found during verification

- A vehicle-licensing portal and a dealer navigation label mentioning manufacturers could pass a keyword-only activity check. The portal policy and main-content/Markdown activity extraction address the source of those false positives.
- A TikTok URL was parsed as an email because `/` was permitted in an unrestricted email regex. URL removal and syntax validation fix extraction and final-row normalization.
- Vento included its own search query in relevance evidence and accepted creators with no demonstrated pet niche/local presence. Queries no longer establish evidence; profile/bio checks, bounded city matching and exclusion of tour destinations qualify actual creators. A high follower count alone is insufficient.
- Directory heading guesses such as “Key Takeaways” could waste name-resolution queries. Only relevant directory sections and address-backed candidate names are used.
- A location-only logo hid the actual company copyright brand. Excluded geographic names now apply consistently, and trademark decorations are removed from the published brand.

## Verification

The pre-upgrade baseline passed **269 tests**. The initial new regressions reproduced **five failures** before fixes. The final full suite, with the optional installed-browser integration enabled, passed **295 tests** in 23.68 seconds. The real-browser fixture serves a controlled JavaScript shell and verifies sourced extraction without asserting SMTP verification. The deadline regression uses a meaningful finished/unfinished-peer distinction rather than an 80ms Windows scheduler race. A production Vento company cannot pass solely on a snippet when no official website was verified; its controlled positive fixture also verifies that website-first enrichment avoids twelve unnecessary searches.

The browser contract passes saved results, refresh, cancellation, keyboard/click routing, Velit recovery, Vento rendering, responsive layouts and a reopened 15-row XLSX export, with zero page errors. Browser API fixtures consume no search credits. Main localhost already runs with reload and exposes the updated mode schema; the audit server uses a separate SQLite file, preserving the user's search history.

Selected live runs (single observations, not service guarantees):

| Case | Returned / requested | Observed wall time | Tavily reported credits |
|---|---:|---:|---:|
| Texas van/RV businesses, final idle-budget run | 11 / 15 | 181.9s (178.7s engine) | 16, complete request reporting |
| Velit, California van/RV businesses | 5 / 5 | 15.9s | At least 3; one interrupted request unreported |
| London accountants | 5 / 5 | 34.2s | At least 4; one interrupted request unreported |
| Vento, Austin pet grooming | 5 / 5 | 19.1s | 8 |
| Vento, Seattle dog-parent creators, corrected qualification | 0 / 2 | 74.1s | 18 |

The final Texas run reached five in approximately 16 engine seconds and eleven in approximately 89 seconds, then stopped when no additional verified businesses arrived. MarketersMEDIA, Field Van's Dallas service-area page, the licensing portal and the manufacturer-navigation false positive are not among its eleven returned businesses. A previous diagnostic Seattle run returned two false positives; those are excluded from the deliverable and the corrected run reports the shortfall honestly. Its candidates lacked confirmed creator niche or the follower threshold. Apify successfully enriched profiles, but its monetary charges were not measured (three batches in the corrected creator run).

Selected runs account for **at least 49 reported Tavily credits**. The complete local audit ledger includes intermediate debugging/cancelled runs: **at least 149 reported Tavily credits, with three unreported attempts** across 12 unique audit runs. Hunter and Gemini calls were zero in the selected runs. Account usage snapshots did not advance reliably during the final run and are not substituted for request-level billing evidence.

## Lead source review and deliverable scope

The selected company runs contain **26 company records** (11 Texas, five California, five London, five Austin grooming). Their published websites, category/location evidence and contacts were reviewed. Direct HTTP source snapshots reproduce most contacts; blocked rechecks use the companies' official pages through an alternate reader. All 26 have published phone routes; that is not evidence they answer calls. The reviewed workbook leaves one Premier Autos metadata email blank because it could not be reproduced independently; its published phone and custom Sprinter program remain available. All email delivery is unconfirmed. Scores are completeness/evidence heuristics, not accuracy percentages.

Examples of alternate official evidence: [Big Valley Ford contacts](https://www.bigvalleyford.biz/contact.htm), [its upfitting service](https://www.bigvalleyford.biz/commercial/upfits-california.htm), [Kreston Reeves London](https://www.krestonreeves.com/locations/london/), [Premier Autos contacts](https://www.premierautosofdallas.com/contact.htm), [its custom van program](https://www.premierautosofdallas.com/premier-legend-vans.htm), and [Texas Fleet Outfitters' service page](https://texasfleetoutfitters.com/commercial-upfitting). [Setina's own dealer listing](https://setina.com/where-to-buy/) corroborates Texas Fleet Outfitters' address/phone. Premier's custom-build program is not proof of a separately owned manufacturing factory.

The workbook/report bundle stays in ignored local `exports/scraping-upgrade/deliverable/`; live contact data and credentials are not committed. Historical raw runs retain their original observations; they are not silently rewritten as current verified results. The UI identifies older saved quality policies.

Remaining limits: no universal 15-lead guarantee, no mailbox delivery/phone-answering/outreach verification, no certified live Sheets write (`TODO_SHEET_ID` is absent), no proprietary Hunter/Apollo-sized database, and no certification for multi-worker/serverless deployment. Local SQLite/scheduler workers still require a persistent single application worker. These limits do not turn shortfalls or unavailable sources into successful matches.

Implementation references: [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/), [Schema.org LocalBusiness](https://schema.org/LocalBusiness), [Playwright browser-context routing](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-route).
