import asyncio
import json
import os
import random
import re
import time
from datetime import datetime, timedelta

import discord
import requests
from bs4 import BeautifulSoup
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Config file path
CONFIG_PATH = "config.yaml"

# LinkedIn configuration
WEBSITE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Rotate user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def parse_keyword_list(value):
    """Return a clean list of keywords from comma-separated string or list."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def load_config(config_path=CONFIG_PATH):
    """Load channel configuration from YAML (or JSON-compatible YAML)."""
    with open(config_path, "r") as f:
        content = f.read()

    try:
        import yaml

        raw_config = yaml.safe_load(content) or {}
    except ImportError:
        # Fallback for environments without PyYAML. The file must stay JSON-compatible.
        raw_config = json.loads(content)

    base_params = raw_config.get("defaults", {}).get("params", {}) or {}
    channels = []

    for entry in raw_config.get("channels", []):
        channel_env = entry.get("channel_env")
        if not channel_env:
            print("Skipping channel without channel_env")
            continue

        channel_id = os.getenv(channel_env)
        if not channel_id:
            print(f"Channel env var not set: {channel_env}")
            continue

        try:
            channel_id = int(channel_id)
        except ValueError:
            print(f"Invalid channel id for {channel_env}: {channel_id}")
            continue

        params = {**base_params, **(entry.get("params") or {})}

        channels.append(
            {
                "channel_env": channel_env,
                "channel_id": channel_id,
                "include": parse_keyword_list(entry.get("include", "")),
                "exclude": parse_keyword_list(entry.get("exclude", "")),
                "params": params,
            }
        )

    return channels

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
    }

def is_recent(time_posted_str):
    if not time_posted_str:
        return False
    now = datetime.now()

    match = re.search(r"(\d+)\s*(minute|hour|day|second)", time_posted_str.lower())
    if not match:
        return False

    num = int(match.group(1))
    unit = match.group(2)

    if "second" in unit:
        delta = timedelta(seconds=num)
    elif "minute" in unit:
        delta = timedelta(minutes=num)
    elif "hour" in unit:
        delta = timedelta(hours=num)
    elif "day" in unit:
        delta = timedelta(days=num)
    else:
        return False

    return delta <= timedelta(minutes=5)

def fetch_jobs(params):
    """Fetch jobs posted in last 5 minutes"""
    all_jobs = []
    start = 0

    while True:
        try:
            response = requests.get(
                WEBSITE_URL,
                headers=get_headers(),
                params={**params, "start": start},
            )

            if response.status_code != 200:
                print(f"Error: Status {response.status_code}")
                time.sleep(2)
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            jobs = soup.find_all("li")

            if not jobs:
                break

            for job in jobs:
                try:
                    title = job.find('h3').get_text().strip() if job.find('h3') else None
                    company = job.find('h4').get_text().strip() if job.find('h4') else None
                    url = job.find('a')['href'] if job.find('a') else None
                    time_posted = job.find('time').get_text().strip() if job.find('time') else None

                    if title and url and is_recent(time_posted):
                        all_jobs.append({
                            'title': title,
                            'company': company,
                            'url': url,
                            'time_posted': time_posted
                        })

                except Exception as e:
                    print(f"Error processing job: {e}")

            start += 10
            time.sleep(1 + random.random())

        except Exception as e:
            print(f"Fetch error: {e}")
            break

    return all_jobs

def filter_jobs(jobs, include_list, exclude_list):
    """Return jobs matching include/exclude keywords."""
    filtered = []
    for job in jobs:
        title = job["title"].lower()

        has_include = include_list and any(kw.lower() in title for kw in include_list)
        has_exclude = any(kw.lower() in title for kw in exclude_list)

        if has_include and not has_exclude:
            filtered.append(job)

    return filtered

async def run_discord_bot(channel_configs):
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='/', intents=intents)

    @bot.event
    async def on_ready():
        print(f"Bot ready: {bot.user}")

        for cfg in channel_configs:
            channel = bot.get_channel(cfg["channel_id"])

            if not channel:
                print(f"Channel not found: {cfg['channel_id']}")
                continue

            jobs = fetch_jobs(cfg["params"])
            selected_jobs = filter_jobs(jobs, cfg["include"], cfg["exclude"])

            for job in selected_jobs:
                embed = discord.Embed(
                    title=job['title'],
                    url=job['url'],
                    description=f"**Company:** {job['company']}\n**Posted:** {job['time_posted']}",
                    color=0x0099ff
                )
                await channel.send(embed=embed)

        await bot.close()

    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"Bot error: {e}")

def lambda_handler(event, context):
    channel_configs = load_config()
    asyncio.run(run_discord_bot(channel_configs))
    return {'statusCode': 200, 'body': 'Done'}
