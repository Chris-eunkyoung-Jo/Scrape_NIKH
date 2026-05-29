#-*-coding:utf-8-*-
# 2026.05. 
# Author: GPT-5.0 (with human guidance)
# This script scrapes articles from the "ma_007" root level on db.history.go
import argparse
import csv
import re
import time
from collections import deque

import requests
from bs4 import BeautifulSoup


LEVEL_ENDPOINT = "https://db.history.go.kr/modern/level.do"

OUT_FIELDS = ["source_url", "vol", "date", "title", "genre", "body"]

# Korean label -> output column -> flexible regex for the label
LABELS = [
    ("잡지명", "vol", r"잡\s*지\s*명"),
    ("발행일", "date", r"발\s*행\s*일"),
    ("기사제목", "title", r"기\s*사\s*제\s*목"),
    ("기사형태", "genre", r"기\s*사\s*형\s*태"),
]

MAX_META_LEN = {
    "vol": 120,
    "date": 80,
    "title": 300,
    "genre": 100,
}

BODY_SELECTORS = [
    ".view_cont",
    ".viewCon",
    ".view_con",
    ".viewContent",
    ".view_content",
    ".view_txt",
    ".viewTxt",
    ".view_text",
    ".article_cont",
    ".article_content",
    ".article_body",
    ".articleBody",
    ".articleText",
    ".article_text",
    ".cont_view",
    ".content_view",
    ".detail_content",
    ".detail_cont",
    "#articleText",
    "#article_text",
    "#viewContent",
    "#view_content",
    "#content_text",
    "#contents_body",
    "article",
    "#contents",
    "#content",
]


def make_level_url(level_id: str) -> str:
    return f"{LEVEL_ENDPOINT}?levelId={level_id}"


def normalize_text(text: str) -> str:
    """Remove newlines/tabs and collapse whitespace to single spaces."""
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_value(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"^[\s:：\-–—|/]+", "", value)
    value = re.sub(r"[\s:：\-–—|/]+$", "", value)
    return value.strip()


def label_count(text: str) -> int:
    return sum(1 for _, _, pat in LABELS if re.search(pat, text))


def add_meta(result: dict, key: str, value: str) -> None:
    value = clean_value(value)
    if not value:
        return

    # Skip values that are just another label.
    for _, _, pat in LABELS:
        if re.fullmatch(pat + r"\s*[:：]?", value):
            return

    if len(value) > MAX_META_LEN[key]:
        return

    if not result.get(key):
        result[key] = value


def parse_label_runs(text: str, result: dict) -> None:
    """
    Parse strings like:
    '잡지명 태극학보 제1호 발행일 1906년 08월 24일 기사제목 ... 기사형태 논설'
    """
    text = normalize_text(text)
    if not text:
        return

    matches = []
    for kr_label, key, pat in LABELS:
        for m in re.finditer(pat + r"\s*[:：]?", text):
            matches.append((m.start(), m.end(), key))

    if not matches:
        return

    matches.sort(key=lambda x: x[0])

    for i, (_, end, key) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        value = text[end:next_start]
        add_meta(result, key, value)


def extract_metadata(soup: BeautifulSoup) -> dict:
    result = {key: "" for _, key, _ in LABELS}

    # 1) Table rows: th/td pairs or full row text
    for tr in soup.find_all("tr"):
        row_text = normalize_text(tr.get_text(" ", strip=True))
        if 0 < len(row_text) < 1000 and label_count(row_text):
            parse_label_runs(row_text, result)

        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])

        for i, cell in enumerate(cells):
            cell_text = normalize_text(cell.get_text(" ", strip=True))
            if not cell_text:
                continue

            for _, key, pat in LABELS:
                # Case: <th>잡지명</th><td>태극학보 제1호</td>
                if re.fullmatch(pat + r"\s*[:：]?", cell_text):
                    if i + 1 < len(cells):
                        add_meta(result, key, cells[i + 1].get_text(" ", strip=True))

                # Case: <td>잡지명 태극학보 제1호</td>
                m = re.search(pat + r"\s*[:：]?\s*(.+)$", cell_text)
                if m:
                    add_meta(result, key, m.group(1))

    # 2) dl/dt/dd layout
    for dt in soup.find_all("dt"):
        dt_text = normalize_text(dt.get_text(" ", strip=True))
        for _, key, pat in LABELS:
            if re.fullmatch(pat + r"\s*[:：]?", dt_text):
                dd = dt.find_next_sibling("dd")
                if dd:
                    add_meta(result, key, dd.get_text(" ", strip=True))

    # 3) Small text blocks such as li/span/div
    for tag in soup.find_all(["li", "p", "span", "div"]):
        # Avoid parsing huge parent containers.
        if tag.name == "div" and tag.find(["table", "dl", "ul", "ol", "li", "p", "div"]):
            continue

        text = normalize_text(tag.get_text(" ", strip=True))
        if 0 < len(text) < 900 and label_count(text):
            parse_label_runs(text, result)

    return result


