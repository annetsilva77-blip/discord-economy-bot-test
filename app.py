import os
import json
import threading
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, render_template, request, redirect, url_for

# Global configuration constants
OWNER_ID = 1327939431608483895
SHOP_FILE = "shop.json"

app = Flask(__name__)

def load_shop():
    """Loads the database configurations safely from our persistent JSON cache file."""
    if os.path.exists(SHOP_FILE):
        try:
            with open(SHOP_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_shop(data):
    """Writes the updated array mapping back to file system."""
    with open(SHOP_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- FLASK WEB ROUTING ---
@app.route('/', methods=['GET', 'POST'])
def index():
    user_auth = request.args.get('owner_id')
    is_owner = (user_auth == str(OWNER_ID))
    shop_items = load_shop()

    if request.method == 'POST':
        if not is_owner:
            return "Unauthorized: Action strictly restricted to application creator.", 403
        
        name = request.form.get('name')
        price = request.form.get('price')
        
        if name and price:
            shop_items.append({"name": name, "price": int(price)})
            save_shop(shop_items)
            return redirect(url_for('index', owner_id=OWNER_ID))

    return render_template('admin.html', shop_items=shop_items, is_owner=is_owner)

# --- DISCORD APPLICATION BOT INTERFACE ---
class ShopBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Syncs the commands globally inside Discord systems
        await self.tree.sync()
        print("Application tree synchronized across global regions successfully!")

bot = ShopBot()

@bot.event
async def on_ready():
    print(f"Connection established! Logged in as: {bot.user.name}")

@bot.tree.command(name="shop", description="Displays all functional items listed for purchase and costs.")
async def shop(interaction: discord.Interaction):
    shop_items = load_shop()
    if not shop_items:
        return await interaction.response.send_message("🛒 The item inventory shop is currently empty! Ask the owner to add items.", ephemeral=True)
        
    embed = discord.Embed(
        title="🛒 Active Economy Shop", 
        description="Browse the items below and use your coins to purchase premium items!", 
        color=discord.Color.green()
    )
    for item in shop_items:
        embed.add_field(name=f"📦 {item['name']}", value=f"Cost: **{item['price']} coins**", inline=False)
        
    await interaction.response.send_message(embed=embed)

# --- ENGINE WORKSPACE THREAD RUNNERS ---
def run_discord_bot():
    """Runs the live bot application framework safely inside a background thread loop."""
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ CRITICAL ERROR: 'DISCORD_TOKEN' environment variable is missing in Render settings!")
        return
        
    # Create a fresh event loop specifically for the Discord bot thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start(token))

if __name__ == "__main__":
    # 1. Launch the Discord bot in a separate background thread
    bot_thread = threading.Thread(target=run_discord_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # 2. Run the Flask Web Server on the MAIN thread so Render detects it instantly
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
