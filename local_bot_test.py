import requests
from bs4 import BeautifulSoup
import time
import random
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import re
from datetime import datetime, timedelta

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

# Dictionary to store job descriptions (in-memory cache)
job_descriptions_cache = {}

def get_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept-Language': 'en-US,en;q=0.9',
    }

def is_recent(time_posted_str):
    """Check if the job was posted within the last 5 minutes"""
    if not time_posted_str:
        return False
    
    # Get current time
    now = datetime.now()
    
    # Parse the time_posted string
    match = re.search(r'(\d+)\s*(minute|hour|day|second)', time_posted_str.lower())
    if not match:
        return False
    
    num = int(match.group(1))
    unit = match.group(2)
    
    # Calculate the time delta
    if 'second' in unit:
        delta = timedelta(seconds=num)
    elif 'minute' in unit:
        delta = timedelta(minutes=num)
    elif 'hour' in unit:
        delta = timedelta(hours=num)
    elif 'day' in unit:
        delta = timedelta(days=num)
    else:
        return False
    
    # Check if the posting time is within the last 5 minutes
    return delta <= timedelta(minutes=50) #TODO: change this to 5 minutes

def fetch_job_description(job_url):
    """Fetch the full job description from the job page"""
    try: #job-details > div > p
        response = requests.get(job_url, headers=get_headers())
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            print(soup)
            description_div = soup.find('div', {'class':'jobs-description__container'})
            print(description_div.get_text())
            if description_div:
                # Clean up the description text
                description = description_div.get_text(separator='\n', strip=True)
                # Truncate if too long (Discord has a 4096 character limit for embeds)
                return description[:4000] + '...' if len(description) > 4000 else description
        return "Description not available"
    except Exception as e:
        print(f"Error fetching job description: {e}")
        return "Description not available"

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
            print(jobs)
            if not jobs:
                break
                
            for job in jobs:
                try:
                    title = job.find('h3').get_text().strip() if job.find('h3') else None
                    company = job.find('h4').get_text().strip() if job.find('h4') else None
                    url = job.find('a')['href'] if job.find('a') else None
                    time_posted = job.find('time').get_text().strip() if job.find('time') else None
                    
                    if title and 'student' in title.lower() and url and is_recent(time_posted):
                        # Generate a unique ID for this job (using URL hash)
                        job_id = hash(url)
                        # Fetch the description and cache it
                        description = fetch_job_description(url)
                        job_descriptions_cache[job_id] = description
                        
                        all_jobs.append({
                            'id': job_id,
                            'title': title,
                            'company': company,
                            'url': url,
                            'time_posted': time_posted,
                            'description': description
                        })
                    else:
                        print(f"Skipping job: {title} - Not a student job or not recent: {title} | {time_posted}")
                except Exception as e:
                    print(f"Error processing job: {e}")
                    continue
                    
            start += 10
            time.sleep(1 + random.random())  # Rate limiting
            
        except Exception as e:
            print(f"Fetch error: {e}")
            break
            
    return all_jobs

# Create a function to handle the Discord bot functionality
async def run_discord_bot():
    # Create a new bot instance each time
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='/', intents=intents)

    class DescriptionView(discord.ui.View):
        """Custom view for the description button"""
        def __init__(self, job_id):
            super().__init__(timeout=None)  # Timeout None makes it persistent
            self.job_id = job_id

        @discord.ui.button(label="Show Description", style=discord.ButtonStyle.primary, custom_id="show_desc")
        async def show_description(self, interaction: discord.Interaction, button: discord.ui.Button):
            description = job_descriptions_cache.get(self.job_id, "Description not available")
            
            # Check if description is too long for a single message
            if len(description) > 2000:
                parts = [description[i:i+2000] for i in range(0, len(description), 2000)]
                await interaction.response.send_message(content=f"**Job Description (1/{len(parts)}):**\n{parts[0]}", ephemeral=True)
                for i, part in enumerate(parts[1:], 2):
                    await interaction.followup.send(content=f"**Job Description ({i}/{len(parts)}):**\n{part}", ephemeral=True)
            else:
                await interaction.response.send_message(content=f"**Job Description:**\n{description}", ephemeral=True)

    @bot.event
    async def on_ready():
        print(f"Bot is ready and logged in as {bot.user}")
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
                
                # Add the view with the description button
                view = DescriptionView(job['id'])
                await channel.send(embed=embed, view=view)
            
            # await channel.send(f"✅ Found {len(jobs)} new student jobs in the last 5 minutes")
        else:
            print("No new jobs found")
            # await channel.send("ℹ️ No new student jobs found in the last 5 minutes")
        
        # Close the bot after sending messages
        await bot.close()

    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"Error running bot: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

def lambda_handler(event, context):
    print("Starting job check...")
    # Clear the cache at the start of each run
    global job_descriptions_cache
    job_descriptions_cache = {}
    
    # Run the bot using asyncio
    asyncio.run(run_discord_bot())
    return {
        'statusCode': 200,
        'body': 'Job check completed'
    }

# Define dummy event and context
event = {
    # Put any relevant keys your Lambda uses here
    'someKey': 'someValue'
}
class Context:
    def __init__(self):
        self.function_name = "test_function"
        self.memory_limit_in_mb = 128
        self.invoked_function_arn = "arn:aws:lambda:local:test:function:test_function"
        self.aws_request_id = "test-request-id"
context = Context()

# Define any global variables your Lambda depends on
job_descriptions_cache = {}

# Assuming your lambda_handler is already defined above or imported
if __name__ == '__main__':
    result = lambda_handler(event, context)
    print(result)