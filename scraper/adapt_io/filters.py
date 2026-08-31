import re
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


def open_prospect_search(page: Page) -> None:
    candidates = (
        page.get_by_role("button", name="Prospect Search", exact=True),
        page.get_by_role("link", name="Prospect Search", exact=True),
        page.get_by_text("Prospect Search", exact=True),
    )

    if not _click_first_visible(candidates, page, timeout_seconds=60):
        raise TimeoutError("Prospect Search did not appear after login")


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
    if not _click_first_visible(
        (page.get_by_text(filter_name, exact=True),),
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

    open_filter(page, "Location")
    location_input = page.get_by_placeholder("City", exact=True)

    for location in locations:
        location_input.fill(location)
        if not _click_first_visible(
            (
                page.get_by_text(
                    re.compile(
                        rf"^{re.escape(location.strip())}.*$",
                        re.IGNORECASE,
                    ),
                ),
            ),
            page,
            timeout_seconds=5,
        ):
            continue


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
    if industries:
        open_filter(page, "Industry")
        _check_options(page, industries)


def apply_employee_counts(page: Page, employee_counts: list[str]) -> None:
    if employee_counts:
        open_filter(page, "Employee Count")
        _check_options(page, employee_counts)


def apply_filters(page: Page, filters: dict) -> None:
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
        try:
            apply_filter(page, values)
        except PlaywrightTimeoutError as exc:
            raise TimeoutError(f"{filter_name} filter timed out") from exc

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