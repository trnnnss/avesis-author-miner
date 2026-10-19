"""AVESİS HTML adaptörü. Tarama eğitimden bağımsızdır."""

import logging
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .data import clean_records, load_records, save_records

LOGGER = logging.getLogger(__name__)
USER_AGENT = "AvesisMiner/1.0"
RESERVED = {
    "arama",
    "search",
    "login",
    "account",
    "api",
    "content",
    "assets",
    "yayinlar",
    "publications",
    "robots.txt",
    "favicon.ico",
    "home",
    "research",
    "researcher",
    "tr",
    "en",
}


def publication_url(url):
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Geçerli bir HTTP(S) profil bağlantısı gerekli.")
    segments = parsed.path.strip("/").split("/")
    if len(segments) == 2 and segments[1].lower() == "yayinlar":
        segments = segments[:1]
    if len(segments) != 1 or not re.fullmatch(r"[\w.-]+", segments[0]) or segments[0].lower() in RESERVED:
        raise ValueError(f"AVESİS profil adresi bekleniyordu: {url}")
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{segments[0]}/yayinlar", "", ""))


class Client:
    def __init__(self, delay=1.0, timeout=20):
        if delay < 0.5 or timeout <= 0:
            raise ValueError("delay en az 0.5 saniye, timeout pozitif olmalı.")
        self.delay, self.timeout = delay, timeout
        self.session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers["User-Agent"] = USER_AGENT
        self.robots, self.last_request = {}, {}

    def close(self):
        self.session.close()

    def _request(self, url, delay):
        host = urlsplit(url).netloc
        elapsed = time.monotonic() - self.last_request.get(host, 0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        try:
            # Redirectler ayrıca robots kontrolünden geçirilir.
            return self.session.get(url, timeout=self.timeout, allow_redirects=False)
        finally:
            self.last_request[host] = time.monotonic()

    def get(self, url, redirects=0):
        if redirects > 5:
            raise ValueError("Çok fazla yönlendirme.")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Geçersiz HTTP(S) adresi.")
        origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        if origin not in self.robots:
            robots_url = origin + "/robots.txt"
            response = self._request(robots_url, self.delay)
            parser = RobotFileParser(robots_url)
            if response.status_code == 404:
                parser.parse([])
            elif response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                raise ValueError(f"robots.txt okunamadı (HTTP {response.status_code}): {origin}")
            self.robots[origin] = parser
        parser = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise ValueError(f"robots.txt taramaya izin vermiyor: {url}")
        delay = max(self.delay, parser.crawl_delay(USER_AGENT) or 0)
        response = self._request(url, delay)
        if response.is_redirect:
            return self.get(urljoin(url, response.headers["Location"]), redirects + 1)
        response.raise_for_status()
        return response


def parse_publications(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    items = soup.select("div.pub-item")
    for item in items:
        title = item.find("strong")
        authors = item.select("a.authorsRichText")
        if not title or not authors:
            continue
        title_text = title.get_text(" ", strip=True)
        names = [a.get_text(" ", strip=True) for a in authors if a.get_text(" ", strip=True)]
        if title_text and names:
            rows.append(
                {
                    "title": title_text,
                    "author": names[0],
                    "authors": " | ".join(names),
                    "source_url": source_url,
                }
            )
    pages = []
    current = urlsplit(source_url)
    for anchor in soup.select("a[href]"):
        candidate = urljoin(source_url, anchor["href"])
        parsed = urlsplit(candidate)
        if (
            parsed.netloc == current.netloc
            and parsed.path.rstrip("/") == current.path.rstrip("/")
            and parsed.query
            and not parsed.fragment
        ):
            if re.search(r"(?:^|&)(?:page|p|sayfa|pageno|pagenumber)=\d+(?:&|$)", parsed.query, re.I):
                pages.append(candidate)
    return rows, list(dict.fromkeys(pages)), len(items)


def scrape(links, output, *, max_pages=10, max_publications=0, delay=1.0, timeout=20, client=None):
    if max_pages < 1 or max_publications < 0:
        raise ValueError("max-pages pozitif, max-publications sıfır veya pozitif olmalı.")
    # URL hatası, herhangi bir ağ isteğinden önce gösterilir.
    targets = list(dict.fromkeys(publication_url(link) for link in links))
    output = Path(output)
    existing = load_records(output) if output.exists() else pd.DataFrame(columns=["title", "author"])
    rows, results = [], []
    own_client = client is None
    client = client or Client(delay=delay, timeout=timeout)
    try:
        for target in targets:
            queue, visited, profile_rows = deque([target]), set(), []
            errors = []
            discovered = {target}
            while queue and len(visited) < max_pages:
                url = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                try:
                    response = client.get(url)
                    page_rows, pages, item_count = parse_publications(response.text, response.url)
                    if item_count == 0:
                        errors.append(
                            f"Yayın HTML öğesi bulunamadı: {url}; boş profil, dinamik yükleme veya farklı sayfa yapısı olabilir."
                        )
                    elif not page_rows:
                        errors.append(f"Yayın öğelerinden başlık ve ilk yazar okunamadı: {url}")
                    profile_rows.extend(page_rows)
                    for page in pages:
                        if page not in discovered:
                            discovered.add(page)
                            queue.append(page)
                    if max_publications and len(profile_rows) >= max_publications:
                        profile_rows = profile_rows[:max_publications]
                        break
                except (requests.RequestException, ValueError) as exc:
                    errors.append(str(exc))
            rows.extend(profile_rows)
            for error in errors:
                LOGGER.warning("%s", error)
            results.append(
                {
                    "profile": target,
                    "pages": len(visited),
                    "records": len(profile_rows),
                    "page_limit_reached": bool(queue and len(visited) >= max_pages),
                    "errors": errors,
                }
            )
            LOGGER.info("%s: %d kayıt", target, len(profile_rows))
    finally:
        if own_client:
            client.close()
    if not rows:
        raise ValueError(
            "Hiç yayın okunamadı. Mevcut veri dosyası değiştirilmedi; bağlantıları ve tarama uyarılarını kontrol edin."
        )
    combined = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    # Çelişkiler ham veride korunur; eğitim temizleyicisi bunları ayırıp raporlar.
    combined = combined.drop_duplicates(subset=["title", "author"], keep="first")
    save_records(combined, output)
    _, quality = clean_records(combined)
    return {"profiles": results, "fetched_rows": len(rows), "saved_rows": len(combined), "quality": quality}


def discover_profiles(html, page_url):
    """Yalnızca HTML içinde gerçekten bulunan aynı alan adındaki profil bağlantıları."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for anchor in soup.select("a[href]"):
        url = urljoin(page_url, anchor["href"])
        if urlsplit(url).netloc != urlsplit(page_url).netloc:
            continue
        try:
            links.add(publication_url(url).removesuffix("/yayinlar"))
        except ValueError:
            continue
    return sorted(links)
