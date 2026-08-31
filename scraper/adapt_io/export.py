from datetime import datetime, timezone
import logging
from pathlib import Path
import re

from playwright.sync_api import Page

logger = logging.getLogger(__name__)

CONTACT_LINK_SELECTOR = 'a[href*="linkedin.com/in/"]'
DEBUG_PATH = Path(__file__).resolve().parents[2] / "results" / "pagination_debug.log"


def _write_pagination_debug(message: str) -> None:
    try:
        DEBUG_PATH.parent.mkdir(exist_ok=True)
        with DEBUG_PATH.open("a", encoding="utf-8") as debug_file:
            debug_file.write(
                f"{datetime.now(timezone.utc).isoformat()} {message}\n"
            )
            debug_file.flush()
    except OSError:
        pass


def _pagination_debug(page: Page, stage: str, visible_count: int = 0) -> str:
    state = page.evaluate(
        """({stage, visibleCount}) => {
            const pagination = document.querySelector('.pagination');
            const text = pagination?.querySelector('.text')?.innerText || '';
            const next = pagination?.querySelector('.next-page');
            const summary = document.body.innerText.match(/([\\d,]+)\\s+contacts\\s+from/i);
            return JSON.stringify({
                stage,
                visibleCount,
                pageText: text,
                totalSummary: summary ? summary[0] : '',
                paginationClass: pagination?.className || '',
                nextClass: next?.className || '',
                nextHtml: next?.outerHTML || '',
            });
        }""",
        {
            "stage": stage,
            "visibleCount": visible_count,
        },
    )
    _write_pagination_debug(f"ADAPT_PAGINATION {state}")
    return state


def _extract_visible_contacts(page: Page) -> list[dict[str, str]]:
    """Extract contact cards from Adapt.io's div-based results grid."""
    return page.locator(CONTACT_LINK_SELECTOR).evaluate_all(
        """
        (links) => {
            const emailPattern = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}/ig;
            const phonePattern = /(?:\\+?\\d[\\d ()-]{7,}\\d)/g;
            const rows = [];
            const seen = new Set();

            for (const link of links) {
                let row = link;
                while (row.parentElement) {
                    const parent = row.parentElement;
                    if (parent.querySelectorAll('a[href*="linkedin.com/in/"]').length !== 1) {
                        break;
                    }
                    row = parent;
                }

                const text = row.innerText.replace(/\\s+/g, " ").trim();
                const lines = row.innerText
                    .split(/\\n+/)
                    .map((value) => value.replace(/\\s+/g, " ").trim())
                    .filter(Boolean);
                const contactUrl = link.href;
                const key = contactUrl || text;
                if (!text || seen.has(key)) continue;
                seen.add(key);

                const urls = [...row.querySelectorAll("a[href]")]
                    .map((item) => item.href)
                    .filter(Boolean);
                const emails = text.match(emailPattern) || [];
                const phones = text.match(phonePattern) || [];
                const images = [...row.querySelectorAll("img[src]")]
                    .map((item) => item.src)
                    .filter(Boolean);
                const contactNameElement = row.querySelector(
                    ".contact-name-wrapper .contact-name"
                );
                const companyNameElement = row.querySelector(
                    ".company-name-wrapper .company-name"
                );
                const companyLink = [...row.querySelectorAll('a[href*="linkedin.com/company/"]')][0];
                const companyUrl = companyLink ? companyLink.href : "";
                const companyName = (
                    companyNameElement?.innerText ||
                    companyLink?.innerText ||
                    ""
                ).replace(/\\s+/g, " ").trim();
                const titleElement = row.querySelector(
                    ".contact-name-wrapper .title"
                );
                const locationElement = row.querySelector(
                    ".contact-name-wrapper .location-address .info-detail"
                );
                const employeeElement = row.querySelector(
                    '.industry-content-info .info-wrap svg[title="Employee Count"]'
                )?.parentElement?.querySelector("span");
                const name = (
                    contactNameElement?.innerText ||
                    lines.find((value) => value && !value.includes("@")) ||
                    ""
                ).replace(/\\s+/g, " ").trim();
                const headcountOptions = [
                    "0 - 25", "25 - 100", "100 - 250", "250 - 1000",
                    "1K - 10K", "10K - 50K", "50K - 100K", "> 100K",
                ];
                const headcount = (
                    employeeElement?.innerText.trim() ||
                    headcountOptions.find((value) => lines.includes(value)) ||
                    ""
                );
                const headcountIndex = headcount ? lines.indexOf(headcount) : -1;
                const nameIndex = lines.indexOf(name);
                const locationIndex = lines.findIndex((value, index) =>
                    index > nameIndex && value.split(",").length >= 2
                );
                const jobTitle = titleElement?.innerText.trim() || (
                    locationIndex > nameIndex
                        ? lines.slice(nameIndex + 1, locationIndex).join(" ")
                        : ""
                );
                const location = locationElement?.innerText.trim() || (
                    locationIndex >= 0 ? lines[locationIndex] : ""
                );
                const revenue = headcountIndex >= 0 ? lines[headcountIndex + 1] || "" : "";
                const domains = [...new Set(urls.filter((url) => {
                    try {
                        const host = new URL(url).hostname;
                        return !host.includes("linkedin.com") &&
                            !host.includes("facebook.com") &&
                            !host.includes("x.com");
                    } catch (_) {
                        return false;
                    }
                }))];
                const emailStatus = lines.find((value) =>
                    ["verified", "valid"].includes(value.toLowerCase())
                ) || "";

                const nameParts = name.split(/\\s+/).filter(Boolean);
                rows.push({
                    first_name: nameParts[0] || "",
                    last_name: nameParts.slice(1).join(" "),
                    job_title: jobTitle,
                    company_name: companyName,
                    company_domain: domains[0] || "",
                    employee_count: headcount,
                    location: location,
                    linkedin_profile_url: contactUrl,
                });
            }

            return rows;
        }
        """
    )


