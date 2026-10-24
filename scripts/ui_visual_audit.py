"""Small local-only responsive smoke audit for the standalone UI pages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


VIEWPORTS = ((375, 812), (768, 900), (1024, 768), (1440, 900))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-base", default="http://127.0.0.1:8765")
    parser.add_argument("--static-base", default="http://127.0.0.1:8766")
    parser.add_argument("--page", action="append", dest="selected_pages")
    parser.add_argument(
        "--output",
        default=str(Path(os.environ.get("TEMP", ".")) / "leadgen_visual_audit" / "redesign"),
    )
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    pages = (
        ("dashboard", f"{args.app_base}/"),
        ("studio", f"{args.app_base}/studio"),
        ("leadgen", f"{args.app_base}/leads"),
        ("email-verifier", f"{args.app_base}/email-verifier"),
        ("velit-scheduler", f"{args.app_base}/velit-batch-scheduler"),
        ("hunter-search", f"{args.app_base}/hunter-search"),
        ("company-chat", f"{args.static_base}/company_chat.html"),
        ("linkedin-campaign", f"{args.static_base}/linkedin_campaign.html"),
    )
    if args.selected_pages:
        selected = set(args.selected_pages)
        pages = tuple(item for item in pages if item[0] in selected)

    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, url in pages:
            for width, height in VIEWPORTS:
                page = browser.new_page(
                    viewport={"width": width, "height": height},
                    color_scheme="dark",
                )
                # A screenshot audit must never start, pause, reset, or enqueue a
                # real job. Existing pages may issue writes during boot, so keep
                # those inside the browser as synthetic conflict responses while
                # allowing all read-only requests through to the local app.
                page.add_init_script(
                    """
                    (() => {
                        const nativeFetch = window.fetch.bind(window);
                        window.__uiAuditBlockedWrites = [];
                        window.fetch = (input, init = {}) => {
                            const method = String(init.method || 'GET').toUpperCase();
                            if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
                                const url = typeof input === 'string' ? input : input?.url || '';
                                window.__uiAuditBlockedWrites.push({ method, url });
                                return Promise.resolve(new Response(
                                    JSON.stringify({ detail: 'Blocked by read-only UI visual audit' }),
                                    { status: 409, headers: { 'Content-Type': 'application/json' } },
                                ));
                            }
                            return nativeFetch(input, init);
                        };
                    })();
                    """
                )
                console_errors: list[str] = []
                page_errors: list[str] = []
                failed_responses: list[dict[str, object]] = []
                page.on(
                    "console",
                    lambda message, bucket=console_errors: bucket.append(message.text)
                    if message.type == "error"
                    else None,
                )
                page.on("pageerror", lambda error, bucket=page_errors: bucket.append(str(error)))
                page.on(
                    "response",
                    lambda item, bucket=failed_responses: bucket.append(
                        {"status": item.status, "url": item.url}
                    )
                    if item.status >= 400
                    else None,
                )
                response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                # Allow the shared entrance treatment and any first-paint scripts to settle
                # without making the full multi-viewport audit unnecessarily slow.
                page.wait_for_timeout(350)
                metrics = page.evaluate(
                    """() => ({
                        viewport: innerWidth,
                        scrollWidth: document.documentElement.scrollWidth,
                        nav: Boolean(document.querySelector('.workspace-nav')),
                        css: [...document.styleSheets].some(
                            sheet => (sheet.href || '').includes('/assets/workspace.css')
                        ),
                        main: Boolean(document.querySelector('main, [role=main]')),
                        workspaceLinks: [...document.querySelectorAll('.workspace-link')]
                            .map(link => ({
                                text: link.textContent.trim(),
                                left: Math.round(link.getBoundingClientRect().left),
                                right: Math.round(link.getBoundingClientRect().right),
                                display: getComputedStyle(link).display,
                            })),
                        blockedWrites: window.__uiAuditBlockedWrites || [],
                        offenders: [...document.body.querySelectorAll('*')]
                            .map(element => {
                                const rect = element.getBoundingClientRect();
                                return {
                                    tag: element.tagName.toLowerCase(),
                                    id: element.id,
                                    className: typeof element.className === 'string'
                                        ? element.className.slice(0, 120)
                                        : '',
                                    left: Math.round(rect.left),
                                    right: Math.round(rect.right),
                                    width: Math.round(rect.width),
                                };
                            })
                            .filter(item => item.right > innerWidth + 2 || item.left < -2)
                            .slice(0, 8),
                    })"""
                )
                if width in (375, 1440):
                    page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=False)
                results.append(
                    {
                        "page": name,
                        "width": width,
                        "status": response.status if response else None,
                        "overflow": metrics["scrollWidth"] > metrics["viewport"] + 2,
                        "nav": metrics["nav"],
                        "css": metrics["css"],
                        "main": metrics["main"],
                        "scroll_width": metrics["scrollWidth"],
                        "workspace_links": metrics["workspaceLinks"],
                        "blocked_writes": metrics["blockedWrites"],
                        "offenders": metrics["offenders"] if metrics["scrollWidth"] > metrics["viewport"] + 2 else [],
                        "console_errors": console_errors,
                        "page_errors": page_errors,
                        "failed_responses": failed_responses,
                    }
                )
                page.close()
        browser.close()

    print(json.dumps({"screenshots": str(output), "results": results}, indent=2))


if __name__ == "__main__":
    main()
