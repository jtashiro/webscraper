# webscraper

A Selenium + `requests` based image-gallery downloader, built for sites (e.g. imagefap.com) that gate access behind a CAPTCHA/bot-protection check and paginate large galleries.

The browser (Selenium + Brave) is used to load pages, pass any bot-protection challenge, and locate photo/image links. Once authenticated, cookies are copied into a `requests.Session` so bulk image downloads happen over plain HTTP instead of the browser, which is much faster.

## Files

- **imagefap-scraper.py** — The scraper. CLI-driven, paginates through gallery pages automatically, sanitizes filenames, skips files already downloaded, and validates downloaded content (rejects non-image responses and truncated/error-page downloads).
- **\*.txt** (e.g. `cuffs.txt`, `pierced and chastity.txt`) — Plain lists of gallery URLs, one per line; pass any of them to `--url-file` to process them all in one run.

## Requirements

- Python 3.10+
- `selenium`, `requests`
- Brave Browser installed (default expected path is set in `BRAVE_PATH` near the top of the script — update it if your install location differs)
- A matching `chromedriver` available on your `PATH` (Brave is Chromium-based)

Install dependencies:

```bash
pip install selenium requests
```

## Usage

```bash
python3 imagefap-scraper.py [--target-url URL] [--url-file FILE] [--test-next-navigation] [--captcha-wait]
```

- `--target-url` — Gallery URL to scrape. Defaults to the URL hardcoded in `DEFAULT_TARGET_URL`.
- `--url-file` — Path to a text file with one gallery URL per line (blank lines and `#`-comments ignored, e.g. `cuffs.txt`). All URLs are processed sequentially, reusing a single browser instance instead of relaunching one per gallery. Takes precedence over `--target-url`.
- `--test-next-navigation` — Dry run: walks through all gallery pages via the "next" link and reports photo/filename counts per page, without downloading anything.
- `--captcha-wait` — Pause after each gallery's initial page load and wait for `[ENTER]` before continuing, so you can manually solve a CAPTCHA or other bot-protection challenge in the browser window. Omit this flag to run unattended on sites that don't challenge you.

Downloaded images are saved to a folder named after each gallery URL's path (e.g. a gallery at `.../pictures/5151100/My%20Gallery` saves to `My Gallery/`).

## Notes

- A custom `User-Agent` and the page `Referer` are set on outgoing image requests to look like normal browser traffic.
- `Object.defineProperty(navigator, 'webdriver', ...)` and Chrome's automation-related options are disabled/masked to reduce automation detection.
- Only use this against sites and content you have the right to access and download.
