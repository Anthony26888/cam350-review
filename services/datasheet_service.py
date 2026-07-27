import urllib.request
import urllib.parse
import ssl
import re
from typing import Optional


class DatasheetService:
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    @staticmethod
    def _fetch(url: str) -> Optional[str]:
        try:
            ctx = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers=DatasheetService._HEADERS)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    @staticmethod
    def _search_digikey(mpn: str) -> str:
        search_url = f"https://www.digikey.com/en/products/result?keywords={urllib.parse.quote(mpn)}"
        html = DatasheetService._fetch(search_url)
        if html:
            product_links = re.findall(r'href="(/en/products/detail/[^"]+)"', html)
            if product_links:
                return f"https://www.digikey.com{product_links[0]}"
        return search_url

    @staticmethod
    def _search_mouser(mpn: str) -> str:
        search_url = f"https://www.mouser.com/c/?q={urllib.parse.quote(mpn)}"
        html = DatasheetService._fetch(search_url)
        if html:
            product_links = re.findall(r'href="(/(?:\w{2}/)?ProductDetail/[^"]+)"', html)
            if product_links:
                return f"https://www.mouser.com{product_links[0]}"
        return search_url

    @staticmethod
    def _search_google(mpn: str) -> str:
        return f"https://www.google.com/search?q={urllib.parse.quote(mpn + ' datasheet')}"

    @staticmethod
    def search(mpn: str) -> str:
        if not mpn or not mpn.strip():
            return ""
        mpn = mpn.strip()
        return DatasheetService._search_digikey(mpn)
