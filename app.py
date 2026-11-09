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

# Global configuration variables
OWNER_ID = 1327939431608483895
SHOP_FILE = "shop.json"
DATA_FILE = "economy_data.json"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Career paths structure dictionary layout 
JOBS_LIST = {
    "beggar": {"salary_min": 10, "salary_max": 40, "cooldown": 30, "description": "Beg strangers for spare change on the street corner."},
    "gamer": {"salary_min": 50, "salary_max": 150, "cooldown": 60, "description": "Stream voxel sandbox games and build a digital fanbase."},
    "developer": {"salary_min": 150, "salary_max": 450, "cooldown": 120, "description": "Write cloud systems, microcontrollers, and custom discord bots."}
}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Auto-create image storage folders inside the virtual container 
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- ENGINE DATA HANDLING ---
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
    
    # Enforce profile schema structure upgrades
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

# --- FLASK PUBLIC WEB ROUTING ---
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

# --- DISCORD CORE MASTER SYSTEMS ---
class EconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Bot tree commands synchronized globally across Discord networks.")

bot = EconomyBot()

@bot.event
async def on_ready():
    print(f"Logged in and active as: {bot.user.name}")

# --- ECONOMY USER SLASH COMMANDS ---

@bot.tree.command(name="bal", description="Checks your wallet and bank portfolio balances.")
@app_commands.describe(member="The member whose balance you want to verify (optional)")
async def bal(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)
    
    embed = discord.Embed(title=f"🏦 {target.name}'s Financial Portfolio", color=discord.Color.gold())
    embed.add_field(name="👛 Wallet", value=f"{profile['wallet']} coins", inline=True)
    embed.add_field(name="🏛️ Bank", value=f"{profile['bank']} coins", inline=True)
    embed.add_field(name="📊 Net Worth", value=f"{profile['wallet'] + profile['bank']} coins", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="deposit", description="Deposits coins out of your wallet safely into your bank ledger.")
