#!/usr/bin/env python3
import os
import re
import time
import random
import argparse
import requests
import urllib.parse
import subprocess
from typing import List, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin

# ================= CONFIGURATION =================
DEFAULT_TARGET_URL = "https://www.imagefap.com/pictures/5151100/Insex%20412%20-%20LiveFeed%20Drink?gid=5151100&view=2.html"
BRAVE_PATH         = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
WAIT_TIMEOUT       = 15
ZOOM_LEVEL         = "50%"
# =================================================

XPATH_IMAGE = '/html/body/center/table[2]/tbody/tr/td[1]/table/tbody/tr/td[1]/div/center/table[2]/tbody/tr/td/table/tbody/tr/td/center/table/tbody/tr/td/div[5]/center/div[1]/span/img'
XPATH_NEXT  = '/html/body/center/table[2]/tbody/tr/td[1]/table/tbody/tr/td[1]/div/center/table/tbody/tr/td/table/tbody/tr/td/center/div[1]/font[1]/span/a[contains(text(), "next")]'


def parse_args():
    parser = argparse.ArgumentParser(description="ImageFap gallery downloader.")
    parser.add_argument(
        '--target-url',
        type=str,
        default=None,
        help=f"Gallery URL to scrape (default: {DEFAULT_TARGET_URL.replace('%', '%%')})"
    )
    parser.add_argument(
        '--test-next-navigation',
        action='store_true',
        help='Skip downloads and just test next page navigation.'
    )
    parser.add_argument(
        '--captcha-wait',
        action='store_true',
        help='Pause and wait for manual CAPTCHA/bot-protection handling before starting automation.'
    )
    parser.add_argument(
        '--url-file',
        type=str,
        default=None,
        help='Path to a file with one target gallery URL per line; processed sequentially, reusing one browser instance.'
    )
    parser.add_argument(
        '--private',
        action='store_true',
        help='Launch Brave in a private (incognito) window.'
    )
    return parser.parse_args()


def read_urls_from_file(path: str) -> List[str]:
    """Reads target URLs from a file, one per line, ignoring blank lines and '#' comments, and dropping duplicates."""
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

    seen = set()
    urls = []
    for url in lines:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    duplicate_count = len(lines) - len(urls)
    if duplicate_count:
        print(f"   🧹 Removed {duplicate_count} duplicate URL(s) from '{path}'.")

    return urls


def make_save_folder(target_url: str) -> str:
    """Generate a save folder name from the basename of the target URL."""
    path = urllib.parse.urlparse(target_url).path
    basename = os.path.basename(path.rstrip('/'))
    basename = urllib.parse.unquote(basename)
    basename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', basename)
    basename = basename.strip('. ')
    return basename or "downloaded_images"


def setup_driver(brave_path: str, headless: bool = False, private: bool = False) -> webdriver.Chrome:
    """Initializes ChromeDriver using Brave Browser."""
    options = Options()
    options.binary_location = brave_path
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless")
    if private:
        options.add_argument("--incognito")

    service = Service(log_output=subprocess.DEVNULL)
    driver = webdriver.Chrome(options=options, service=service)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def navigate(driver: webdriver.Chrome, url: str) -> None:
    """Navigates to a URL and re-applies the configured page zoom (lost on every fresh page load)."""
    driver.get(url)
    driver.execute_script(f"document.documentElement.style.zoom='{ZOOM_LEVEL}'")


def scroll_to_bottom(driver: webdriver.Chrome) -> None:
    """Scrolls to bottom to trigger lazy loading."""
    print("   Scrolling to load all thumbnails...")
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollTo(0, 0);")


def get_photo_urls(driver: webdriver.Chrome, base_url: str) -> List[Tuple[str, str]]:
    """
    Finds all photo page links and filenames from the gallery page.
    Returns a list of (url, filename) tuples.
    """
    photo_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/photo/')]")
    seen = set()
    urls = []
    for link in photo_links:
        href = link.get_attribute("href")
        if href and href not in seen:
            urls.append(urljoin(base_url, href))
            seen.add(href)

    i_elements = driver.find_elements(By.TAG_NAME, 'i')
    filenames = [
        el.text.strip()
        for el in i_elements
        if el.text.strip().lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
    ]

    print(f"   Photos found: {len(urls)}, Filenames found: {len(filenames)}")
    if filenames:
        print(f"   First filename: '{filenames[0]}'")
        print(f"   Last filename:  '{filenames[-1]}'")

    paired = []
    for i, url in enumerate(urls):
        filename = filenames[i] if i < len(filenames) else f"image_{i+1:04d}.jpg"
        paired.append((url, filename))

    return paired


