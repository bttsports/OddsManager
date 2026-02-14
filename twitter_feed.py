#!/usr/bin/env python
import sys
import os
# Ensure script runs from its own folder
os.chdir(os.path.dirname(__file__))
# ensure project root is on PYTHONPATH
sys.path.append("C:/Users/davpo/PycharmProjects/NFLPlayerModel")
import unicodedata
import db
import re
from os_check import *
from selenium.webdriver.common.keys import Keys
from difflib import SequenceMatcher
from dateutil.parser import isoparse
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium.common.exceptions import InvalidCookieDomainException
from scraper_utils import *
from selenium.common.exceptions import TimeoutException
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import pickle
import time
import logging
import datetime

logger = logging.getLogger()  # root logger
logger.setLevel(logging.INFO)

# Remove all pre-existing handlers (important!)
if logger.hasHandlers():
    logger.handlers.clear()

# Add our UTF-8 file handler manually
file_handler = logging.FileHandler("twitter_feed.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

logger.addHandler(file_handler)


TWITTER_LOGIN = "https://twitter.com/login"
TWITTER_LIST_URL = "https://x.com/i/lists/52021139"
COOKIE_FILE = "twitter_cookies.pkl"


# def load_dcs():
#     pkl_path = PROJECT_FILE_PATH + "/nfl_dash_app/gatherers/espndc.pkl"
#
#     if os.path.exists(pkl_path):
#         with open(pkl_path, "rb") as f:
#             return pickle.load(f)
#
#     dc_data = scrape_all_espn_depth_charts()
#     with open(pkl_path, "wb") as f:
#         pickle.dump(dc_data, f)
#
#     return dc_data
#
#
# PRELOADED_DEPTH_CHARTS = load_dcs()
# ALL_NAMES = extract_all_values(PRELOADED_DEPTH_CHARTS)


def save_cookies(driver):
    cookies = driver.get_cookies()
    # drop any that look expired
    now = time.time()
    good = []
    for c in cookies:
        exp = c.get("expiry")
        if exp and exp < now:
            continue
        good.append(c)
    with open(COOKIE_FILE, "wb") as f:
        pickle.dump(good, f)


def load_cookies(driver):
    driver.get("https://twitter.com")
    # 2) load up whatever we saved last time
    if not os.path.exists(COOKIE_FILE):
        return

    with open(COOKIE_FILE, "rb") as f:
        cookies = pickle.load(f)

    for c in cookies:
        # strip things Selenium hates
        c.pop("sameSite",  None)
        c.pop("hostOnly",   None)
        c.pop("session",    None)
        c.pop("expiry",     None)
        # force domain/path
        c["domain"] = ".twitter.com"
        c["path"]   = "/"
        try:
            driver.add_cookie(c)
        except InvalidCookieDomainException:
            # if it still doesn’t like it, skip
            continue

    # 3) reload so these cookies take effect
    driver.get("https://twitter.com/home")
    # if we got redirected to /login, cookies didn't work
    return driver.current_url.startswith("https://twitter.com/login")


# def get_all_dc_names(espn_team_abbr=None):
#     """Returns a list of full player names from the ESPN depth charts, only for espn_team_abbr if passed in"""
#     if espn_team_abbr is None:
#         all_names = [((name for name in list(pos_dict.values())) for pos_dict in team_dict)
#                      for team_dict in PRELOADED_DEPTH_CHARTS]
#         return all_names
#     else:
#         return [(name for name in list(pos_dict.values())) for pos_dict in PRELOADED_DEPTH_CHARTS[espn_team_abbr]]


def do_automated_login(driver):
    """Fill in the username/password form, submit, wait until we're off /login."""
    if OS == 'ubuntu':
        from dotenv import load_dotenv

        load_dotenv("/mnt/c/Users/davpo/PycharmProjects/NFLPlayerModel/.env")

        user = os.getenv("TWITTER_USER")
        pwd = os.getenv("TWITTER_PASS")
    else:
        user = os.getenv("TWITTER_USER")
        pwd  = os.getenv("TWITTER_PASS")
    if not user or not pwd:
        raise RuntimeError("Please set TWITTER_USER & TWITTER_PASS in your env.")

    driver.get("https://x.com/login")
    wait = WebDriverWait(driver, 30)

    ident = wait.until(EC.visibility_of_element_located(
        (By.CSS_SELECTOR, 'input[name="text"]')))
    ident.clear(); ident.send_keys(user); ident.send_keys(Keys.ENTER)

    try:
        challenge = WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[name="text"]'))
        )
        # If a second text input appears, fill it with the same identifier
        # or with the requested phone/email if you have it.
        if challenge.is_displayed():
            challenge.clear(); challenge.send_keys(user); challenge.send_keys(Keys.ENTER)
    except TimeoutException:
        pass

    # 3) Password screen
    pwd_in = wait.until(EC.visibility_of_element_located(
        (By.CSS_SELECTOR, 'input[name="password"]')))
    pwd_in.clear()
    pwd_in.send_keys(pwd)
    pwd_in.send_keys(Keys.ENTER)


    # 5) Verify we are not on /login anymore
    try:
        wait.until(lambda d: "/login" not in d.current_url)
    except TimeoutException:
        raise RuntimeError("Login failed or challenged")

    # 6) Optional: wait for home UI proof
    driver.get("https://x.com/home")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[aria-label="Home"]')))


