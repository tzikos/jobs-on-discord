import requests
from bs4 import BeautifulSoup
import time
import csv
from datetime import datetime
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
import random

# Load environment variables from the .env file
load_dotenv()

# Access the variables using os.getenv()
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

# Website URL to monitor
WEBSITE_URL = 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?distance=25&geoId=102194656&keywords=student'

# Path to the central .txt file
CENTRAL_FILE_PATH = 'expo/central.txt'

# User agent rotation to avoid detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
]

def get_headers():
    """Generate headers for the request without hardcoded cookies"""
    return {
        'authority': 'www.linkedin.com',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'cache-control': 'max-age=0',
        'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': random.choice(USER_AGENTS)
    }

params = {
    'f_AL': 'true',
    'f_TPR': 'r300',  # Last 1 hour
    # 'f_WT': '2',        # Remote-friendly jobs (optional)
    # 'f_E': '1',         # Entry-level (good for students)
    'location': 'Copenhagen, Capital Region, Denmark',
    'keywords': 'student data scientist OR student machine learning OR student deep learning OR student devops OR student data analyst OR student data engineer OR student', 
    'sortBy': 'DD'
}

# Setup Discord bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Function to check if the directory exists, if not create it
def ensure_directory_exists(file_path):
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

# Function to check website for new jobs
def check_website():
    start = 0
    all_jobs = []
    
    while True:
        url = f"{WEBSITE_URL}&start={start}"
        print(f"Fetching: {url}")
        
        try:
            # Get fresh headers for each request
            headers = get_headers()
            response = requests.get(url, headers=headers, params=params)
            
            # Check if response is successful
            if response.status_code != 200:
                print(f"Error: Received status code {response.status_code}")
                # Add delay before retrying on error
                time.sleep(5)
                continue
                
            soup = BeautifulSoup(response.text, 'html.parser')
            jobs = soup.find_all("li")
            
            if not jobs:
                print("No more jobs found. Stopping.")
                break
            
            for job in jobs:
                try:
                    job_link = job.find('a')
                    if job_link:
                        url = job_link.get('href')
                        # Clean up and validate URL
                        if not url.startswith('http'):
                            url = f"https://www.linkedin.com{url}"
                            
                        job_id = url.split('?')[0].split('-')[-1]
                        title_element = job.find('h3')
                        company_element = job.find('h4')
                        
                        if title_element and company_element:
                            title = title_element.get_text().strip()
                            company = company_element.get_text().strip()
                            location_element = job.find('span', class_='job-search-card__location')
                            location = location_element.get_text().strip() if location_element else "Location not specified"
                            time_element = job.find('time')
                            timeposted = time_element.get_text().strip() if time_element else "Time not specified"
                            all_jobs.append((job_id, url, title, company, location, timeposted))
                except Exception as e:
                    print(f"Error processing a job: {e}")
                    continue
            
            start += 10  # Increment start index to fetch the next set of results
            # Random delay between 1-3 seconds to avoid rate limiting
            time.sleep(1 + random.random() * 2)  
        
        except Exception as e:
            print(f"Error fetching jobs: {e}")
            # Add longer delay on exception
            time.sleep(10)
            break
    
    return all_jobs

# Function to read existing IDs from the central file
def read_existing_ids():
    ensure_directory_exists(CENTRAL_FILE_PATH)
    try:
        with open(CENTRAL_FILE_PATH, 'r') as file:
            existing_ids = [line.strip() for line in file.readlines()]
        return existing_ids
    except FileNotFoundError:
        # If the file does not exist, return an empty list
        return []

# Function to add a new ID to the central file
def add_new_id(new_id):
    ensure_directory_exists(CENTRAL_FILE_PATH)
    with open(CENTRAL_FILE_PATH, 'a') as file:
        file.write(new_id + '\n')

# Function to log job to CSV
def log_job_to_csv(job_id, url):
    csv_file_path = 'jobs_sent.csv'
    ensure_directory_exists(csv_file_path)
    
    # Check if the CSV file exists, if not create it with headers
    try:
        with open(csv_file_path, 'r') as file:
            pass
    except FileNotFoundError:
        with open(csv_file_path, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Job ID', 'URL', 'Datetime Sent'])

    # Append the new job details to the CSV file
    with open(csv_file_path, 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([job_id, url, datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    
    # Get the channel to send messages to
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    
    if not channel:
        print(f"ERROR: Could not find channel with ID {DISCORD_CHANNEL_ID}")
        await bot.close()
        return
    
    # Process jobs
    print('Reading existing job IDs')
    existing_ids = read_existing_ids()
    
    print('Getting new jobs')
    new_jobs = check_website()
    
    jobs_sent = 0
    
    for new_id, new_url, new_title, new_company, new_location, new_time_posted in new_jobs:
        print(f'Checking id {new_id}')
        if new_id not in existing_ids and 'student' in new_title.lower():
            print(f'{new_id} does not already exist')
            try:
                # Create and send an embed message
                embed = discord.Embed(
                    title=new_title,
                    url=new_url,
                    description=f"Company: **{new_company}**\nLocation: **{new_location}**",
                    color=0x0099ff
                )
                embed.set_footer(text=f"Job ID: {new_id} • {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{new_time_posted}")
                
                await channel.send(embed=embed)
                log_job_to_csv(new_id, new_url)
                jobs_sent += 1
                
            except Exception as e:
                await channel.send(f"There was an **ERROR** processing job {new_id}: {str(e)}")
                
            add_new_id(new_id)
            time.sleep(1)  # Brief pause between messages
        else:
            print(f'{new_id} already exists or does not contain "student"')
    
    if jobs_sent > 0:
        await channel.send(f"Job check complete. Found {jobs_sent} new student job(s).")
    else:
        print("No new jobs to send.")
    
    # Close the bot connection when done
    await bot.close()

# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)