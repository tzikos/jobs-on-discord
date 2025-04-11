import requests
from bs4 import BeautifulSoup
import time
import random
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))

# LinkedIn configuration (now checks last 5 minutes only)
WEBSITE_URL = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search'
PARAMS = {
    'distance': '25',
    'geoId': '102194656',
    'keywords': 'student',
    'f_AL': 'true',
    'f_TPR': 'r300',  # Last 5 minutes
    'location': 'Copenhagen, Capital Region, Denmark',
    'sortBy': 'DD'
}

# User agent rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    # Add more user agents as needed
]

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
    }

def fetch_jobs():
    """Fetch jobs posted in the last 5 minutes"""
    all_jobs = []
    start = 0
    
    while True:
        try:
            response = requests.get(
                WEBSITE_URL,
                headers=get_headers(),
                params={**PARAMS, 'start': start}
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
                    
                    if title and 'student' in title.lower() and url:
                        all_jobs.append({
                            'title': title,
                            'company': company,
                            'url': url,
                            'time_posted': job.find('time').get_text().strip() if job.find('time') else None
                        })
                except Exception as e:
                    print(f"Error processing job: {e}")
                    continue
                    
            start += 10
            time.sleep(1 + random.random())  # Rate limiting
            
        except Exception as e:
            print(f"Fetch error: {e}")
            break
            
    return all_jobs

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        print(f"Error: Channel {DISCORD_CHANNEL_ID} not found")
        await bot.close()
        return
    
    jobs = fetch_jobs()
    
    if jobs:
        for job in jobs:
            embed = discord.Embed(
                title=job['title'],
                url=job['url'],
                description=f"**Company:** {job['company']}\n**Posted:** {job['time_posted']}",
                color=0x0099ff
            )
            await channel.send(embed=embed)
        await channel.send(f"✅ Found {len(jobs)} new student jobs in the last 5 minutes")
    else:
        print("No new jobs found")
    
    await bot.close()

def lambda_handler(event, context):
    print("Starting job check...")
    bot.run(DISCORD_BOT_TOKEN)
    return {
        'statusCode': 200,
        'body': 'Job check completed'
    }

if __name__ == "__main__":
    # For local testing
    bot.run(DISCORD_BOT_TOKEN)