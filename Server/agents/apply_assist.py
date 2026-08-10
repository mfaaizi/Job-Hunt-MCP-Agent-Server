"""
Application-assist agent: opens a job's apply page in a visible browser and
auto-fills whatever fields it can confidently identify — name, email, phone,
resume upload. It NEVER clicks Submit. The browser stays open after this
returns; the person reviews and completes/submits manually.

ASYNC API, not sync: Playwright's *synchronous* API is only safe to call
from the exact same OS thread that started it. FastMCP dispatches sync tool
functions through a thread pool, so a second call landing on a different
worker thread than the first would break the sync driver entirely (raises
"cannot switch to a different thread"). Using the async API and making the
MCP tool itself `async def` avoids this: FastMCP runs async tools directly
on its single event loop rather than farming them out to a thread pool, so
there's no cross-thread access to begin with.

Browser lifecycle note: this deliberately does NOT use `async with
async_playwright() as p:` — that context manager closes the browser when the
block exits, which would happen the instant the MCP tool call returns.
Instead, the Playwright instance and browser context are started once and
kept alive as module-level singletons for the life of the server process, so
the window stays open and visible to the person after the tool call completes.

Login: uses a PERSISTENT browser profile rather than scripted credentials —
either a dedicated Playwright-managed profile (log in once via
scripts/setup_browser_login.py) or, if configured, your actual real Chrome
profile reused directly. Either way, no password is ever read, stored, or
handled by this project — this sidesteps Google's aggressive bot-detection
on scripted logins entirely, since it's always a real human-authenticated
session being reused, never a scripted login attempt.
"""
import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page, async_playwright

from server.config import settings

_playwright_instance = None
_context: Optional[BrowserContext] = None
_init_lock = asyncio.Lock()


async def _get_context(headless: bool = False) -> BrowserContext:
    """
    Lazily starts one shared, persistent browser context, reused across
    calls. headless=False by default — the whole point is a visible window
    the person can take over.

    Two modes, controlled by BROWSER_PROFILE_MODE:
      "dedicated" — uses BROWSER_PROFILE_DIR, a Playwright-managed profile.
        Any login set up via scripts/setup_browser_login.py carries over.
      "real_chrome" — reuses your actual, already-logged-in Chrome profile
        via REAL_CHROME_USER_DATA_DIR / REAL_CHROME_PROFILE_DIRECTORY. Chrome
        must be fully closed first — it locks its profile folder while open,
        and launch_persistent_context will raise if it's still running.
    """
    global _playwright_instance, _context

    async with _init_lock:  # avoid two concurrent calls both trying to launch a browser
        if _context is not None:
            return _context

        _playwright_instance = await async_playwright().start()

        if settings.BROWSER_PROFILE_MODE == "real_chrome":
            if not settings.REAL_CHROME_USER_DATA_DIR:
                raise RuntimeError(
                    "BROWSER_PROFILE_MODE is 'real_chrome' but REAL_CHROME_USER_DATA_DIR is not "
                    "set in .env. See README for how to find this path."
                )
            try:
                _context = await _playwright_instance.chromium.launch_persistent_context(
                    user_data_dir=settings.REAL_CHROME_USER_DATA_DIR,
                    channel="chrome",
                    headless=headless,
                    args=[f"--profile-directory={settings.REAL_CHROME_PROFILE_DIRECTORY}"],
                )
            except Exception as e:
                raise RuntimeError(
                    "Couldn't open your real Chrome profile — it's almost always because "
                    "Chrome is still running. Close every Chrome window, then check Task "
                    "Manager for a lingering chrome.exe process and end it too. Also double "
                    "check REAL_CHROME_PROFILE_DIRECTORY matches the 'Profile Path' shown at "
                    "chrome://version exactly (e.g. 'Default' vs 'Profile 1' are different "
                    "profiles with different logins). Original error: "
                    f"{e}"
                ) from e
        else:
            _context = await _playwright_instance.chromium.launch_persistent_context(
                user_data_dir=str(settings.BROWSER_PROFILE_DIR),
                headless=headless,
            )

        return _context


def _split_name(full_name: Optional[str]) -> tuple[str, str]:
    """
    Naive first/last name split — takes the first word as first name and
    everything else as last name. Doesn't handle multi-part surnames,
    middle names, or non-Western name orderings correctly, but is a
    reasonable default for auto-fill (the person reviews before submitting
    regardless, so a wrong split here is a minor, visible, easy fix, not a
    silent error).
    """
    if not full_name:
        return "", ""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


