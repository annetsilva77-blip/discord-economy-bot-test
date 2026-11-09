
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
from werkzeug.utils import secure_filename

OWNER_ID = 1327939431608483895

SHOP_FILE = "shop.json"
DATA_FILE = "economy_data.json"
UPLOAD_FOLDER = "static/uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

JOBS_LIST = {
    "beggar": {
        "salary_min": 10,
        "salary_max": 40,
        "cooldown": 30,
        "description": "Beg strangers for spare change on the street corner."
    },
    "gamer": {
        "salary_min": 50,
        "salary_max": 150,
        "cooldown": 60,
        "description": "Stream voxel sandbox games and build a digital fanbase."
    },
    "developer": {
        "salary_min": 150,
        "salary_max": 450,
        "cooldown": 120,
        "description": "Write cloud systems, microcontrollers, and custom Discord bots."
    }
}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATA_LOCK = threading.RLock()


def load_json(filename):
    with DATA_LOCK:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        return [] if filename == SHOP_FILE else {}


def save_json(filename, data):
    with DATA_LOCK:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


def ensure_profile(economy, user_id):
    uid = str(user_id)

    if uid not in economy or not isinstance(economy[uid], dict):
        economy[uid] = {
            "wallet": 0,
            "bank": 0,
            "inventory": [],
            "job": "beggar",
            "last_work": 0
        }

    profile = economy[uid]

    profile.setdefault("wallet", 0)
    profile.setdefault("bank", 0)
    profile.setdefault("inventory", [])
    profile.setdefault("job", "beggar")
    profile.setdefault("last_work", 0)

    if profile["job"] not in JOBS_LIST:
        profile["job"] = "beggar"

    return profile


def get_profile(user_id):
    with DATA_LOCK:
        economy = load_json(DATA_FILE)
        profile = ensure_profile(economy, user_id)
        save_json(DATA_FILE, economy)
        return dict(profile)


def update_balance(user_id, wallet_change=0, bank_change=0):
    with DATA_LOCK:
        economy = load_json(DATA_FILE)
        profile = ensure_profile(economy, user_id)

        profile["wallet"] = max(0, profile["wallet"] + wallet_change)
        profile["bank"] = max(0, profile["bank"] + bank_change)

        save_json(DATA_FILE, economy)


def add_to_inventory(user_id, item_name):
    with DATA_LOCK:
        economy = load_json(DATA_FILE)
        profile = ensure_profile(economy, user_id)

        profile["inventory"].append(item_name)

        save_json(DATA_FILE, economy)


def set_user_job(user_id, job_name):
    with DATA_LOCK:
        economy = load_json(DATA_FILE)
        profile = ensure_profile(economy, user_id)

        profile["job"] = job_name

        save_json(DATA_FILE, economy)


def update_work_timestamp(user_id):
    with DATA_LOCK:
        economy = load_json(DATA_FILE)
        profile = ensure_profile(economy, user_id)

        profile["last_work"] = int(time.time())

        save_json(DATA_FILE, economy)


@app.route("/", methods=["GET", "POST"])
def index():
    shop_items = load_json(SHOP_FILE)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()
        image_file = request.files.get("image")

        if not name or not price:
            return "Please enter an item name and price.", 400

        try:
            item_price = int(price)
            if item_price <= 0:
                return "Price must be greater than zero.", 400
        except ValueError:
            return "Invalid price.", 400

        image_url = ""

        if image_file and image_file.filename:
            safe_name = secure_filename(image_file.filename)
            ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""

            if ext in ALLOWED_EXTENSIONS:
                filename = f"item_{int(time.time())}_{random.randint(1000, 9999)}.{ext}"
                image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                image_url = url_for(
                    "static",
                    filename=f"uploads/{filename}",
                    _external=True
                )

        shop_items.append({
            "name": name,
            "price": item_price,
            "image_url": image_url
        })

        save_json(SHOP_FILE, shop_items)

        return redirect(url_for("index"))

    return render_template("admin.html", shop_items=shop_items)


class EconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synchronized.")


bot = EconomyBot()


@bot.event
async def on_ready():
    print(f"Logged in as: {bot.user}")


@bot.tree.command(name="bal", description="Checks your wallet and bank balances.")
@app_commands.describe(member="The member whose balance you want to check")
async def bal(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)

    embed = discord.Embed(
        title=f"🏦 {target.name}'s Financial Portfolio",
        color=discord.Color.gold()
    )

    embed.add_field(name="👛 Wallet", value=f"{profile['wallet']} coins")
    embed.add_field(name="🏛️ Bank", value=f"{profile['bank']} coins")
    embed.add_field(
        name="📊 Net Worth",
        value=f"{profile['wallet'] + profile['bank']} coins",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="deposit", description="Deposits coins into your bank.")
