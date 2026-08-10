#!/usr/bin/env python3
"""Daily health-policy digest from Reddit, Bluesky, and Substack."""

from __future__ import annotations

import calendar
import html
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import feedparser
import requests
import time
import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")
BLUESKY_SEARCH_URLS = (
    "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
    "https://bsky.social/xrpc/app.bsky.feed.searchPosts",
)
REQUEST_HEADERS = {"User-Agent": "HealthSocialMonitor/1.0 (health-policy-digest)"}


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def keyword_pattern(keywords: list[str]) -> re.Pattern[str]:
    escaped = [re.escape(k) for k in keywords]
    return re.compile("|".join(escaped), re.IGNORECASE)


def matches_keywords(text: str, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text or ""))


def format_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(clean)).strip()


def parse_feed_datetime(entry: feedparser.FeedParserDict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    timestamp = calendar.timegm(parsed)
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def normalize_substack_feed(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith("/feed"):
        return cleaned
    if cleaned.startswith("http") and "substack.com" in cleaned:
        return f"{cleaned}/feed"
    slug = cleaned.removeprefix("https://").removeprefix("http://").removesuffix(".substack.com")
    return f"https://{slug}.substack.com/feed"


def reddit_rss_url(sub_name: str, reddit_cfg: dict[str, Any]) -> str:
    base = f"https://www.reddit.com/r/{sub_name}/new.rss"
    user = os.environ.get("REDDIT_RSS_USER") or reddit_cfg.get("rss_user")
    feed_id = os.environ.get("REDDIT_RSS_FEED") or reddit_cfg.get("rss_feed")
    if user and feed_id:
        return f"{base}?user={user}&feed={feed_id}"
    return base


def fetch_reddit_items(config: dict[str, Any], pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    reddit_cfg = config["reddit"]
    lookback = timedelta(hours=int(reddit_cfg["lookback_hours"]))
    cutoff = datetime.now(timezone.utc) - lookback
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    use_auth = bool(
        (os.environ.get("REDDIT_RSS_USER") or reddit_cfg.get("rss_user"))
        and (os.environ.get("REDDIT_RSS_FEED") or reddit_cfg.get("rss_feed"))
    )
    delay = 0 if use_auth else int(reddit_cfg.get("request_delay_seconds", 62))

    for index, sub_name in enumerate(reddit_cfg["subreddits"]):
        if index > 0 and delay:
            time.sleep(delay)

        feed_url = reddit_rss_url(sub_name, reddit_cfg)
        parsed = feedparser.parse(feed_url)

        for entry in parsed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue

            title = entry.get("title", "Untitled post")
            summary = strip_html(entry.get("summary", ""))
            body = f"{title}\n{summary}"
            if not matches_keywords(body, pattern):
                continue

            published = parse_feed_datetime(entry)
            if published and published < cutoff:
                continue
            if not published:
                published = datetime.now(timezone.utc)

            author = entry.get("author", "[unknown]")
            seen.add(link)
            items.append(
                {
                    "source": "Reddit",
                    "community": f"r/{sub_name}",
                    "title": title,
                    "url": link,
                    "author": author,
                    "timestamp": published,
                    "snippet": summary[:280],
                }
            )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items[: int(config["limits"]["max_items_per_source"])]


def bluesky_post_url(uri: str, handle: str | None) -> str:
    # at://did:plc:xxx/app.bsky.feed.post/yyy -> https://bsky.app/profile/handle/post/yyy
    post_id = uri.rsplit("/", 1)[-1]
    profile = handle or "unknown"
    return f"https://bsky.app/profile/{profile}/post/{post_id}"


def fetch_bluesky_search_posts(keyword: str, limit: int) -> list[dict[str, Any]]:
    params = {"q": keyword, "limit": limit, "sort": "latest"}
    last_error: str | None = None

    for url in BLUESKY_SEARCH_URLS:
        try:
            response = requests.get(url, params=params, headers=REQUEST_HEADERS, timeout=30)
            if response.status_code in {403, 429}:
                last_error = f"{response.status_code} from {url}"
                continue
            response.raise_for_status()
            return response.json().get("posts", [])
        except requests.RequestException as exc:
            last_error = str(exc)

    if last_error:
        print(f"  Warning: Bluesky unavailable for '{keyword}' ({last_error})")
    return []


def fetch_bluesky_items(config: dict[str, Any], pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    bluesky_cfg = config["bluesky"]
    per_keyword = int(bluesky_cfg["posts_per_keyword"])
    keywords = config["beat"]["keywords"]
    seen: set[str] = set()
    items: list[dict[str, Any]] = []

    for keyword in keywords:
        posts = fetch_bluesky_search_posts(keyword, per_keyword)

        for post in posts:
            uri = post.get("uri", "")
            if not uri or uri in seen:
                continue

            record = post.get("record", {})
            text = record.get("text", "")
            if not matches_keywords(text, pattern):
                continue

            seen.add(uri)
            author = post.get("author", {})
            handle = author.get("handle")
            created_raw = record.get("createdAt")
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00")) if created_raw else datetime.now(timezone.utc)

            items.append(
                {
                    "source": "Bluesky",
                    "community": f"@{handle}" if handle else "Bluesky",
                    "title": text.split("\n", 1)[0][:140],
                    "url": bluesky_post_url(uri, handle),
                    "author": handle or "unknown",
                    "timestamp": created,
                    "snippet": text[:280],
                }
            )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    result = items[: int(config["limits"]["max_items_per_source"])]
    if not result:
        print("  Note: Bluesky returned no posts (often blocked from cloud servers — Reddit/Substack still work)")
    return result


def fetch_substack_items(config: dict[str, Any], pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    substack_cfg = config.get("substack") or {}
    newsletters = substack_cfg.get("newsletters") or []
    if not newsletters:
        return []

    lookback = timedelta(hours=int(substack_cfg.get("lookback_hours", 72)))
    cutoff = datetime.now(timezone.utc) - lookback
    filter_by_keywords = bool(substack_cfg.get("filter_by_keywords", False))
    seen: set[str] = set()
    items: list[dict[str, Any]] = []

    for newsletter in newsletters:
        feed_url = normalize_substack_feed(newsletter["feed"])
        display_name = newsletter.get("name") or feed_url
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            print(f"  Warning: Substack feed failed for {display_name}: {exc}")
            continue

        for entry in parsed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue

            title = entry.get("title", "Untitled post")
            summary = strip_html(entry.get("summary", ""))
            body = f"{title}\n{summary}"
            if filter_by_keywords and not matches_keywords(body, pattern):
                continue

            published = parse_feed_datetime(entry)
            if published and published < cutoff:
                continue
            if not published:
                published = datetime.now(timezone.utc)

            seen.add(link)
            author = entry.get("author") or display_name
            items.append(
                {
                    "source": "Substack",
                    "community": display_name,
                    "title": title,
                    "url": link,
                    "author": author,
                    "timestamp": published,
                    "snippet": summary[:280],
                }
            )

    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return items[: int(config["limits"]["max_items_per_source"])]


def render_section(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"<h2>{html.escape(title)}</h2><p><em>No matching posts in this run.</em></p>"

    rows = []
    for item in items:
        rows.append(
            "<li>"
            f"<strong><a href=\"{html.escape(item['url'])}\">{html.escape(item['title'])}</a></strong><br>"
            f"<span>{html.escape(item['source'])} · {html.escape(item['community'])} · "
            f"{html.escape(item['author'])} · {html.escape(format_timestamp(item['timestamp']))}</span>"
            f"<br><span>{html.escape(item['snippet'])}</span>"
            "</li>"
        )

    return f"<h2>{html.escape(title)}</h2><ul>{''.join(rows)}</ul>"


def build_email_html(
    reddit_items: list[dict[str, Any]],
    bluesky_items: list[dict[str, Any]],
    substack_items: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    keywords = ", ".join(config["beat"]["keywords"])

    body = (
        f"<h1>Health Social Digest — {today}</h1>"
        f"<p>Beat: {html.escape(keywords)}</p>"
        f"{render_section('Substack', substack_items)}"
        f"{render_section('Reddit', reddit_items)}"
        f"{render_section('Bluesky', bluesky_items)}"
        "<p><em>Tip: edit <code>config.yaml</code> to add keywords, subreddits, or Substack feeds when your beat changes.</em></p>"
    )
    return f"<!DOCTYPE html><html><body style=\"font-family: sans-serif; line-height: 1.5;\">{body}</body></html>"


def send_email(subject: str, html_body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT") or "587")
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    email_to = os.environ["EMAIL_TO"]
    email_from = os.environ.get("EMAIL_FROM", smtp_user)

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = email_from
    message["To"] = email_to
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(email_from, [email_to], message.as_string())
    except smtplib.SMTPAuthenticationError:
        print(
            "Email login failed. Check SMTP_USER, SMTP_PASSWORD (Gmail app password, no spaces), "
            "and that EMAIL_FROM matches SMTP_USER.",
            file=sys.stderr,
        )
        raise


def require_env(name: str) -> None:
    if not os.environ.get(name):
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    for name in ["SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]:
        require_env(name)

    config = load_config()
    pattern = keyword_pattern(config["beat"]["keywords"])

    print("Fetching Reddit...")
    try:
        reddit_items = fetch_reddit_items(config, pattern)
    except Exception as exc:
        print(f"  Warning: Reddit skipped ({exc})")
        reddit_items = []
    print(f"  Found {len(reddit_items)} Reddit posts")

    print("Fetching Bluesky...")
    try:
        bluesky_items = fetch_bluesky_items(config, pattern)
    except Exception as exc:
        print(f"  Warning: Bluesky skipped ({exc})")
        bluesky_items = []
    print(f"  Found {len(bluesky_items)} Bluesky posts")

    print("Fetching Substack...")
    try:
        substack_items = fetch_substack_items(config, pattern)
    except Exception as exc:
        print(f"  Warning: Substack skipped ({exc})")
        substack_items = []
    print(f"  Found {len(substack_items)} Substack posts")

    html_body = build_email_html(reddit_items, bluesky_items, substack_items, config)
    subject_prefix = config["email"]["subject_prefix"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = len(reddit_items) + len(bluesky_items) + len(substack_items)
    subject = f"{subject_prefix} — {today} ({total} items)"

    print("Sending email...")
    try:
        send_email(subject, html_body)
    except Exception as exc:
        print(f"Email failed: {exc}", file=sys.stderr)
        raise
    print("Done.")


if __name__ == "__main__":
    main()