def flexible_value_pattern(value: str) -> str:
    parts = normalize_text(value).split()
    return r"\s+".join(re.escape(p) for p in parts)


def clean_body_text(text: str, meta: dict) -> str:
    text = normalize_text(text)

    # Remove metadata phrases if they leaked into the body candidate.
    for _, key, label_pat in LABELS:
        value = meta.get(key, "")
        if value:
            value_pat = flexible_value_pattern(value)
            text = re.sub(
                label_pat + r"\s*[:：]?\s*" + value_pat,
                " ",
                text,
                count=3,
            )

    return normalize_text(text)


def link_text_ratio(tag) -> float:
    total = len(normalize_text(tag.get_text(" ", strip=True)))
    if total == 0:
        return 0.0
    link_total = sum(
        len(normalize_text(a.get_text(" ", strip=True))) for a in tag.find_all("a")
    )
    return link_total / total


def make_body_soup(soup: BeautifulSoup) -> BeautifulSoup:
    work = BeautifulSoup(str(soup), "lxml")

    for tag in work.find_all(["script", "style", "noscript", "iframe", "form", "header", "footer", "nav"]):
        tag.decompose()

    remove_selectors = [
        ".gnb",
        "#gnb",
        ".lnb",
        "#lnb",
        ".breadcrumb",
        ".location",
        ".path",
        ".paging",
        ".pagination",
        ".btn_area",
        ".button",
        ".search",
        ".searchArea",
        ".tree",
        "#tree",
        ".sidebar",
        "#sidebar",
        "#left",
    ]

    for selector in remove_selectors:
        for tag in work.select(selector):
            tag.decompose()

    # Remove metadata tables/lists.
    for tag in list(work.find_all(["table", "dl"])):
        text = normalize_text(tag.get_text(" ", strip=True))
        if label_count(text) >= 1:
            tag.decompose()

    for tag in list(work.find_all(["ul", "ol"])):
        text = normalize_text(tag.get_text(" ", strip=True))
        if label_count(text) >= 2:
            tag.decompose()

    return work


def body_after_last_metadata(soup: BeautifulSoup, meta: dict) -> str:
    full = normalize_text(soup.get_text(" ", strip=True))
    ends = []

    for _, key, label_pat in LABELS:
        value = meta.get(key, "")
        if not value:
            continue

        value_pat = flexible_value_pattern(value)
        pattern = label_pat + r"\s*[:：]?\s*" + value_pat

        for m in re.finditer(pattern, full):
            ends.append(m.end())

    if not ends:
        return ""

    candidate = full[max(ends):]
    candidate = clean_body_text(candidate, meta)
    return candidate if len(candidate) >= 30 else ""


def extract_body(soup: BeautifulSoup, meta: dict) -> str:
    work = make_body_soup(soup)

    # Try known body/content containers first.
    for selector in BODY_SELECTORS:
        candidates = []
        for tag in work.select(selector):
            text = clean_body_text(tag.get_text(" ", strip=True), meta)
            if len(text) >= 30 and link_text_ratio(tag) < 0.60:
                candidates.append(text)

        if candidates:
            return max(candidates, key=len)

    # Fallback: join paragraph text.
    paragraphs = []
    for p in work.find_all("p"):
        text = clean_body_text(p.get_text(" ", strip=True), meta)
        if len(text) > 2 and label_count(text) == 0:
            paragraphs.append(text)

    paragraph_text = normalize_text(" ".join(paragraphs))
    if len(paragraph_text) >= 30:
        return paragraph_text

    # Fallback: longest div/section/article with low link ratio.
    block_candidates = []
    for tag in work.find_all(["article", "section", "div"]):
        text = clean_body_text(tag.get_text(" ", strip=True), meta)
        if len(text) >= 30 and link_text_ratio(tag) < 0.60:
            block_candidates.append(text)

    if block_candidates:
        return max(block_candidates, key=len)

    # Last fallback: slice full page text after metadata.
    return body_after_last_metadata(soup, meta)