def _is_upgrade_modal_visible(page: Page) -> bool:
    """Checks if Adapt.io free plan upgrade modal or limit popover is visible."""
    try:
        modal_text_found = page.evaluate(
            """() => {
                const bodyText = document.body.innerText || '';
                return /only first \\d+ results are available as a free user/i.test(bodyText)
                    || /please purchase a plan to access more/i.test(bodyText)
                    || /upgrade now/i.test(bodyText);
            }"""
        )
        return bool(modal_text_found)
    except Exception:
        return False


def _next_page(page: Page, previous_key: str) -> bool:
    _pagination_debug(page, "before_next")
    pagination = page.locator(".pagination").first
    if not pagination.count():
        return False

    pagination_text = pagination.locator(".text").first
    page_label = pagination_text.inner_text() if pagination_text.count() else ""
    page_match = re.search(
        r"Pages\s+(\d+)\s+of\s+(\d+)",
        page_label,
        re.IGNORECASE,
    )

    if not page_match:
        return False

    current_page_num = int(page_match.group(1))
    total_pages = int(page_match.group(2))

    if current_page_num >= total_pages:
        return False

    next_page = pagination.locator(".next-page").first
    if not next_page.count():
        return False

    classes = next_page.get_attribute("class") or ""
    if "disable" in classes.split():
        return False

    try:
        next_page.click(timeout=5000)
    except Exception:
        next_page.evaluate("element => element.click()")

    _pagination_debug(page, "after_click")

    # Give browser a brief pause to render either upgrade modal or new results
    page.wait_for_timeout(1000)

    if _is_upgrade_modal_visible(page):
        logger.info("Adapt.io free tier limit popup detected. Finishing pagination gracefully.")
        _write_pagination_debug("UPGRADE_MODAL_DETECTED: Stopping pagination gracefully.")
        return False

    try:
        page.wait_for_function(
            """({previousPage}) => {
                const bodyText = document.body.innerText || '';
                if (/only first \\d+ results are available/i.test(bodyText) || /upgrade now/i.test(bodyText)) {
                    return true;
                }
                const pageText = document.querySelector('.pagination .text');
                return pageText && pageText.innerText !== previousPage;
            }""",
            arg={
                "previousPage": page_label,
            },
            timeout=10_000,
        )
    except Exception:
        if _is_upgrade_modal_visible(page):
            logger.info("Adapt.io free tier limit detected on timeout.")
            return False
        logger.warning("Pagination text did not update after click. Stopping pagination.")
        return False

    if _is_upgrade_modal_visible(page):
        return False

    try:
        page.locator(CONTACT_LINK_SELECTOR).first.wait_for(
            state="visible",
            timeout=10_000,
        )
        page.wait_for_function(
            """(previousKey) => {
                const link = document.querySelector('a[href*="linkedin.com/in/"]');
                return link && link.href !== previousKey;
            }""",
            arg=previous_key,
            timeout=10_000,
        )
    except Exception:
        logger.warning("Contacts list did not update for next page. Stopping pagination.")
        return False

    _pagination_debug(page, "after_change")
    return True


def _wait_for_pagination(page: Page) -> None:
    page.wait_for_function(
        """() => {
            const contacts = document.querySelectorAll('a[href*="linkedin.com/in/"]').length;
            const pagination = document.querySelector('.pagination');
            const element = pagination?.querySelector('.text');
            return contacts > 0 && (
                !pagination ||
                (element && /Pages\\s+\\d+\\s+of\\s+\\d+/i.test(element.innerText))
            );
        }""",
        timeout=60_000,
    )


def _refresh_stale_pagination(page: Page, visible_count: int) -> None:
    if visible_count < 50:
        return

    page.wait_for_function(
        """(visibleCount) => {
            const element = document.querySelector('.pagination .text');
            if (!element) return false;
            const match = element.innerText.match(/Pages\\s+(\\d+)\\s+of\\s+(\\d+)/i);
            if (!match) return false;
            const summary = document.body.innerText.match(/([\\d,]+)\\s+contacts\\s+from/i);
            const totalContacts = summary ? Number(summary[1].replace(/,/g, "")) : 0;
            return Number(match[2]) > 1 || totalContacts <= visibleCount;
        }""",
        arg=visible_count,
        timeout=10_000,
    )


def scrape_prospects(page: Page) -> list[dict[str, str]]:
    """Collect all visible contact cards, advancing through every result page."""
    _write_pagination_debug("SCRAPER_BUILD pagination-direct-debug-v1")
    page.locator(CONTACT_LINK_SELECTOR).first.wait_for(
        state="visible",
        timeout=60_000,
    )
    _wait_for_pagination(page)

    results = []
    seen = set()
    for _ in range(1000):
        page_rows = _extract_visible_contacts(page)
        _refresh_stale_pagination(page, len(page_rows))
        if not page_rows:
            if results:
                # We already scraped previous pages
                break
            raise TimeoutError("no contact cards were rendered for the current page")

        _pagination_debug(page, "page_extracted", len(page_rows))
        for row in page_rows:
            key = row["linkedin_profile_url"] or (
                f"{row['first_name']} {row['last_name']}".strip()
            )
            if key and key not in seen:
                seen.add(key)
                results.append(row)

        previous_key = page_rows[0]["linkedin_profile_url"] or page_rows[0]["first_name"]
        if not _next_page(page, previous_key):
            break

    return results