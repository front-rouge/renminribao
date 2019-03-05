#!/usr/bin/env python3
import sys
import asyncio
import time
import logging
import feedparser
import json
import html
import re
from urllib import request
from urllib.error import HTTPError, URLError
import typing as t


logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: %(message)s')
logger = logging.getLogger(__name__)


__VERSION__: str = "2.0"
USER_AGENT = f"RenminRibao/{__VERSION__} ({sys.platform})"
HTTP_HEADER: t.Dict[str, str] = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
MINUTE: int = 60
HOUR: int = MINUTE * 60
DAY: int = HOUR * 24
YTB_FEED_BASE_URL: str = "https://www.youtube.com/feeds/videos.xml?channel_id="
REGEX_TAG = re.compile(r'(<!--.*?-->|<[^>]*>)')

config: t.Dict = {}
feedparser.USER_AGENT = USER_AGENT


def import_json(json_file: str) -> t.Any:
    with open(json_file, 'r') as f:
        res = json.load(f)
    return res


def do_post_request(url: str, data: t.Dict[str, t.Any]):
    req = request.Request(url, json.dumps(data).encode('ascii'), HTTP_HEADER)
    try:
        request.urlopen(req)
    except HTTPError as e:
        logger.error(f"{url} got {e.code} - {e.reason}")
        logger.debug(e.read())
    except URLError as e:
        logger.error(f"[{url}] {e.reason}")


def get_header_data(feed: t.Any) -> t.Dict[str, str]:
    data: t.Dict[str, str] = dict()
    if "title" in feed:
        data['name'] = feed['title']
    if "link" in feed:
        data['url'] = feed['link']
    if "image" in feed and "href" in feed['image']:
        data['icon_url'] = feed['image']['href']
    return data


async def task_handler(name: str, urls: t.List[str], wait_time: int, callback: t.Any):
    logger.info(f"Starting {name}")
    last_check: time.struct_time = time.gmtime()
    temp_time: time.struct_time = last_check
    while True:  # run forever
        for url in urls:
            try:
                logger.info(f"Fetch {url}")
                res = feedparser.parse(url)
                temp_time = time.gmtime()
                if "updated_parsed" in res.feed and last_check > res.feed.updated_parsed:
                    continue
                header_data: t.Dict[str, str] = get_header_data(res.feed)
                for entry in res.entries:
                    logger.debug(entry)
                    if last_check > entry.published_parsed:
                        continue
                    logger.info(f"New entry found: {entry.title}")
                    await callback(header_data, entry)
            except Exception as e:
                logger.error(str(e))
        last_check = temp_time
        await asyncio.sleep(wait_time)


def to_summary(text: str) -> str:
    text = html.unescape(text)
    text = REGEX_TAG.sub('', text)
    return text[:500]


async def task_rss():
    async def callback(header_data: t.Dict[str, str], entry: t.Any):
        summary: str = to_summary(entry.summary)
        data: t.Dict[str, t.Any] = {
            "embeds": [{
                "author": header_data,
                "description": f"**__{entry.title}__**\n{summary}\n[Lire la suite]({entry.link})"
            }]
        }
        for hook in config['webhooks']:
            do_post_request(hook, data)

    if "feeds" not in config:
        return
    await task_handler('task_rss', config['feeds'], MINUTE * 15, callback)


async def task_youtube():
    async def callback(header_data: t.Dict[str, str], entry: t.Any):
        data: t.Dict[str, t.Any] = {
            "content": f"**__{entry.title}__**\n{entry.link}"
        }
        for hook in config['webhooks']:
            do_post_request(hook, data)

    if "youtube" not in config:
        return
    ytb_feeds: t.List[str] = [YTB_FEED_BASE_URL + i for i in config['youtube']]
    await task_handler('task_youtube', ytb_feeds, HOUR, callback)


if __name__ == '__main__':
    config = import_json('config.json')
    loop = asyncio.get_event_loop()
    loop.create_task(task_rss())
    loop.create_task(task_youtube())
    try:
        loop.run_forever()
    except Exception:
        loop.close()