@app_commands.describe(amount="Amount of coins to deposit, or all")
async def deposit(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    wallet = profile["wallet"]

    if amount.lower() == "all":
        target_amount = wallet
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Enter a valid number or 'all'.",
                ephemeral=True
            )

    if target_amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if target_amount > wallet:
        return await interaction.response.send_message(
            "❌ You don't have enough coins in your wallet.",
            ephemeral=True
        )

    update_balance(
        interaction.user.id,
        wallet_change=-target_amount,
        bank_change=target_amount
    )

    await interaction.response.send_message(
        f"📥 Deposited **{target_amount} coins** into your bank!"
    )


@bot.tree.command(name="withdraw", description="Withdraws coins from your bank.")
@app_commands.describe(amount="Amount of coins to withdraw, or all")
async def withdraw(interaction: discord.Interaction, amount: str):
    profile = get_profile(interaction.user.id)
    bank = profile["bank"]

    if amount.lower() == "all":
        target_amount = bank
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Enter a valid number or 'all'.",
                ephemeral=True
            )

    if target_amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if target_amount > bank:
        return await interaction.response.send_message(
            "❌ You don't have enough coins in your bank.",
            ephemeral=True
        )

    update_balance(
        interaction.user.id,
        wallet_change=target_amount,
        bank_change=-target_amount
    )

    await interaction.response.send_message(
        f"📤 Withdrew **{target_amount} coins** into your wallet!"
    )


@bot.tree.command(name="slots", description="Play the virtual coin slot game.")
@app_commands.describe(bet="The number of virtual coins to bet")
@app_commands.checks.cooldown(1, 10.0)
async def slots(interaction: discord.Interaction, bet: int):
    profile = get_profile(interaction.user.id)

    if bet <= 0:
        return await interaction.response.send_message(
            "❌ Bet must be greater than zero.",
            ephemeral=True
        )

    if bet > profile["wallet"]:
        return await interaction.response.send_message(
            "❌ You don't have enough coins.",
            ephemeral=True
        )

    emojis = ["🍒", "🍇", "🍊", "💎", "🎰"]
    slot1, slot2, slot3 = random.choices(emojis, k=3)

    slot_display = f"[ {slot1} | {slot2} | {slot3} ]"

    if slot1 == slot2 == slot3:
        winnings = bet * 3
        update_balance(interaction.user.id, wallet_change=-bet + winnings)

        await interaction.response.send_message(
            f"{slot_display}\n🎉 **JACKPOT!** You won **{winnings} coins**!"
        )

    elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
        winnings = bet
        update_balance(interaction.user.id, wallet_change=-bet + winnings)

        await interaction.response.send_message(
            f"{slot_display}\n🙂 **Match 2!** Your bet was returned: **{winnings} coins**!"
        )

    else:
        update_balance(interaction.user.id, wallet_change=-bet)

        await interaction.response.send_message(
            f"{slot_display}\n😢 **You lost!** You lost **{bet} coins**."
        )