@app_commands.describe(amount="The specific number of coins to deposit, or use 'all'")
async def deposit(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    wallet = profile["wallet"]
    
    if amount.lower() == "all":
        target_amount = wallet
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message("❌ Please provide a valid integer amount or 'all'.", ephemeral=True)
            
    if target_amount <= 0:
        return await interaction.response.send_message("❌ You cannot deposit zero or negative amounts!", ephemeral=True)
    if target_amount > wallet:
        return await interaction.response.send_message("❌ You do not hold that much wealth inside your wallet!", ephemeral=True)
        
    update_balance(interaction.user.id, wallet_change=-target_amount, bank_change=target_amount)
    await interaction.response.send_message(f"📥 Successfully deposited **{target_amount} coins** into your bank!")

@bot.tree.command(name="withdraw", description="Withdraws stored coins out of your bank ledger back into your wallet.")
@app_commands.describe(amount="The specific number of coins to withdraw, or use 'all'")
async def withdraw(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    bank = profile["bank"]
    
    if amount.lower() == "all":
        target_amount = bank
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message("❌ Please provide a valid integer amount or 'all'.", ephemeral=True)
            
    if target_amount <= 0:
        return await interaction.response.send_message("❌ You cannot withdraw zero or negative amounts!", ephemeral=True)
    if target_amount > bank:
        return await interaction.response.send_message("❌ You do not have that many coins inside your bank ledger!", ephemeral=True)
        
    update_balance(interaction.user.id, wallet_change=target_amount, bank_change=-target_amount)
    await interaction.response.send_message(f"📤 Successfully withdrew **{target_amount} coins** into your wallet!")

# --- JOBS AND WORK SHIFT MODULE ---

@bot.tree.command(name="jobs", description="Lists the employment market boards and lets you choose a career.")
@app_commands.describe(join_job="Type the name of a career route path to enlist (optional)")
async def jobs(interaction: discord.Interaction, join_job: str = None):
    profile = get_profile(interaction.user.id)
    current_job = profile.get("job", "beggar")
    
    if join_job:
        target_job = join_job.strip().lower()
        if target_job not in JOBS_LIST:
            return await interaction.response.send_message(f"❌ Invalid job path! Type `/jobs` to view valid listings.", ephemeral=True)
        
        set_user_job(interaction.user.id, target_job)
        return await interaction.response.send_message(f"💼 Employment contract updated! You are now working as a **{target_job.capitalize()}**.")
        
    embed = discord.Embed(title="💼 Job Market Dashboard", description=f"Your Active Position: **{current_job.capitalize()}**\n\nTo apply for a vacancy, type: `/jobs join_job:[Name]`\n", color=discord.Color.blue())
    
    for job_name, data in JOBS_LIST.items():
        embed.add_field(
            name=f"🛠️ {job_name.capitalize()}",
            value=f"**Pay Scales:** {data['salary_min']} - {data['salary_max']} coins\n**Cooldown:** {data['cooldown']} seconds\n*{data['description']}*",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="work", description="Complete active employment operational tasks to receive salary funds.")
async def work(interaction: discord.Interaction):
    profile = get_profile(interaction.user.id)
    current_job = profile.get("job", "beggar")
    last_work = profile.get("last_work", 0)
    
    job_info = JOBS_LIST[current_job]
    current_time = int(time.time())
    elapsed = current_time - last_work
    earnings = random.randint(job_info["salary_min"], job_info["salary_max"])
update_balance(interaction.user.id, wallet_change=earnings)
update_work_timestamp(interaction.user.id)
await interaction.response.send_message(f"💰 You completed a work shift as a {current_job.capitalize()} and received {earnings} coins!")

--- SHOPPING ENGINE PROTOCOLS ---

@bot.tree.command(name="shop", description="Displays all item inventories loaded through the web panel portal.")
async def shop(interaction: discord.Interaction):
shop_items = load_json(SHOP_FILE)
if not shop_items:
return await interaction.response.send_message("🛒 The item stock rooms are empty! Use the web dashboard panel to list products.", ephemeral=True)
await interaction.response.defer()
for item in shop_items:
embed = discord.Embed(
title=f"📦 {item['name']}",
description=f"Cost Vector: {item['price']} coins",
color=discord.Color.green()
)
if item.get("image_url"):
embed.set_image(url=item["image_url"])
await interaction.followup.send(embed=embed)
@bot.tree.command(name="buy", description="Purchase items from store stocks matching product names completely.")
@app_commands.describe(item_name="The exact product title shown under the store catalog layout")
async def buy(interaction: discord.Interaction, item_name: str):
shop_items = load_json(SHOP_FILE)
profile = get_profile(interaction.user.id)
target_name = item_name.strip().lower()
item = next((i for i in shop_items if i["name"].lower() == target_name), None)
if not item:
return await interaction.response.send_message("❌ Product not located! Ensure name syntax matches the /shop listing exactly.", ephemeral=True)
if profile["wallet"] < item["price"]:
return await interaction.response.send_message(f"❌ Transaction failed. You require {item['price']} coins in your wallet wallet to purchase this item.", ephemeral=True)
update_balance(interaction.user.id, wallet_change=-item["price"])
add_to_inventory(interaction.user.id, item["name"])
await interaction.response.send_message(f"🎉 Acquisition confirmed! {item['name']} bought for {item['price']} coins. Review your items via /inventory.")
@bot.tree.command(name="inventory", description="Checks your storage container inventory lists.")
@app_commands.describe(member="The member whose inventory stack you want to inspect (optional)")
async def inventory(interaction: discord.Interaction, member: discord.Member = None):
target = member or interaction.user
profile = get_profile(target.id)
user_inventory = profile.get("inventory", [])
if not user_inventory:
return await interaction.response.send_message(f"🎒 {target.name}'s inventory ledger is empty!", ephemeral=member is not None)
counts = {}
for item in user_inventory:
counts[item] = counts.get(item, 0) + 1
inv_list = "\n".join([f"• {name} x{qty}" for name, qty in counts.items()])
embed = discord.Embed(title=f"🎒 {target.name}'s Storage Inventory", description=inv_list, color=discord.Color.blue())
await interaction.response.send_message(embed=embed)

--- OVERRIDE ADMINISTRATIVE TOOLS ---

@bot.tree.command(name="addmoney", description="Grants specified coin amounts directly to wallet nodes (Admins/Owner Only).")
@app_commands.describe(member="The player node receiving funding", amount="The specific value amount of coins to transfer")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
is_owner = interaction.user.id == OWNER_ID
is_admin = interaction.permissions.administrator if interaction.guild else False
if not (is_owner or is_admin):
return await interaction.response.send_message("❌ Command execution rejected. Insufficient security credentials.", ephemeral=True)
if amount <= 0:
return await interaction.response.send_message("❌ Transaction error: Input value must exceed 0.", ephemeral=True)
update_balance(member.id, wallet_change=amount)
await interaction.response.send_message(f"✅ Secure injection complete! {amount} coins deposited to {member.mention}'s wallet node.")

--- BACKGROUND RUNNER ENGINES ---

def run_discord_bot():
token = os.environ.get("DISCORD_TOKEN")
if not token:
print("❌ CRITICAL ERROR: Environment variable 'DISCORD_TOKEN' was not found.")
return
# Establish a fresh async context explicitly bound to Python 3.14 runner layers
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
loop.run_until_complete(bot.start(token))
if name == "main":
# 1. Spawn Discord loops inside their own isolated background worker channel threads
bot_thread = threading.Thread(target=run_discord_bot)
bot_thread.daemon = True
bot_thread.start()
# 2. Bind Flask directly to the primary system entry process thread
port = int(os.environ.get("PORT", 10000))
app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    if elapsed < job_info["cooldown"]:
        remaining = job_info["cooldown"] - elapsed
        return await interaction.response.send_message(f"⏳ Shift constraints active! Return to work in **{remaining} seconds**.", ephemeral=True)
        
