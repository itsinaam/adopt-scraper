import re
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def open_prospect_search(page: Page) -> None:
    if "advanced-search" in page.url.lower():
        return

    candidates = (
        page.get_by_role("button", name="Prospect Search", exact=True),
        page.get_by_role("link", name="Prospect Search", exact=True),
        page.get_by_text("Prospect Search", exact=True),
        page.locator('a[href*="advanced-search"]'),
    )

    if _click_first_visible(candidates, page, timeout_seconds=15):
        try:
            page.wait_for_url(lambda u: "advanced-search" in u.lower(), timeout=15_000)
            return
        except Exception:
            pass

    # Fallback: navigate directly to advanced-search URL if button didn't appear or navigate
    try:
        page.goto("https://leads.adapt.io/advanced-search/contact#search", wait_until="domcontentloaded", timeout=20_000)
    except Exception:
        page.goto("https://leads.adapt.io/advanced-search/contact#search", wait_until="commit", timeout=15_000)


def _click_first_visible(locators, page: Page, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for locator in locators:
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    candidate.click()
                    return True

        page.wait_for_timeout(250)

    return False


def open_filter(
    page: Page,
    filter_name: str,
) -> None:
    filter_target = page.get_by_text(filter_name, exact=True)
    if _click_first_visible((filter_target,), page, timeout_seconds=3):
        return

    # If the filter is under "Company Criteria" and collapsed, expand it
    company_criteria = page.get_by_text("Company Criteria", exact=True)
    if company_criteria.count() > 0 and company_criteria.first.is_visible():
        company_criteria.first.click()
        page.wait_for_timeout(300)

    if not _click_first_visible(
        (filter_target,),
        page,
        timeout_seconds=30,
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


def apply_locations(page: Page, locations: list[str]) -> None:
    if not locations:
        return

    cleaned_locations = [loc.strip() for loc in locations if loc and loc.strip()]
    if not cleaned_locations:
        return

    open_filter(page, "Location")

    # Switch to Country tab if not already active
    active_country_tab = page.locator(".tab.active").filter(
        has_text=re.compile(r"^Country$", re.IGNORECASE)
    )
    if active_country_tab.count() == 0 or not active_country_tab.first.is_visible():
        country_tab_candidates = (
            page.locator(".tab").filter(has_text=re.compile(r"^Country$", re.IGNORECASE)),
            page.locator(".tab", has_text="Country"),
            page.get_by_role("tab", name="Country"),
            page.get_by_text("Country", exact=True),
        )
        if not _click_first_visible(country_tab_candidates, page, timeout_seconds=10):
            raise TimeoutError("Country tab did not appear in Location filter")

    country_input = _first_visible_locator(
        page.locator('input[placeholder="Country"], input[placeholder*="Country"]'),
        page,
        timeout_seconds=10,
        description="Country input",
    )

    for location in cleaned_locations:
        country_input.fill("")
        country_input.fill(location)
        page.wait_for_timeout(300)

        # Select the first result matching the search from the suggestion dropdown
        first_result_candidates = (
            page.locator(".suggestion-wrapper").get_by_text(
                re.compile(rf"^\s*{re.escape(location)}", re.IGNORECASE)
            ),
            page.locator(".suggestion-wrapper [role='option']"),
            page.locator(".suggestion-wrapper label"),
            page.locator(".suggestion-wrapper [class*='item']"),
            page.locator(".suggestion-wrapper [class*='suggestion']"),
            page.locator(".suggestion-wrapper > div").filter(has_text=re.compile(r"\S")),
            page.locator(".suggestion-wrapper > *").filter(has_text=re.compile(r"\S")),
            page.get_by_text(
                re.compile(
                    rf"^{re.escape(location)}.*$",
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
        page.wait_for_timeout(600)

        # Click the "All" checkbox / label to select all matching items for this search
        all_checkbox = page.locator(".top-wrapper input[type='checkbox']")
        if all_checkbox.count() > 0 and all_checkbox.first.is_checked():
            continue

        all_label_candidates = (
            page.locator(".top-wrapper label").filter(has_text=re.compile(r"^All$", re.IGNORECASE)),
            page.locator(".top-wrapper").get_by_text("All", exact=True),
            page.locator(".top-wrapper label"),
            page.locator("label").filter(has_text=re.compile(r"^All$", re.IGNORECASE)),
            page.get_by_text("All", exact=True),
        )

        if not _click_first_visible(all_label_candidates, page, timeout_seconds=5):
            if all_checkbox.count() > 0:
                try:
                    all_checkbox.first.check(force=True)
                except Exception:
                    pass

        page.wait_for_timeout(400)


def apply_employee_counts(page: Page, employee_counts: list[str]) -> None:
    if employee_counts:
        open_filter(page, "Employee Count")
        _check_options(page, employee_counts)


def apply_filters(page: Page, filters: dict, log_callback=None) -> None:
    filter_steps = (
        ("Job Title", apply_job_titles, filters.get("job_titles", [])),
        ("Location", apply_locations, filters.get("locations", [])),
        ("Industry", apply_industries, filters.get("industries", [])),
        (
            "Employee Count",
            apply_employee_counts,
            filters.get("employee_counts", []),
        ),
    )

    for filter_name, apply_filter, values in filter_steps:
        if values and log_callback:
            log_callback(
                f"Applying filter '{filter_name}': {', '.join(str(v) for v in values[:3])}"
                f"{'...' if len(values) > 3 else ''}"
            )
        try:
            apply_filter(page, values)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError(f"{filter_name} filter timed out") from exc

    if log_callback:
        log_callback("Submitting search: clicking 'See matching contacts'...")

    matching_contacts_candidates = (
        page.get_by_role(
            "button",
            name="See matching contacts",
            exact=True,
        ),
        page.get_by_text("See matching contacts", exact=True),
    )
    if not _click_first_visible(
        matching_contacts_candidates,
        page,
        timeout_seconds=30,
    ):
        raise TimeoutError("See matching contacts button did not appear")