@bot.tree.command(name="jobs", description="Lists available jobs and lets you choose one.")
@app_commands.describe(join_job="Name of the job you want to join")
async def jobs(interaction: discord.Interaction, join_job: str = None):
    profile = get_profile(interaction.user.id)
    current_job = profile.get("job", "beggar")

    if join_job:
        target_job = join_job.strip().lower()

        if target_job not in JOBS_LIST:
            return await interaction.response.send_message(
                "❌ Invalid job path! Type `/jobs` to view valid listings.",
                ephemeral=True
            )

        set_user_job(interaction.user.id, target_job)

        return await interaction.response.send_message(
            f"💼 Employment contract updated! You are now working as a **{target_job.capitalize()}**."
        )

    embed = discord.Embed(
        title="💼 Job Market Dashboard",
        description=(
            f"Your Active Position: **{current_job.capitalize()}**\n\n"
            "To apply for a vacancy, type `/jobs join_job:[Name]`."
        ),
        color=discord.Color.blue()
    )

    for job_name, data in JOBS_LIST.items():
        embed.add_field(
            name=f"🛠️ {job_name.capitalize()}",
            value=(
                f"Pay Scales: {data['salary_min']} - {data['salary_max']} coins\n"
                f"Cooldown: {data['cooldown']} seconds\n"
                f"*{data['description']}*"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="work", description="Work your job to earn virtual coins.")
async def work(interaction: discord.Interaction):
    profile = get_profile(interaction.user.id)

    current_job = profile.get("job", "beggar")

    if current_job not in JOBS_LIST:
        current_job = "beggar"

    last_work = profile.get("last_work", 0)
    job_info = JOBS_LIST[current_job]

    current_time = int(time.time())
    elapsed = current_time - last_work

    if elapsed < job_info["cooldown"]:
        remaining = job_info["cooldown"] - elapsed

        return await interaction.response.send_message(
            f"⏳ Your shift is on cooldown! Return in {remaining} seconds.",
            ephemeral=True
        )

    earnings = random.randint(
        job_info["salary_min"],
        job_info["salary_max"]
    )

    update_balance(interaction.user.id, wallet_change=earnings)
    update_work_timestamp(interaction.user.id)

    await interaction.response.send_message(
        f"💰 You completed a shift as a **{current_job.capitalize()}** and earned **{earnings} coins**!"
    )


@bot.tree.command(name="shop", description="Displays all available shop items.")
async def shop(interaction: discord.Interaction):
    shop_items = load_json(SHOP_FILE)

    if not shop_items:
        return await interaction.response.send_message(
            "🛒 The shop is empty!",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🛒 Active Economy Shop",
        color=discord.Color.green()
    )

    shop_list_text = ""
    last_image_url = None

    for item in shop_items:
        shop_list_text += (
            f"📦 **{item['name']}**\n"
            f"└ 💰 Cost: `{item['price']} coins`\n\n"
        )

        if item.get("image_url"):
            last_image_url = item["image_url"]

    embed.description = shop_list_text[:4000]

    if last_image_url:
        embed.set_thumbnail(url=last_image_url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="buy", description="Purchase an item from the shop.")
@app_commands.describe(item_name="The exact product name")
async def buy(interaction: discord.Interaction, item_name: str):
    shop_items = load_json(SHOP_FILE)
    profile = get_profile(interaction.user.id)

    target_name = item_name.strip().lower()

    item = next(
        (i for i in shop_items if i["name"].lower() == target_name),
        None
    )

    if not item:
        return await interaction.response.send_message(
            "❌ Product not found! Check the `/shop` listing.",
            ephemeral=True
        )

    if profile["wallet"] < item["price"]:
        return await interaction.response.send_message(
            f"❌ You need {item['price']} coins in your wallet.",
            ephemeral=True
        )

    update_balance(
        interaction.user.id,
        wallet_change=-item["price"]
    )

    add_to_inventory(interaction.user.id, item["name"])

    await interaction.response.send_message(
        f"🎉 You bought **{item['name']}** for **{item['price']} coins**! Check `/inventory`."
    )


@bot.tree.command(name="inventory", description="Checks your inventory.")
@app_commands.describe(member="The member whose inventory you want to check")
async def inventory(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)

    user_inventory = profile.get("inventory", [])

    if not user_inventory:
        return await interaction.response.send_message(
            f"🎒 {target.name}'s inventory is empty!",
            ephemeral=member is not None
        )

    counts = {}

    for item in user_inventory:
        counts[item] = counts.get(item, 0) + 1

    inv_list = "\n".join(
        [f"🎒 **{name}** `x{qty}`" for name, qty in counts.items()]
    )

    embed = discord.Embed(
        title=f"🎒 {target.name}'s Storage Inventory",
        description=inv_list[:4000],
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="addmoney", description="Adds virtual coins to a player's wallet.")
@app_commands.describe(
    member="The player receiving coins",
    amount="The number of coins to add"
)
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    is_owner = interaction.user.id == OWNER_ID
    is_admin = (
        interaction.permissions.administrator
        if interaction.guild
        else False
    )

    if not (is_owner or is_admin):
        return await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    update_balance(member.id, wallet_change=amount)

    await interaction.response.send_message(
        f"✅ Added **{amount} coins** to {member.mention}'s wallet!"
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        message = f"⏳ Slow down! Try again in {error.retry_after:.2f} seconds."
    else:
        print(f"Command error: {error}")
        message = "❌ Something went wrong while running that command."

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def run_discord_bot():
    token = os.environ.get("DISCORD_TOKEN")

    if not token:
        print("❌ DISCORD_TOKEN environment variable was not found.")
        return

    asyncio.run(bot.start(token))


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )
