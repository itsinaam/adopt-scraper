import re
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


CONTACT_CRITERIA_FILTERS = {
    "Job Title",
    "Contact Location",
    "Location",
    "Department",
    "Seniority",
    "Name",
}

COMPANY_CRITERIA_FILTERS = {
    "Industry",
    "Employee Count",
    "Revenue",
    "Company",
    "Company Name",
    "Company Location",
}


def _dismiss_popups(page: Page) -> None:
    try:
        popup_selectors = [
            'button:has-text("Skip")',
            'button:has-text("Got it")',
            'button:has-text("Close")',
            'button:has-text("Maybe later")',
            '.modal-header .close',
            '[aria-label="Close"]',
            '.walkme-action-destroy-1',
            'div[data-ng-click*="close"]',
        ]
        for selector in popup_selectors:
            elements = page.locator(selector)
            for idx in range(elements.count()):
                el = elements.nth(idx)
                if el.is_visible():
                    try:
                        el.click()
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
    except Exception:
        pass


def open_prospect_search(page: Page) -> None:
    if "advanced-search" not in page.url.lower():
        candidates = (
            page.get_by_role("button", name="Prospect Search", exact=True),
            page.get_by_role("link", name="Prospect Search", exact=True),
            page.get_by_text("Prospect Search", exact=True),
            page.locator('a[href*="advanced-search"]'),
        )

        if _click_first_visible(candidates, page, timeout_seconds=15):
            try:
                page.wait_for_url(lambda u: "advanced-search" in u.lower(), timeout=15_000)
            except Exception:
                pass

        if "advanced-search" not in page.url.lower():
            try:
                page.goto("https://leads.adapt.io/advanced-search/contact#search", wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                page.goto("https://leads.adapt.io/advanced-search/contact#search", wait_until="commit", timeout=20_000)

    # Dismiss any welcome/tour modals if present
    _dismiss_popups(page)

    # Wait for the search interface and criteria sidebar to be ready
    try:
        page.wait_for_selector('text="Contact Criteria"', timeout=30_000)
    except Exception:
        try:
            page.wait_for_selector('text="Job Title"', timeout=20_000)
        except Exception:
            if "login" in page.url.lower():
                raise TimeoutError("Adapt.io session expired while opening Prospect Search")
            page.wait_for_timeout(5000)


def _click_first_visible(locators, page: Page, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for locator in locators:
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    try:
                        candidate.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass
                    try:
                        candidate.click(timeout=2000)
                        return True
                    except Exception:
                        continue

        page.wait_for_timeout(250)

    return False


def open_filter(
    page: Page,
    filter_name: str,
) -> None:
    _dismiss_popups(page)

    filter_pattern = re.compile(
        rf"^\s*{re.escape(filter_name)}\s*$",
        re.IGNORECASE,
    )
    filter_target = (
        page.get_by_text(filter_pattern),
        page.get_by_role("button", name=filter_pattern),
        page.locator(
            f"xpath=//*[normalize-space(text())={filter_name!r}]"
        ),
    )

    # Wait for the filter itself before expanding its criteria section.
    if _click_first_visible(filter_target, page, timeout_seconds=10):
        return

    # 2. If not visible, expand the correct parent criteria section
    if filter_name in CONTACT_CRITERIA_FILTERS:
        contact_criteria_pattern = re.compile(
            r"^\s*Contact\s+Criteria\s*$",
            re.IGNORECASE,
        )
        contact_criteria = (
            page.get_by_text(contact_criteria_pattern),
            page.get_by_role("button", name=contact_criteria_pattern),
            page.locator(
                "xpath=//*[normalize-space(text())='Contact Criteria']"
            ),
        )
        if _click_first_visible(contact_criteria, page, timeout_seconds=10):
            page.wait_for_timeout(500)
    elif filter_name in COMPANY_CRITERIA_FILTERS:
        company_criteria_pattern = re.compile(
            r"^\s*Company\s+Criteria\s*$",
            re.IGNORECASE,
        )
        company_criteria = (
            page.get_by_text(company_criteria_pattern),
            page.get_by_role("button", name=company_criteria_pattern),
            page.locator(
                "xpath=//*[normalize-space(text())='Company Criteria']"
            ),
        )
        if _click_first_visible(company_criteria, page, timeout_seconds=10):
            page.wait_for_timeout(500)

    # 3. Final attempt to find and click the filter target
    if not _click_first_visible(
        filter_target,
        page,
        timeout_seconds=45,
    ):
        raise TimeoutError(f"{filter_name} filter did not appear")


def apply_job_titles(
    page: Page,
    job_titles: list[str],
) -> None:
    if not job_titles:
        return

    job_titles = [title.strip() for title in job_titles if title.strip()]
    if not job_titles:
        return

    open_filter(
        page,
        "Job Title",
    )

    title_input = _first_visible_locator(
        page.locator('input[placeholder="Title"]'),
        page,
        timeout_seconds=30,
        description="Title input",
    )

    for title in job_titles:
        title_input.fill(title)

        if not _click_first_visible(
            (page.get_by_text(title, exact=True),),
            page,
            timeout_seconds=5,
        ):
            continue


def _first_visible_locator(
    locator,
    page: Page,
    timeout_seconds: int,
    description: str,
):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for index in range(locator.count()):
            candidate = locator.nth(index)
            if candidate.is_visible():
                return candidate

        page.wait_for_timeout(250)

    raise TimeoutError(f"{description} did not appear")


def _submit_search(page: Page) -> None:
    candidates = (
        page.get_by_role(
            "button",
            name=re.compile(r"see\s+matching\s+contacts", re.IGNORECASE),
        ),
        page.locator("button").filter(
            has_text=re.compile(r"see\s+matching\s+contacts", re.IGNORECASE)
        ),
        page.locator(
            'button[data-ng-click*="search"], '
            'button[ng-click*="search"], '
            'button[aria-label*="matching contacts" i]'
        ),
        page.get_by_text(
            re.compile(r"^\s*see\s+matching\s+contacts\s*$", re.IGNORECASE)
        ),
    )

    page.keyboard.press("Escape")
    _dismiss_popups(page)
    page.wait_for_timeout(1000)

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if _click_first_visible(candidates, page, timeout_seconds=3):
            return

        clicked = page.evaluate(
            """() => {
                const normalize = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const buttons = [...document.querySelectorAll('button, [role="button"]')];
                const target = buttons.find(button => {
                    const text = normalize(button.innerText || button.getAttribute('aria-label'));
                    const style = window.getComputedStyle(button);
                    return text.includes('see matching contacts')
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && !button.disabled;
                });
                if (!target) return false;
                target.click();
                return true;
            }"""
        )
        if clicked:
            return
        page.wait_for_timeout(500)

    raise TimeoutError("See matching contacts button did not appear after retries")


def _apply_location_tab(page: Page, tab_name: str, values: list[str]) -> None:
    cleaned_values = [v.strip() for v in values if isinstance(v, str) and v.strip()]
    if not cleaned_values:
        return

    tab_title = tab_name.strip().title()

    # Switch to tab if not already active
    tab_pattern = re.compile(rf"^\s*{re.escape(tab_title)}\s*$", re.IGNORECASE)
    active_tab = page.locator(".tab.active").filter(has_text=tab_pattern)
    if active_tab.count() == 0 or not active_tab.first.is_visible():
        tab_candidates = (
            page.locator(".tab").filter(has_text=tab_pattern),
            page.locator(".tab", has_text=tab_title),
            page.get_by_role("tab", name=tab_title),
            page.get_by_text(tab_title, exact=True),
        )
        if not _click_first_visible(tab_candidates, page, timeout_seconds=10):
            raise TimeoutError(f"{tab_title} tab did not appear in Location filter")
        page.wait_for_timeout(300)

    tab_input = _first_visible_locator(
        page.locator(
            f'input[placeholder="{tab_title}" i], '
            f'input[placeholder*="{tab_title}" i], '
            f'.top-wrapper input, '
            f'input[type="text"]'
        ),
        page,
        timeout_seconds=10,
        description=f"{tab_title} input",
    )

    for item in cleaned_values:
        tab_input.fill("")
        tab_input.fill(item)
        page.wait_for_timeout(400)

        # Select the first result matching the search from the suggestion dropdown
        first_result_candidates = (
            page.locator(".suggestion-wrapper").get_by_text(
                re.compile(rf"^\s*{re.escape(item)}", re.IGNORECASE)
            ),
            page.locator(".suggestion-wrapper [role='option']"),
            page.locator(".suggestion-wrapper label"),
            page.locator(".suggestion-wrapper [class*='item']"),
            page.locator(".suggestion-wrapper [class*='suggestion']"),
            page.locator(".suggestion-wrapper > div").filter(has_text=re.compile(r"\S")),
            page.locator(".suggestion-wrapper > *").filter(has_text=re.compile(r"\S")),
            page.get_by_text(
                re.compile(
                    rf"^{re.escape(item)}.*$",
                    re.IGNORECASE,
                ),
            ),
        )

        if not _click_first_visible(
            first_result_candidates,
            page,
            timeout_seconds=5,
        ):
            continue

        page.wait_for_timeout(300)


def apply_locations(page: Page, locations) -> None:
    if not locations:
        return

    open_filter(page, "Location")

    # If locations is a dict: e.g. {"country": ["Canada"], "city": ["Halifax (NS)"]}
    if isinstance(locations, dict):
        for key, vals in locations.items():
            if not vals:
                continue
            if not isinstance(vals, list):
                vals = [vals] if isinstance(vals, str) else []
            k_lower = key.strip().lower()
            if k_lower in ("country", "countries"):
                _apply_location_tab(page, "Country", vals)
            elif k_lower in ("city", "cities"):
                _apply_location_tab(page, "City", vals)
            elif k_lower in ("state", "states", "region", "regions"):
                _apply_location_tab(page, "State", vals)
            else:
                _apply_location_tab(page, key.capitalize(), vals)

    # If locations is a list:
    elif isinstance(locations, list):
        dict_items = [item for item in locations if isinstance(item, dict)]
        if dict_items:
            for item in dict_items:
                apply_locations(page, item)

        string_items = [item for item in locations if isinstance(item, str) and item.strip()]
        if string_items:
            _apply_location_tab(page, "Country", string_items)


def _check_options(page: Page, options: list[str]) -> None:
    for option in options:
        option_pattern = re.compile(
            rf"^\s*{re.escape(option)}\s*$",
            re.IGNORECASE,
        )
        candidates = (
            page.get_by_label(option, exact=True),
            page.locator("label").filter(has_text=option_pattern),
            page.get_by_text(option_pattern),
        )

        if not _click_first_visible(candidates, page, timeout_seconds=5):
            continue


def apply_industries(page: Page, industries: list[str]) -> None:
    if not industries:
        return

    cleaned_industries = [ind.strip() for ind in industries if ind and ind.strip()]
    if not cleaned_industries:
        return

    open_filter(page, "Industry")

    search_input = _first_visible_locator(
        page.locator('.top-wrapper input[placeholder="Search"], .top-wrapper input, input[placeholder="Search"]'),
        page,
        timeout_seconds=10,
        description="Industry search input",
    )

    for industry in cleaned_industries:
        search_input.fill("")
        search_input.fill(industry)
        page.wait_for_timeout(300)

        industry_pattern = re.compile(
            rf"^\s*{re.escape(industry)}\s*$",
            re.IGNORECASE,
        )
        candidates = (
            page.locator(".option-wrapper").get_by_text(industry_pattern),
            page.locator(".option-wrapper label").filter(has_text=industry_pattern),
            page.locator(".option-wrapper [role='checkbox']"),
            page.locator("label").filter(has_text=industry_pattern),
            page.get_by_text(industry_pattern),
        )

        if not _click_first_visible(
            candidates,
            page,
            timeout_seconds=5,
        ):
            continue

        page.wait_for_timeout(400)


def apply_employee_counts(page: Page, employee_counts: list[str]) -> None:
    if employee_counts:
        open_filter(page, "Employee Count")
        _check_options(page, employee_counts)


def apply_filters(page: Page, filters: dict, log_callback=None) -> None:
    # Consolidate location filters (support top-level "cities", "countries", or nested "locations")
    locations = filters.get("locations")
    cities = filters.get("cities") or filters.get("city")
    countries = filters.get("countries") or filters.get("country")
    states = filters.get("states") or filters.get("state")

    if cities or countries or states:
        if not locations:
            locations = {}
        elif isinstance(locations, list) and all(isinstance(x, str) for x in locations):
            locations = {"country": locations}
        elif not isinstance(locations, dict):
            locations = {}

        if cities:
            locations["city"] = (locations.get("city") or []) + (cities if isinstance(cities, list) else [cities])
        if countries:
            locations["country"] = (locations.get("country") or []) + (countries if isinstance(countries, list) else [countries])
        if states:
            locations["state"] = (locations.get("state") or []) + (states if isinstance(states, list) else [states])

    filter_steps = (
        ("Job Title", apply_job_titles, filters.get("job_titles", [])),
        ("Location", apply_locations, locations),
        ("Industry", apply_industries, filters.get("industries", [])),
        (
            "Employee Count",
            apply_employee_counts,
            filters.get("employee_counts", []),
        ),
    )

    for filter_name, apply_filter, values in filter_steps:
        if values and log_callback:
            if isinstance(values, dict):
                formatted_values = ", ".join(
                    f"{k.capitalize()}={v}" for k, v in values.items() if v
                )
            elif isinstance(values, list):
                formatted_values = f"{', '.join(str(v) for v in values[:3])}{'...' if len(values) > 3 else ''}"
            else:
                formatted_values = str(values)
            log_callback(f"Applying filter '{filter_name}': {formatted_values}")
        try:
            apply_filter(page, values)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError(f"{filter_name} filter timed out") from exc

    if log_callback:
        log_callback("Submitting search: clicking 'See matching contacts'...")

    _submit_search(page)