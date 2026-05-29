import re
import json
import requests
from bs4 import BeautifulSoup

from response_check_article_url import get_level_id


def retrieve_article_data(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    res = requests.get(url, headers=headers, timeout=20)
    res.raise_for_status()

    # Korean pages may need encoding detection
    res.encoding = res.apparent_encoding

    soup = BeautifulSoup(res.text, "lxml")

    def normalize_label(text):
        return re.sub(r"\s+", "", text).rstrip(":：")

    def clean_text(tag, separator=" "):
        if tag is None:
            return None

        for x in tag.select("script, style"):
            x.decompose()

        text = tag.get_text(separator, strip=True)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        return text.strip()

    def find_div_cont_value(label):
        """
        Find the <div class="cont"> value associated with a Korean label
        such as 잡지명, 발행일, 기사제목, 기사형태.
        """
        for text_node in soup.find_all(string=True):
            if normalize_label(text_node) == label:
                label_tag = text_node.parent

                # Search nearby parent blocks first
                node = label_tag
                for _ in range(5):
                    if node is None:
                        break

                    cont = node.find(
                        lambda tag: tag.name == "div"
                        and "cont" in tag.get("class", [])
                    )

                    if cont:
                        return clean_text(cont)

                    node = node.parent

                # Fallback: next <div class="cont">
                cont = label_tag.find_next(
                    lambda tag: tag.name == "div"
                    and "cont" in tag.get("class", [])
                )

                if cont:
                    return clean_text(cont)

        return None

    labels = ["잡지명", "발행일", "기사제목", "기사형태"]

    result = {
        label: find_div_cont_value(label)
        for label in labels
    }

    # Extract text from <div id="cont_view">
    cont_view = soup.find("div", id="cont_view")
    result["본문"] = clean_text(cont_view, separator="\n")

    return result

def load_article_urls(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return [line.strip() for line in f if line.strip()]


def save_jsonl(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


urls = load_article_urls("article_urls.csv")
print(f"Loaded {len(urls)} article URLs")

for url in urls[:]:  # 
    print(f"\nRetrieving data from: {url}")
    try:
        data = retrieve_article_data(url)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        save_jsonl([data], f"data/{get_level_id(url)}.jsonl")
    except Exception as e:
        print(f"Error retrieving {url}: {e}")

exit()
'''below is test code for single article URL'''
url = "https://db.history.go.kr/modern/level.do?levelId=ma_007_0010_0030"
article_data = retrieve_article_data(url)

#print(article_data)
print(json.dumps(article_data, ensure_ascii=False, indent=2))
save_jsonl([article_data], "data/ma_007_0010_0030.jsonl")