"""Download every ICAR-CRIDA District Agriculture Contingency Plan (DACP) PDF.

Scrapes the state/district index at https://www.icar-crida.res.in/Crop_Contingency_Plan.html
(the HTML is malformed -- many `<a>` tags are never closed -- so this uses a tolerant
sequential scan rather than a strict HTML parser) and downloads every linked PDF into
`data/raw/<State>/<original-filename>.pdf`.

Usage:
    uv run python scripts/download_dacp.py [--workers 12] [--dest data/raw]

Idempotent: existing valid PDFs (non-empty, `%PDF` magic) are skipped. Safe to re-run to
pick up documents ICAR-CRIDA adds or renames later.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlparse

INDEX_URL = "https://www.icar-crida.res.in/Crop_Contingency_Plan.html"
USER_AGENT = "Mozilla/5.0 (ankur-dacp-downloader)"

# Sequential scan: a state header (`href="#collapseNN">State<`) followed by any number of
# PDF anchors belongs to that state, until the next header. Tolerates missing `</a>`.
_TOKEN_RE = re.compile(
    r'href="#collapse\w+"[^>]*>\s*(?P<state>[^<]+?)\s*<'
    r'|<a\s+href="(?P<href>[^"]+\.pdf)"[^>]*>(?P<text>[^<]*)',
    re.IGNORECASE,
)


def fetch_index(url: str = INDEX_URL) -> str:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "30", "-A", USER_AGENT, url],
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8", errors="ignore")


def parse_index(page_html: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    current_state: str | None = None
    for match in _TOKEN_RE.finditer(page_html):
        if match.group("state"):
            current_state = html.unescape(match.group("state").strip())
            continue
        href = html.unescape(match.group("href").strip())
        district = html.unescape(match.group("text").strip()).strip(" |")
        url = urljoin(INDEX_URL, href)
        if url in seen_urls or current_state is None:
            continue
        seen_urls.add(url)
        entries.append({"state": current_state, "district": district, "url": url})
    return entries


def _slugify(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name.strip().replace(" ", "_"))


def dest_for(entry: dict[str, str], dest_root: Path) -> Path:
    state_dir = _slugify(entry["state"])
    filename = _slugify(unquote(Path(urlparse(entry["url"]).path).name))
    return dest_root / state_dir / filename


def download_one(entry: dict[str, str], dest_root: Path) -> tuple[str, str]:
    dest = dest_for(entry, dest_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000 and dest.read_bytes()[:4] == b"%PDF":
        return str(dest), "exists"

    tmp = dest.with_suffix(dest.suffix + ".part")

    def try_fetch(url: str) -> bool:
        try:
            subprocess.run(
                [
                    "curl", "-sL", "--max-time", "45", "--retry", "2", "--retry-delay", "1",
                    "-A", USER_AGENT, "-o", str(tmp), quote(url, safe=":/%?&=,;+@")
                ],
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # curl's own --max-time should make this rare, but a hung/very slow
            # connection (e.g. cluster egress to a specific host) can still outlive
            # the outer subprocess timeout -- one bad file must not crash the whole
            # ThreadPoolExecutor batch (see the icar-crida.res.in cluster-egress
            # timeout this was written for).
            return False
        return tmp.exists() and tmp.stat().st_size > 1000 and tmp.read_bytes()[:4] == b"%PDF"

    url = entry["url"]
    # The server's directory casing is inconsistent with the index page's links for a
    # handful of documents (case-sensitive IIS backend); retry with a lowercased
    # directory component before giving up.
    ok = try_fetch(url)
    if not ok:
        parsed = urlparse(url)
        directory, _, filename = parsed.path.rpartition("/")
        lowered = parsed._replace(path=f"{directory.lower()}/{filename}")
        if lowered.geturl() != url:
            ok = try_fetch(lowered.geturl())
    if ok:
        tmp.replace(dest)
        return str(dest), "ok"
    tmp.unlink(missing_ok=True)
    return str(dest), "fail"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("data/raw"))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    entries = parse_index(fetch_index())
    print(f"Found {len(entries)} DACP PDFs across "
          f"{len({e['state'] for e in entries})} states.")

    results: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, e, args.dest): e for e in entries}
        for future in as_completed(futures):
            results.append(future.result())

    ok = sum(1 for _, status in results if status == "ok")
    exists = sum(1 for _, status in results if status == "exists")
    failed = [dest for dest, status in results if status == "fail"]
    print(f"Downloaded {ok} new, {exists} already present, {len(failed)} failed.")
    for dest in failed:
        print(f"  FAILED: {dest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
