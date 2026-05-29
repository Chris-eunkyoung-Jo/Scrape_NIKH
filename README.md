# Scrape_NIKH

This project aims to scrape data from National Institute of Korean History(http://www.history.go.kr/)
In particular, we collect text data from http://db.history.go.kr/ which were already digitised there. 

If you make use of this, feel free to use and don't forget to cite this github site. 

There are a little bit dependencies. 
- webdriver
- sql database

# Description of files

- scrape_periodicals.py: 한국근현대잡지자료
- (Recent version, 2026 May) scrape_issues_urls.py, response_check_article_url.py, and scrape_article_data.py: 한국근현대잡지자료
    - scrape_issues_urls.py: scraping issue urls from the top level url of a periodical volume and saving them as `ma_volnum_issues.csv`
    - response_check_article_url.py: preparing valid article urls using issue urls from 'ma_XX_issues.csv' and saving them as `article_urls.csv`. 
    - scrape_article_data.py: scraping meta data and article body text using `article_urls.csv` and saving the results as JSONL files under data directory. 
- down-1.sh, down-2.sh,.. : 휴전회담회의록 in 대한민국
- (Moved to an indenpendent project, 2026 May) hanja2hangul: a program of convering hanja to hangul



