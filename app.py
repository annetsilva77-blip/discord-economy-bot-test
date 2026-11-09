import os
import json
import random
import threading
import asyncio
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
        economy[uid] = {"wallet": 0, "bank": 0, "inventory": []}
        save_json(DATA_FILE, economy)
    if "inventory" not in economy[uid]:
        economy[uid]["inventory"] = []
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
            item_id = len(shop_items) + 1
            shop_items.append({"id": item_id, "name": name.strip(), "price": int(price), "image_url": image_url})
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

@bot.tree.command(name="shop", description="Displays all functional items listed for purchase.")
async def shop(interaction: discord.Interaction):
    shop_items = load_json(SHOP_FILE)
    if not shop_items:
        return await interaction.response.send_message("🛒 The shop inventory is empty! Visit the website panel to add items.", ephemeral=True)
        
    await interaction.response.defer()
    
    for item in shop_items:
        embed = discord.Embed(
            title=f"📦 {item['name']}", 
            description=f"Cost: **{item['price']} coins**", 
            color=discord.Color.green()
        )
        if item.get("image_url"):
            embed.set_image(url=item["image_url"])
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="buy", description="Purchase an item using its name.")
@app_commands.describe(item_name="The exact name of the item from the shop")
async def buy(interaction: discord.Interaction, item_name: str):
    shop_items = load_json(SHOP_FILE)
    profile = get_profile(interaction.user.id)
    
    # Clean the input to avoid spacing mismatches
    target_name = item_name.strip().lower()
    
    # Look up the item by matching names completely
    item = next((i for i in shop_items if i["name"].lower() == target_name), None)
    
    if not item:
        return await interaction.response.send_message("❌ That item does not exist in the shop! Check spelling in `/shop`.", ephemeral=True)
        
    if profile["wallet"] < item["price"]:
        return await interaction.response.send_message(f"❌ You need **{item['price']} coins** in your wallet to buy this item!", ephemeral=True)
        
    # Deduct funds and move the named item directly into their user profile storage account
    update_balance(interaction.user.id, wallet_change=-item["price"])
    add_to_inventory(interaction.user.id, item["name"])
    
    await interaction.response.send_message(f"🎉 Successfully purchased **{item['name']}** for **{item['price']} coins**! Type `/inventory` to check it out.")

@bot.tree.command(name="inventory", description="View all the premium items you have purchased.")
@app_commands.describe(member="The member whose inventory you want to check (optional)")
async def inventory(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)
    user_inventory = profile.get("inventory", [])
    
    if not user_inventory:
        return await interaction.response.send_message(f"🎒 {target.name}'s inventory is currently empty!", ephemeral=member is not None)
        
    counts = {}
    for item in user_inventory:
        counts[item] = counts.get(item, 0) + 1
        
    inv_list = "\n".join([f"• **{name}** x{qty}" for name, qty in counts.items()])
    
    embed = discord.Embed(title=f"🎒 {target.name}'s Storage Inventory", description=inv_list, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# --- ADMIN SYSTEM OVERRIDE COMMANDS ---
@bot.tree.command(name="addmoney", description="Adds money to a user's wallet (Admin/Owner only).")
@app_commands.describe(member="The member to give coins to", amount="The number of coins to give")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    is_owner = interaction.user.id == OWNER_ID
    is_admin = interaction.permissions.administrator if interaction.guild else False

    if not (is_owner or is_admin):
        return await interaction.response.send_message("❌ You do not have permission to run this command.", ephemeral=True)

    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be greater than 0!", ephemeral=True)

    update_balance(member.id, wallet_change=amount)
    await interaction.response.send_message(f"✅ Added **{amount} coins** to {member.mention}'s wallet!")

# --- CONCURRENT BACKGROUND WORKSPACE RUNNERS ---
def run_discord_bot():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: 'DISCORD_TOKEN' variable missing!")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(token))

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_discord_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
