import os
import json
import random
import threading
import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, render_template, request, redirect, url_for

# Global configurations
OWNER_ID = 1327939431608483895
SHOP_FILE = "shop.json"
DATA_FILE = "economy_data.json"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Static jobs configuration profile list
JOBS_LIST = {
    "beggar": {"salary_min": 10, "salary_max": 40, "cooldown": 30, "description": "Beg strangers for spare change on the street corner."},
    "gamer": {"salary_min": 50, "salary_max": 150, "cooldown": 60, "description": "Stream voxel sandboxes and build a digital fanbase."},
    "developer": {"salary_min": 150, "salary_max": 450, "cooldown": 120, "description": "Write cloud systems, microcontrollers, and custom discord bots."}
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create folder structure for images if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DATABASE ENGINE STORAGE ---
def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except:
            return [] if filename == SHOP_FILE else {}
    return [] if filename == SHOP_FILE else {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

def get_profile(user_id):
    uid = str(user_id)
    economy = load_json(DATA_FILE)
    if uid not in economy:
        economy[uid] = {"wallet": 0, "bank": 0, "inventory": [], "job": "beggar", "last_work": 0}
        save_json(DATA_FILE, economy)
    
    changed = False
    if "inventory" not in economy[uid]:
        economy[uid]["inventory"] = []
        changed = True
    if "job" not in economy[uid]:
        economy[uid]["job"] = "beggar"
        changed = True
    if "last_work" not in economy[uid]:
        economy[uid]["last_work"] = 0
        changed = True
        
    if changed:
        save_json(DATA_FILE, economy)
        
    return economy[uid]

def update_balance(user_id, wallet_change=0, bank_change=0):
    uid = str(user_id)
    economy = load_json(DATA_FILE)
    profile = get_profile(user_id)
    
    economy[uid]["wallet"] = max(0, profile["wallet"] + wallet_change)
    economy[uid]["bank"] = max(0, profile["bank"] + bank_change)
    save_json(DATA_FILE, economy)

def add_to_inventory(user_id, item_name):
    uid = str(user_id)
    economy = load_json(DATA_FILE)
    get_profile(user_id)
    
    economy[uid]["inventory"].append(item_name)
    save_json(DATA_FILE, economy)

def set_user_job(user_id, job_name):
    uid = str(user_id)
    economy = load_json(DATA_FILE)
    get_profile(user_id)
    
    economy[uid]["job"] = job_name
    save_json(DATA_FILE, economy)

def update_work_timestamp(user_id):
    uid = str(user_id)
    economy = load_json(DATA_FILE)
    economy[uid]["last_work"] = int(time.time())
    save_json(DATA_FILE, economy)

# --- FLASK WEB ROUTING ---
@app.route('/', methods=['GET', 'POST'])
def index():
    shop_items = load_json(SHOP_FILE)

    if request.method == 'POST':
        name = request.form.get('name')
        price = request.form.get('price')
        image_file = request.files.get('image')
        image_url = ""

        if image_file and image_file.filename != '':
            ext = image_file.filename.split('.')[-1].lower()
            if ext in ALLOWED_EXTENSIONS:
                filename = f"item_{random.randint(1000,9999)}.{ext}"
                image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                base_url = request.url_root.rstrip('/')
                image_url = f"{base_url}/static/uploads/{filename}"
        
        if name and price:
            shop_items.append({"name": name.strip(), "price": int(price), "image_url": image_url})
            save_json(SHOP_FILE, shop_items)
            return redirect(url_for('index'))

    return render_template('admin.html', shop_items=shop_items)

# --- DISCORD APPLICATION BOT INTERFACE ---
class EconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Application slash tree synchronized globally!")

bot = EconomyBot()

@bot.event
async def on_ready():
    print(f"Connection established! Bot is active as: {bot.user.name}")

# --- USER ECONOMY SLASH COMMANDS ---

@bot.tree.command(name="bal", description="Checks the wallet and bank balances of a user.")
@app_commands.describe(member="The member whose balance you want to check (optional)")
async def bal(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)
    
    embed = discord.Embed(title=f"🏦 {target.name}'s Financial Portfolio", color=discord.Color.gold())
    embed.add_field(name="👛 Wallet", value=f"{profile['wallet']} coins", inline=True)
    embed.add_field(name="🏛️ Bank", value=f"{profile['bank']} coins", inline=True)
    embed.add_field(name="📊 Net Worth", value=f"{profile['wallet'] + profile['bank']} coins", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="deposit", description="Deposits coins from your wallet into your bank account.")
@app_commands.describe(amount="The amount of coins to deposit, or use 'all'")
async def deposit(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    wallet = profile["wallet"]
    
    if amount.lower() == "all":
        target_amount = wallet
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message("❌ Provide a valid integer amount or use 'all'.", ephemeral=True)
            
    if target_amount <= 0:
        return await interaction.response.send_message("❌ You cannot deposit zero or negative amounts!", ephemeral=True)
    if target_amount > wallet:
        return await interaction.response.send_message("❌ You do not have enough coins in your wallet!", ephemeral=True)
        
    update_balance(interaction.user.id, wallet_change=-target_amount, bank_change=target_amount)
    await interaction.response.send_message(f"📥 Successfully deposited **{target_amount} coins** into your bank!")

@bot.tree.command(name="withdraw", description="Withdraws coins from your bank account back into your wallet.")
@app_commands.describe(amount="The amount of coins to withdraw, or use 'all'")
async def withdraw(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    bank = profile["bank"]
    
    if amount.lower() == "all":
        target_amount = bank
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message("❌ Provide a valid integer amount or use 'all'.", ephemeral=True)
            
    if target_amount <= 0:
        return await interaction.response.send_message("❌ You cannot withdraw zero or negative amounts!", ephemeral=True)
    if target_amount > bank:
        return await interaction.response.send_message("❌ You do not have enough coins in your bank!", ephemeral=True)
        
    update_balance(interaction.user.id, wallet_change=target_amount, bank_change=-target_amount)
    await interaction.response.send_message(f"📤 Successfully withdrew **{target_amount} coins** into your wallet!")

# --- JOBS AND WORK CAREER ENGINE SYSTEM ---

@bot.tree.command(name="jobs", description="Lists available career paths and lets you choose a job.")
@app_commands.describe(join_job="Type the name of a job to enlist in that career field (optional)")
async def jobs(interaction: discord.Interaction, join_job: str = None):
    profile = get_profile(interaction.user.id)
    current_job = profile.get("job", "beggar")
    
    if join_job:
        target_job = join_job.strip().lower()
        if target_job not in JOBS_LIST:
            return await interaction.response.send_message(f"❌ Invalid job path! Use `/jobs` to review the lists.", ephemeral=True)
        
        set_user_job(interaction.user.id, target_job)
        return await interaction.response.send_message(f"💼 Congratulations! You are now employed as a **{target_job.capitalize()}**.")
        
    embed = discord.Embed(title="💼 Job Market Dashboard", description=f"Your Current Position: **{current_job.capitalize()}**\n\nTo apply for a position, use: `/jobs join_job:[Name]`\n", color=discord.Color.blue())
    
    for job_name, data in JOBS_LIST.items():
        embed.add_field(
            name=f"🛠️ {job_name.capitalize()}",
            value=f"**Pay Range:** {data['salary_min']} - {data['salary_max']} coins\n**Cooldown:** {data['cooldown']}s\n*{data['description']}*",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="work", description="Perform your active job tasks to earn shifting income.")
async def work(interaction: discord.Interaction):
    profile = get_profile(interaction.user.id)
    current_job = profile.get("job", "beggar")
    last_work = profile.get("last_work", 0)
    
    job_info = JOBS_LIST[current_job]
    current_time = int(time.time())
    elapsed = current_time - last_work
    
    if elapsed < job_info["cooldown"]:
        remaining = job_info["cooldown"] - elapsed
        return await interaction.response.send_message(f"⏳ Your shifts are exhausted! Please wait **{remaining}s** before working again.", ephemeral=True)
        
    earnings = random.randint(job_info["salary_min"], job_info["salary_max"])
    update_balance(interaction.user.id, wallet_change=earnings)
    update_work_timestamp(interaction.user.id)