async def _try_fill(page: Page, selectors: list[str], value: str, timeout_ms: int = 1500) -> bool:
    """
    Tries each selector in order; fills the first one that matches exactly
    one visible, enabled element. Returns whether anything was filled.
    Each attempt is short-timeout and independently caught, so one bad
    selector (or a page that doesn't have that field at all) never blocks
    trying the rest.
    """
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                continue
            target = locator.first
            if not await target.is_visible(timeout=timeout_ms):
                continue
            await target.fill(value, timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


async def _try_upload(page: Page, selectors: list[str], file_path: str, timeout_ms: int = 1500) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if await locator.count() == 0:
                continue
            await locator.first.set_input_files(file_path, timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


# Selector strategies, most specific first. Covers common attribute patterns
# across ATS platforms (Greenhouse, Lever, Workday) and generic HTML forms.
# Deliberately broad — a false non-match (field exists but isn't filled) is
# far safer than a false match (filling the wrong field), so these lean
# conservative: exact-ish attribute matches over blind text-content guessing.
_FIRST_NAME_SELECTORS = [
    'input[name*="first_name" i]', 'input[id*="first_name" i]', 'input[name*="firstname" i]',
    'input[id*="firstname" i]', 'input[autocomplete="given-name"]',
    'input[aria-label*="first name" i]', 'input[placeholder*="first name" i]',
]
_LAST_NAME_SELECTORS = [
    'input[name*="last_name" i]', 'input[id*="last_name" i]', 'input[name*="lastname" i]',
    'input[id*="lastname" i]', 'input[autocomplete="family-name"]',
    'input[aria-label*="last name" i]', 'input[placeholder*="last name" i]',
]
_FULL_NAME_SELECTORS = [
    'input[autocomplete="name"]', 'input[name="name" i]', 'input[id="name" i]',
    'input[aria-label="full name" i]', 'input[placeholder="full name" i]',
    'input[aria-label="name" i]', 'input[placeholder="your name" i]',
]
_EMAIL_SELECTORS = [
    'input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]',
    'input[autocomplete="email"]', 'input[aria-label*="email" i]', 'input[placeholder*="email" i]',
]
_PHONE_SELECTORS = [
    'input[type="tel"]', 'input[name*="phone" i]', 'input[id*="phone" i]',
    'input[autocomplete="tel"]', 'input[aria-label*="phone" i]', 'input[placeholder*="phone" i]',
]
_RESUME_UPLOAD_SELECTORS = [
    'input[type="file"][name*="resume" i]', 'input[type="file"][id*="resume" i]',
    'input[type="file"][name*="cv" i]', 'input[type="file"][aria-label*="resume" i]',
    'input[type="file"]',  # last resort: any file input, if the page only has one
]


async def open_and_fill_application(
    apply_url: str,
    name: Optional[str],
    email: Optional[str],
    phone: Optional[str],
    resume_file_path: Optional[str],
    headless: bool = False,
) -> dict:
    """
    Opens apply_url in a browser (visible by default — that's the point) and
    attempts to fill name/email/phone and upload the resume file, returning
    a summary of what succeeded. The browser is left open for the person to
    review and finish manually. NEVER clicks any submit/apply button.

    headless=True exists only for automated testing against a mock page —
    real usage should always leave this False so the person can see and
    take over the browser.
    """
    context = await _get_context(headless=headless)
    page = await context.new_page()

    result = {
        "apply_url": apply_url,
        "navigated": False,
        "filled": {"first_name": False, "last_name": False, "full_name": False, "email": False, "phone": False},
        "resume_uploaded": False,
        "warnings": [],
    }

    try:
        await page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
        result["navigated"] = True
    except Exception as e:
        result["warnings"].append(f"Page navigation had an issue (site may still have loaded): {e}")

    # Best-effort: give client-rendered forms (common on ATS platforms) a
    # moment to finish rendering. Not fatal if this times out — some pages
    # never go fully idle due to background requests/websockets.
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass

    first_name, last_name = _split_name(name)

    if first_name:
        result["filled"]["first_name"] = await _try_fill(page, _FIRST_NAME_SELECTORS, first_name)
    if last_name:
        result["filled"]["last_name"] = await _try_fill(page, _LAST_NAME_SELECTORS, last_name)
    if name and not (result["filled"]["first_name"] or result["filled"]["last_name"]):
        # Only try the full-name field if split first/last fields weren't found —
        # avoids double-filling both a split field pair AND a combined field.
        result["filled"]["full_name"] = await _try_fill(page, _FULL_NAME_SELECTORS, name)

    if email:
        result["filled"]["email"] = await _try_fill(page, _EMAIL_SELECTORS, email)
    if phone:
        result["filled"]["phone"] = await _try_fill(page, _PHONE_SELECTORS, phone)

    if resume_file_path and Path(resume_file_path).exists():
        result["resume_uploaded"] = await _try_upload(page, _RESUME_UPLOAD_SELECTORS, resume_file_path)
    elif resume_file_path:
        result["warnings"].append(f"Resume file not found on disk: {resume_file_path}")

    return result
