import re
import csv
import time
from urllib.parse import urlparse, parse_qs, unquote
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_ARTICLE_URL = "https://db.history.go.kr/modern/level.do?levelId={level_id}"

# These generate the same issue URLs you listed: ma_007_0010 ... ma_007_0260
ISSUE_URLS = [
    f"https://db.history.go.kr/modern/level.do?levelId=ma_007_{n:04d}"
    for n in range(10, 270, 10)
]


def make_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 article-url-extractor"
    })

    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session


def get_level_id(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return query["levelId"][0]


def extract_article_urls(issue_url: str, session: requests.Session) -> list[str]:
    issue_id = get_level_id(issue_url)

    response = session.get(issue_url, timeout=30)
    response.raise_for_status()
    article_urls = []
    for affix in range(1, 50): #1~42, ??
        affix_id = format(affix*10, "04d")
        article_url = issue_url + '_' +affix_id # add article level affix to issue level id
        article_response = session.get(article_url, timeout=30)
        if article_response.status_code == 200:
            print(f"{article_url}")
            article_urls.append(article_url)
        else: pass

    return article_urls


def main():
    session = make_session()

    results = {}


    for issue_url in ISSUE_URLS:
        print(f"Scraping: {issue_url}")
        #import pdb; pdb.set_trace()
        article_urls = extract_article_urls(issue_url, session)
        results[issue_url] = article_urls

        print(f"  Found {len(article_urls)} article URLs")
        time.sleep(15)  # be polite to the server

    # Save as CSV
    with open("article_urls.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f) 
        writer.writerow(["article_url"])
        for issue_url, article_urls in results.items():
            for article_url in article_urls:
                writer.writerow([article_url])        

    # Also print results
    for issue_url, article_urls in results.items():
        print("\nISSUE:", issue_url)
        for article_url in article_urls:
            print(article_url)


if __name__ == "__main__":
    main()