def fetch_latest_tweets(list_url, max_scrolls=20):
    driver = get_driver(headless=True, use_fake_useragent=True)
    try:
        do_automated_login(driver)
    except:
        pass
    time.sleep(2)
    return scrape_tweets(driver, list_url, max_scrolls)


def match_player_names(tweet_text, all_names, fuzzy_threshold=0.75):
    """
    Returns a list of player names matched in the tweet_text.

    Priority:
      1. Exact full-name match
      2. If none, match if full first or last name appears

    Args:
        tweet_text (str): The tweet content.
        all_names (List[str]): List of full player names.
        fuzzy_threshold (float): Ratio threshold for fuzzy match fallback.

    Returns:
        List[str]: Matched player names.
    """
    tweet_lower = tweet_text.lower()
    matched = set()

    words = set(re.findall(r'\b\w+\b', tweet_lower))

    # Priority 1: exact full name match
    for full_name in all_names:
        full_name_lower = full_name.lower()

        if full_name_lower in tweet_lower:
            matched.add(full_name)
            continue

    # if name not matched
    if not matched:

        for full_name in all_names:
            # Priority 3: fuzzy match if no strong signal yet
            matches = 0
            for word in words:
                ratio1 = SequenceMatcher(None, full_name_lower.split()[0], word).ratio()
                ratio2 = SequenceMatcher(None, full_name_lower.split()[1], word).ratio()
                # probably at least 2 "words" or names need to match, this will give false positives but
                # better than missing out
                if ratio1 >= fuzzy_threshold or ratio2 >= fuzzy_threshold:
                    matches += 1
                if matches == 2:
                    matched.add(full_name)
                    break

    return ",".join(sorted(matched))


def load_seen_ids():
    """Load all tweet_ids from your tweets table from the last 5 days into a Python set."""
    # calculate the cutoff timestamp (5 days ago)
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5)
    # if your created_at column is stored as ISO strings, .isoformat() will match
    cutoff_str = cutoff.isoformat()
    query = f"SELECT tweet_id FROM nfl_tweets WHERE created_at >= '{cutoff_str}'"
    #print(query)
    rows = db.execute_any_query(query)

    return [row['tweet_id'] for row in rows]