def is_possible_article_level(level_id: str) -> bool:
    # Example article URL: ma_007_0010_0010
    # Root: ma_007
    # Issue: ma_007_0010
    return len(level_id.split("_")) >= 4


def parse_article_page(level_id: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")

    meta = extract_metadata(soup)

    required = ["vol", "date", "title", "genre"]
    if not all(meta.get(k) for k in required):
        return None

    body = extract_body(soup, meta)
    if not body:
        return None

    return {
        "_level_id": level_id,
        "source_url": make_level_url(level_id),
        "vol": meta["vol"],
        "date": meta["date"],
        "title": meta["title"],
        "genre": meta["genre"],
        "body": body,
    }


def discover_level_ids(html: str, root_id: str) -> set[str]:
    """
    Discover levelIds such as:
    ma_007
    ma_007_0010
    ma_007_0010_0010
    """
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(root_id)
        + r"(?:_\d{4})*"
        + r"(?![A-Za-z0-9_])"
    )
    return set(m.group(0) for m in pattern.finditer(html))


def level_sort_key(level_id: str):
    key = []
    for part in level_id.split("_"):
        key.append(int(part) if part.isdigit() else part)
    return key


def fetch(session: requests.Session, url: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                return None

            if not r.encoding or r.encoding.lower() in {"iso-8859-1", "ascii"}:
                r.encoding = r.apparent_encoding or "utf-8"

            return r.text

        except requests.RequestException:
            if attempt == retries:
                return None
            time.sleep(1.5 * attempt)

    return None


def scrape(root_id: str, out_csv: str, delay: float) -> None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 AppleWebKit/537.36 "
                "KHTML, like Gecko Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }
    )

    queue = deque([root_id])
    scheduled = {root_id}
    visited = set()
    rows = []
    seen_source_urls = set()
    issue_urls = []

    while queue:
        level_id = queue.popleft()
        if level_id in visited:
            continue

        visited.add(level_id)
        url = make_level_url(level_id) #JEK, https://db.history.go.kr/modern/level.do?levelId=ma_007_0020' => https://db.history.go.kr/modern/level.do?levelId=ma_007_0020_0010
        print(f"[issue] {url}")
        issue_urls.add(url)

        html = fetch(session, url)# one more delpth level ids needed to be discovered before scraping article page, because some metadata is only visible in issue level page, not in article level page. so we need to discover all possible level ids first, then scrape article pages after that.
        if not html:
            print(f"[skip] fetch failed: {url}")
            continue

        found_ids = discover_level_ids(html, root_id)
        #JEKinstead of activeX work, add id affixes temporarily to discover article level ids. 
        '''found_issue_ids = discover_level_ids(html, root_id)
        #found_ids = set()
        for issue_id in found_issue_ids:
            for affix in range(1, 50): 
                affix_id = format(affix*10, "04d")
                article_id = issue_id + '_' +affix_id # add article level affix to issue level id to get article level id. this is a temporary workaround until we can figure out how to trigger activeX and discover article level ids properly.
                found_ids.add(article_id)
        '''
        for found_id in sorted(found_ids, key=level_sort_key):
            if found_id not in scheduled:
                queue.append(found_id)
                scheduled.add(found_id)

        if is_possible_article_level(level_id): #
            url = make_level_url(level_id) # article level page URL
            html = fetch(session, url) # fetch article level page HTML
            if not html:
                print(f"[skip] fetch failed: {url}")
                continue
            row = parse_article_page(level_id, html)
            if row and row["source_url"] not in seen_source_urls:
                rows.append(row)
                seen_source_urls.add(row["source_url"])
                print(f"[scraped] {row['source_url']} | {row['title']}")

        time.sleep(delay)

    rows.sort(key=lambda r: level_sort_key(r["_level_id"]))
    '''
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f)        
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})
    '''
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f) 
        for each in issue_urls:
            writer.writerow({each})

    print(f"\nVisited URLs: {len(visited)}")
    #print(f"Scraped articles: {len(rows)}")
    #print(f"Saved to: {out_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-id", default="ma_007")
    parser.add_argument("--out", default="ma_007_issues.csv")
    parser.add_argument("--delay", type=float, default=3)
    args = parser.parse_args()
    #import pdb; pdb.set_trace()
    scrape(root_id=args.root_id, out_csv=args.out, delay=args.delay)


#```bash
#python scrape_issues_urls.py --out ma_007_issues.csv
#```