def get_next_url(driver: webdriver.Chrome, current_url: str) -> str | None:
    """Finds and returns the next gallery page URL, or None if not found."""
    try:
        next_link = driver.find_element(By.XPATH, XPATH_NEXT)
        next_href = next_link.get_attribute('href')
        next_text = next_link.text.strip()
        print(f"   Next link found: '{next_text}' → {next_href}")

        if not next_href:
            print("   Next link has no href — stopping.")
            return None

        return urllib.parse.urljoin(current_url, next_href)

    except Exception as e:
        first_line = str(e).split('\n')[0]
        print(f"   No next link found: {first_line}")
        return None


def sanitize_filename(name: str) -> str:
    """Remove illegal filename characters."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name or "unnamed"


def download_single_image(
    session: requests.Session,
    img_src: str,
    save_folder: str,
    filename: str,
    referer_url: str
) -> bool:
    """Downloads a single image and saves it with the given filename."""
    try:
        safe_name = sanitize_filename(filename)

        if not re.search(r'\.(jpg|jpeg|png|gif|webp)$', safe_name, re.IGNORECASE):
            safe_name += '.jpg'

        filepath = os.path.join(save_folder, safe_name)

        if os.path.exists(filepath):
            print(f"   ⏭️  Already exists, skipping: {safe_name}")
            return False

        session.headers.update({'Referer': referer_url})
        response = session.get(img_src, timeout=30, stream=True)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        if 'image' not in content_type:
            print(f"   ⚠️  Not an image (Content-Type: {content_type}), skipping.")
            return False

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        size_kb = os.path.getsize(filepath) / 1024
        if size_kb < 1:
            os.remove(filepath)
            print(f"   ⚠️  File too small ({size_kb:.1f} KB), removed.")
            return False

        print(f"   💾 Saved: {safe_name} ({size_kb:.1f} KB)")
        return True

    except Exception as e:
        print(f"   ❌ Download error: {e}")
        return False


def test_next_navigation(driver: webdriver.Chrome, start_url: str) -> None:
    """Test-only mode: walk through all gallery pages without downloading."""
    print("\n🧪 TEST MODE: next navigation only (no downloads)\n")
    current_url = start_url
    page_num = 0
    total_photos = 0

    while True:
        page_num += 1
        print(f"{'='*60}")
        print(f"📄 Page {page_num}: {current_url}")

        navigate(driver, current_url)
        time.sleep(2)
        scroll_to_bottom(driver)

        photo_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/photo/')]")
        i_elements = [
            el for el in driver.find_elements(By.TAG_NAME, 'i')
            if el.text.strip().lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp'))
        ]

        page_photos = len(photo_links)
        total_photos += page_photos

        print(f"   Photos found: {page_photos}, Filenames found: {len(i_elements)}")
        if i_elements:
            print(f"   First filename: '{i_elements[0].text.strip()}'")
            print(f"   Last filename:  '{i_elements[-1].text.strip()}'")

        next_url = get_next_url(driver, current_url)
        if not next_url:
            print(f"\n{'='*60}")
            print(f"✅ Navigation test complete.")
            print(f"   Pages walked:  {page_num}")
            print(f"   Total photos:  {total_photos}")
            print(f"{'='*60}")
            break

        print(f"➡️  Moving to: {next_url}")
        current_url = next_url
        time.sleep(random.uniform(1, 2))


def scrape_gallery(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    target_url: str,
    test_next: bool = False,
    captcha_wait: bool = False
) -> None:
    """Scrapes a single gallery URL (and its pagination) using an already-initialized driver."""
    save_folder = make_save_folder(target_url)
    os.makedirs(save_folder, exist_ok=True)
    print(f"💾 Save folder: '{save_folder}/'")

    print(f"\nTarget URL: {target_url}")
    print(f"Navigating to gallery...")
    navigate(driver, target_url)
    time.sleep(2)

    if captcha_wait:
        print("\n" + "="*60)
        print("🤖 BOT PROTECTION: Please handle any CAPTCHAs in the browser.")
        print("   Once the gallery is loaded and visible, press [ENTER].")
        print("="*60)
        input("Press [ENTER] to start automation...")

    if test_next:
        test_next_navigation(driver, target_url)
        return

    # Sync cookies from Brave to requests session
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
    print("✅ Session cookies synchronized.")

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
    })

    total_count = 0
    page_num = 0
    current_gallery_url = target_url

    while True:
        page_num += 1
        print(f"\n{'='*60}")
        print(f"📄 Gallery page {page_num}: {current_gallery_url}")
        print(f"{'='*60}")

        navigate(driver, current_gallery_url)
        time.sleep(2)
        scroll_to_bottom(driver)

        photo_url_list = get_photo_urls(driver, current_gallery_url)

        if not photo_url_list:
            print("No photo links found on this page. Stopping.")
            break

        page_count = 0
        for i, (url, filename) in enumerate(photo_url_list):
            try:
                print(f"\n[{i+1}/{len(photo_url_list)}] Visiting: {url}")
                print(f"   📝 Filename: {filename}")
                navigate(driver, url)

                sleep_time = random.uniform(.5, 2)
                print(f"   Waiting {sleep_time:.2f}s...")
                time.sleep(sleep_time)

                primary_image = wait.until(EC.presence_of_element_located((
                    By.XPATH, XPATH_IMAGE
                )))
                img_src = primary_image.get_attribute('src')
                print(f"   🖼️  Image URL: {img_src}")

                if not img_src:
                    print("   ⚠️  No src found, skipping.")
                    continue

                if download_single_image(session, img_src, save_folder, filename, url):
                    page_count += 1

            except Exception as e:
                print(f"   ⚠️  Error on {url}: {e}")
                continue

        total_count += page_count
        print(f"\n📊 Page {page_num}: {page_count} downloaded ({total_count} total).")

        # Find next gallery page
        navigate(driver, current_gallery_url)
        time.sleep(2)

        next_url = get_next_url(driver, current_gallery_url)
        if not next_url:
            print("\n✅ All pages complete.")
            break

        current_gallery_url = next_url
        print(f"\n➡️  Next page: {current_gallery_url}")
        time.sleep(random.uniform(1, 3))

    print(f"\n✨ Done! Downloaded {total_count} images to '{save_folder}/'")


def refresh_urls_from_file(url_file: str, target_urls: List[str], last_mtime: float | None) -> float | None:
    """Re-reads url_file, logs whether it changed since last_mtime, and appends any new URLs to target_urls in place."""
    print(f"🔎 Re-reading url-file '{url_file}' for appended URLs...")
    try:
        new_mtime = os.path.getmtime(url_file)
    except OSError as e:
        print(f"   ⚠️  Could not stat url-file: {e}")
        return last_mtime

    if new_mtime == last_mtime:
        print("   ✅ url-file unchanged since last read.")
        return last_mtime

    seen = set(target_urls)
    fresh_urls = read_urls_from_file(url_file)
    new_entries = [u for u in fresh_urls if u not in seen]

    if new_entries:
        target_urls.extend(new_entries)
        print(f"   📥 url-file updated since last read — added {len(new_entries)} new URL(s) to the queue.")
    else:
        print("   ℹ️  url-file updated since last read, but no new URLs found.")

    return new_mtime


def run_scraper(
    target_urls: List[str],
    test_next: bool = False,
    captcha_wait: bool = False,
    url_file: str | None = None,
    private: bool = False
) -> None:
    """Main orchestrator: processes one or more gallery URLs sequentially, reusing a single browser instance."""
    driver = setup_driver(BRAVE_PATH, private=private)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    target_urls = list(target_urls)
    last_mtime = os.path.getmtime(url_file) if url_file else None

    try:
        i = 0
        while i < len(target_urls):
            target_url = target_urls[i]
            print(f"\n{'#'*60}")
            print(f"# Target {i+1}/{len(target_urls)}: {target_url}")
            print(f"{'#'*60}")
            try:
                scrape_gallery(driver, wait, target_url, test_next=test_next, captcha_wait=captcha_wait and i == 0)
            except Exception as err:
                print(f"\n❌ Error processing {target_url}: {err}")

            if url_file:
                last_mtime = refresh_urls_from_file(url_file, target_urls, last_mtime)

            i += 1

    finally:
        print("Closing browser...")
        driver.quit()


if __name__ == "__main__":
    args = parse_args()

    if args.url_file:
        target_urls = read_urls_from_file(args.url_file)
        print(f"Using --url-file: {args.url_file} ({len(target_urls)} URLs)")
    elif args.target_url:
        target_urls = [args.target_url]
        print(f"Using --target-url: {args.target_url}")
    else:
        target_urls = [DEFAULT_TARGET_URL]
        print(f"Using default URL: {DEFAULT_TARGET_URL}")

    run_scraper(
        target_urls=target_urls,
        test_next=args.test_next_navigation,
        captcha_wait=args.captcha_wait,
        url_file=args.url_file,
        private=args.private
    )