def wait_for_new_tweets(driver, prev_count, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        curr = len(driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]'))
        if curr > prev_count:
            prev_count = curr
            end = time.time() + 1  # extend 1s window when new ones appear
        else:
            time.sleep(0.3)
    return prev_count


def scrape_tweets(driver, list_url, max_scrolls):
    #seen_ids = load_seen_ids()
    driver.get(list_url)
    logger.info("Successful Log In, Accessing List " + str(list_url))
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
    tweets_by_id = {}
    for _ in range(max_scrolls):
        # find all tweet articles on page
        # wait for the main timeline container to exist
        wait = WebDriverWait(driver, 20)
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article[data-testid="tweet"]')))
        except:
            logger.info("failed to find tweet by CSS SELECTOR")
            logger.info("Unable to Access twitter list ", list_url)
            return
        wait_for_new_tweets(driver, 30, timeout=10)
        articles = driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
        if len(articles) == 0:
            logger.info("Unable to Access twitter list ", list_url)
        for art in articles:
            try:
                try:
                    more = art.find_element(
                        By.XPATH,
                        './/div[@data-testid="tweetText"]//span[text()="Show more"]'
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", more)
                    more.click()
                    # wait until the “…” is gone
                    WebDriverWait(art, 2).until(
                        lambda t: '…' not in t.find_element(By.CSS_SELECTOR, 'div[data-testid="tweetText"]').text
                    )
                except:
                    pass
                # 4a) created_at & tweet_id
                time_elem = art.find_element(By.TAG_NAME, "time")
                twitter_dt = time_elem.get_attribute("datetime")
                #print(repr(twitter_dt))
                dt_utc = isoparse(twitter_dt)
                #print("good")
                # 2) Attach UTC tzinfo
                dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
                #print("good1")
                # 3) Convert to Eastern (will give EST or EDT depending on the date)
                created_at = str(dt_utc.astimezone(ZoneInfo("America/New_York")))

                # parent anchor of time has href ending in /status/<tweet_id>
                status_href = time_elem.find_element(By.XPATH, "./..").get_attribute("href")
                tweet_id = status_href.rsplit("/", 1)[-1]

                # if tweet_id in seen_ids:
                #     logger.info("seen tweet id = True")
                #     # we've hit an old tweet → stop everything
                #     driver.quit()
                #     for tid, values in tweets_by_id.items():
                #         matched_names = match_player_names(values['text'], ALL_NAMES)
                #         # remove prefix comma
                #         values['player_names'] = matched_names[1:]
                #     # upload to db
                #     # print(list(tweets_by_id.values())[0])
                #     tweet_data = [list(tweet_data.values()) for tweet_data in tweets_by_id.values()]
                #     for lst in tweet_data:
                #         # print(lst)
                #         db.insert_replace_data('nfl_tweets', lst, insert=False)
                #     logger.info(f"Logged... {len(tweet_data)} Tweets")
                #     return

                # 4b) author (@username)
                # look for the first link whose child is a div[dir="ltr"] starting with '@'
                author = ""
                try:
                    author_div = art.find_element(
                        By.XPATH,
                        './/a[./div[@dir="ltr"]]/div[@dir="ltr"]'
                    )
                    author = author_div.text.lstrip("@")
                except:
                    pass

                # 4c) text
                try:
                    text = art.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
                    text = unicodedata.normalize("NFKC", text)
                    text = re.sub(r"\s+", " ", text).strip().replace('"', "'")
                except:
                    text = ""

                #5 team - search text for any references to matchable team name keywords
                # team_matches = get_list_of_team_matches()
                # team_abbrs = ''
                # for abbr, words in team_matches.items():
                #     for word in words:
                #         if word in text:
                #             team_abbrs += (abbr+",")
                if author:
                    tweet_url = f"https://x.com/{author}/status/{tweet_id}"
                else:
                    tweet_url = f"https://x.com/i/web/status/{tweet_id}"
                tweets_by_id[tweet_id] = {
                    "id": tweet_id,
                    "author": author,
                    "text": text,
                    "created_at": created_at,
                    "url": tweet_url,
                }
                #print("tweets by id", tweets_by_id[tweet_id])
            except Exception:
                # skip any badly-formed articles
                logger.exception("Error")
                logger.info("Skipping a Tweet...")
                continue

        # scroll down
        driver.execute_script("window.scrollBy(0, 600);")
        wait_for_new_tweets(driver, len(articles))
        time.sleep(5)
        #print(tweets_by_id)
        last_height = 0
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # create player_names field analyzing the text
    # for tid, values in tweets_by_id.items():
    #     matched_names = match_player_names(values['text'], ALL_NAMES)
    #     # remove prefix comma
    #     values['player_names'] = matched_names[1:]
    # upload to db
    #print(list(tweets_by_id.values())[0])
    tweet_data = [list(tweet_data.values()) for tweet_data in tweets_by_id.values()]

    logger.info(f"Logged... {len(tweet_data)} Tweets")

    driver.quit()
    return tweet_data




# Example usage:
if __name__ == "__main__":
    list_url = TWITTER_LIST_URL
    tweets = fetch_latest_tweets(list_url, 20)
    print(tweets[:5])
