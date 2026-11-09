
import os
import json
import random
import threading
import asyncio
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from flask import Flask, request, redirect, url_for, render_template_string
from werkzeug.utils import secure_filename

OWNER_ID = 1327939431608483895

SHOP_FILE = "shop.json"
DATA_FILE = "economy_data.json"
UPLOAD_FOLDER = "static/uploads"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

file_lock = threading.RLock()

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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024


# ---------------- JSON DATABASE ----------------

def load_json(filename):
    with file_lock:
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if filename == SHOP_FILE:
                    return data if isinstance(data, list) else []

                return data if isinstance(data, dict) else {}

            except (json.JSONDecodeError, OSError):
                return [] if filename == SHOP_FILE else {}

        return [] if filename == SHOP_FILE else {}


def save_json(filename, data):
    with file_lock:
        temp_file = filename + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        os.replace(temp_file, filename)


def get_profile(user_id):
    uid = str(user_id)

    with file_lock:
        economy = load_json(DATA_FILE)

        if uid not in economy:
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

        save_json(DATA_FILE, economy)

        return profile.copy()


def update_balance(user_id, wallet_change=0, bank_change=0):
    uid = str(user_id)

    with file_lock:
        economy = load_json(DATA_FILE)

        if uid not in economy:
            get_profile(user_id)
            economy = load_json(DATA_FILE)

        economy[uid]["wallet"] = max(
            0, economy[uid]["wallet"] + wallet_change
        )

        economy[uid]["bank"] = max(
            0, economy[uid]["bank"] + bank_change
        )

        save_json(DATA_FILE, economy)


def add_to_inventory(user_id, item_name):
    uid = str(user_id)

    with file_lock:
        economy = load_json(DATA_FILE)

        if uid not in economy:
            get_profile(user_id)
            economy = load_json(DATA_FILE)

        economy[uid]["inventory"].append(item_name)

        save_json(DATA_FILE, economy)


def set_user_job(user_id, job_name):
    uid = str(user_id)

    with file_lock:
        economy = load_json(DATA_FILE)

        if uid not in economy:
            get_profile(user_id)
            economy = load_json(DATA_FILE)

        economy[uid]["job"] = job_name

        save_json(DATA_FILE, economy)


def update_work_timestamp(user_id):
    uid = str(user_id)

    with file_lock:
        economy = load_json(DATA_FILE)

        if uid not in economy:
            get_profile(user_id)
            economy = load_json(DATA_FILE)

        economy[uid]["last_work"] = int(time.time())

        save_json(DATA_FILE, economy)


# ---------------- FLASK WEB DASHBOARD ----------------

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Cardex Shop Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            background: #101827;
            color: white;
            font-family: Arial;
            padding: 30px;
        }

        .container {
            max-width: 700px;
            margin: auto;
        }

        .panel {
            background: #1e293b;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }

        input, button {
            width: 100%;
            padding: 12px;
            margin: 8px 0;
            box-sizing: border-box;
            border-radius: 6px;
            border: none;
        }

        button {
            background: #2563eb;
            color: white;
            cursor: pointer;
            font-weight: bold;
        }

        .item {
            background: #334155;
            padding: 15px;
            border-radius: 8px;
            margin-top: 12px;
        }

        img {
            max-width: 150px;
            display: block;
            margin-top: 10px;
            border-radius: 8px;
        }
    </style>
</head>

<body>
<div class="container">

    <h1>🛒 Cardex Shop Dashboard</h1>

    <div class="panel">
        <h2>Add New Item</h2>

        <form method="POST" enctype="multipart/form-data">

            <input type="text" name="name"
                placeholder="Item name" maxlength="100" required>

            <input type="number" name="price"
                placeholder="Item price" min="1" required>

            <input type="file" name="image"
                accept=".png,.jpg,.jpeg,.gif,.webp">

            <button type="submit">Add Item</button>

        </form>
    </div>

    <div class="panel">
        <h2>Shop Inventory</h2>

        {% for item in shop_items %}

        <div class="item">

            <h3>{{ item.name }}</h3>

            <p>Price: {{ item.price }} coins</p>

            {% if item.image_url %}
                <img src="{{ item.image_url }}">
            {% endif %}

        </div>

        {% else %}

        <p>No items available.</p>

        {% endfor %}

    </div>

</div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():

    shop_items = load_json(SHOP_FILE)

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()

        image_file = request.files.get("image")
        image_url = ""

        if not name or len(name) > 100:
            return "Invalid item name.", 400

        try:
            price = int(price)

            if price <= 0:
                return "Price must be greater than zero.", 400

        except (ValueError, TypeError):
            return "Invalid price.", 400

        if image_file and image_file.filename:

            safe_name = secure_filename(image_file.filename)
            ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""

            if ext not in ALLOWED_EXTENSIONS:
                return "Invalid image format.", 400

            filename = f"item_{uuid.uuid4().hex}.{ext}"

            image_file.save(
                os.path.join(app.config["UPLOAD_FOLDER"], filename)
            )

            image_url = url_for(
                "static",
                filename=f"uploads/{filename}",
                _external=True
            )

        shop_items.append({
            "name": name,
            "price": price,
            "image_url": image_url
        })

        save_json(SHOP_FILE, shop_items)

        return redirect(url_for("index"))

    return render_template_string(
        HTML_PAGE,
        shop_items=shop_items
    )


# ---------------- DISCORD BOT ----------------

class EconomyBot(commands.Bot):

    def __init__(self):

        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):

        await self.tree.sync()

        print("Discord slash commands synchronized.")


bot = EconomyBot()


@bot.event
async def on_ready():

    print(f"Logged in as: {bot.user}")


# ---------------- BALANCE ----------------

@bot.tree.command(
    name="bal",
    description="Checks your wallet and bank balances."
)
@app_commands.describe(
    member="The member whose balance you want to check"
)
async def bal(
    interaction: discord.Interaction,
    member: discord.Member = None
):

    target = member or interaction.user

    profile = get_profile(target.id)

    embed = discord.Embed(
        title=f"🏦 {target.name}'s Financial Portfolio",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="👛 Wallet",
        value=f"{profile['wallet']} coins",
        inline=True
    )

    embed.add_field(
        name="🏛️ Bank",
        value=f"{profile['bank']} coins",
        inline=True
    )

    embed.add_field(
        name="📊 Net Worth",
        value=f"{profile['wallet'] + profile['bank']} coins",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# ---------------- DEPOSIT ----------------

@bot.tree.command(
    name="deposit",
    description="Deposits coins into your bank."
)
@app_commands.describe(
    amount="Number of coins to deposit or all"
)
async def deposit(
    interaction: discord.Interaction,
    amount: str
):

    profile = get_profile(interaction.user.id)

    wallet = profile["wallet"]

    if amount.lower() == "all":
        target_amount = wallet
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Enter a valid amount or all.",
                ephemeral=True
            )

    if target_amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if target_amount > wallet:
        return await interaction.response.send_message(
            "❌ Not enough coins in your wallet.",
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


# ---------------- WITHDRAW ----------------

@bot.tree.command(
    name="withdraw",
    description="Withdraws coins from your bank."
)
@app_commands.describe(
    amount="Number of coins to withdraw or all"
)
async def withdraw(
    interaction: discord.Interaction,
    amount: str
):

    profile = get_profile(interaction.user.id)

    bank = profile["bank"]

    if amount.lower() == "all":
        target_amount = bank
    else:
        try:
            target_amount = int(amount)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Enter a valid amount or all.",
                ephemeral=True
            )

    if target_amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if target_amount > bank:
        return await interaction.response.send_message(
            "❌ Not enough coins in your bank.",
            ephemeral=True
        )

    update_balance(
        interaction.user.id,
        wallet_change=target_amount,
        bank_change=-target_amount
    )

    await interaction.response.send_message(
        f"📤 Withdrew **{target_amount} coins**!"
    )


# ---------------- SLOTS ----------------

@bot.tree.command(
    name="slots",
    description="Play the virtual coin slot game."
)
@app_commands.describe(
    bet="Number of virtual coins"
)
@app_commands.checks.cooldown(1, 10.0)
async def slots(
    interaction: discord.Interaction,
    bet: int
):

    profile = get_profile(interaction.user.id)

    wallet = profile["wallet"]

    if bet <= 0:
        return await interaction.response.send_message(
            "❌ Bet must be greater than zero!",
            ephemeral=True
        )

    if bet > wallet:
        return await interaction.response.send_message(
            "❌ Not enough coins in your wallet.",
            ephemeral=True
        )

    emojis = ["🍒", "🍇", "🍊", "💎", "🎰"]

    slot1, slot2, slot3 = random.choices(emojis, k=3)

    slot_display = f"[ {slot1} | {slot2} | {slot3} ]"

    if slot1 == slot2 == slot3:

        winnings = bet * 3

        update_balance(
            interaction.user.id,
            wallet_change=winnings
        )

        message = (
            f"{slot_display}\n"
            f"🎉 JACKPOT! You won **{winnings} coins**!"
        )

    elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:

        winnings = bet

        update_balance(
            interaction.user.id,
            wallet_change=winnings
        )

        message = (
            f"{slot_display}\n"
            f"🙂 Match 2! You won back **{winnings} coins**!"
        )

    else:

        update_balance(
            interaction.user.id,
            wallet_change=-bet
        )

        message = (
            f"{slot_display}\n"
            f"😢 You lost **{bet} coins**."
        )

    await interaction.response.send_message(message)


# ---------------- JOBS ----------------

@bot.tree.command(
    name="jobs",
    description="View jobs and choose your career."
)
@app_commands.describe(
    join_job="Career to join (optional)"
)
async def jobs(
    interaction: discord.Interaction,
    join_job: str = None
):

    profile = get_profile(interaction.user.id)

    current_job = profile.get("job", "beggar")

    if join_job:

        target_job = join_job.strip().lower()

        if target_job not in JOBS_LIST:
            return await interaction.response.send_message(
                "❌ Invalid job! Use /jobs to view available jobs.",
                ephemeral=True
            )

        set_user_job(
            interaction.user.id,
            target_job
        )

        return await interaction.response.send_message(
            f"💼 You are now working as **{target_job.capitalize()}**!"
        )

    embed = discord.Embed(
        title="💼 Job Market Dashboard",
        description=(
            f"Your Active Position: **{current_job.capitalize()}**\n\n"
            "To apply, use `/jobs join_job:beggar`."
        ),
        color=discord.Color.blue()
    )

    for job_name, data in JOBS_LIST.items():

        embed.add_field(
            name=f"🛠️ {job_name.capitalize()}",
            value=(
                f"Pay: {data['salary_min']} - "
                f"{data['salary_max']} coins\n"
                f"Cooldown: {data['cooldown']} seconds\n"
                f"*{data['description']}*"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# ---------------- WORK ----------------

@bot.tree.command(
    name="work",
    description="Work your current job to earn coins."
)
async def work(interaction: discord.Interaction):

    profile = get_profile(interaction.user.id)

    current_job = profile.get("job", "beggar")

    job_info = JOBS_LIST[current_job]

    last_work = profile.get("last_work", 0)

    current_time = int(time.time())

    elapsed = current_time - last_work

    if elapsed < job_info["cooldown"]:

        remaining = job_info["cooldown"] - elapsed

        return await interaction.response.send_message(
            f"⏳ Wait **{remaining} seconds** before working again.",
            ephemeral=True
        )

    earnings = random.randint(
        job_info["salary_min"],
        job_info["salary_max"]
    )

    update_balance(
        interaction.user.id,
        wallet_change=earnings
    )

    update_work_timestamp(interaction.user.id)

    await interaction.response.send_message(
        f"💰 You worked as **{current_job.capitalize()}** "
        f"and earned **{earnings} coins**!"
    )


# ---------------- SHOP ----------------

@bot.tree.command(
    name="shop",
    description="Displays all shop items."
)
async def shop(interaction: discord.Interaction):

    shop_items = load_json(SHOP_FILE)

    if not shop_items:
        return await interaction.response.send_message(
            "🛒 The shop is empty!",
            ephemeral=True
        )

    await interaction.response.defer()

    for item in shop_items:

        embed = discord.Embed(
            title=f"📦 {item['name']}",
            description=f"Price: **{item['price']} coins**",
            color=discord.Color.green()
        )

        if item.get("image_url"):
            embed.set_image(url=item["image_url"])

        await interaction.followup.send(embed=embed)


# ---------------- BUY ----------------

@bot.tree.command(
    name="buy",
    description="Purchase an item from the shop."
)
@app_commands.describe(
    item_name="Exact item name"
)
async def buy(
    interaction: discord.Interaction,
    item_name: str
):

    shop_items = load_json(SHOP_FILE)

    profile = get_profile(interaction.user.id)

    target_name = item_name.strip().lower()

    item = next(
        (
            i for i in shop_items
            if i["name"].lower() == target_name
        ),
        None
    )

    if not item:
        return await interaction.response.send_message(
            "❌ Item not found! Check /shop.",
            ephemeral=True
        )

    if profile["wallet"] < item["price"]:
        return await interaction.response.send_message(
            f"❌ You need {item['price']} coins to buy this item.",
            ephemeral=True
        )

    update_balance(
        interaction.user.id,
        wallet_change=-item["price"]
    )

    add_to_inventory(
        interaction.user.id,
        item["name"]
    )

    await interaction.response.send_message(
        f"🎉 Purchased **{item['name']}** "
        f"for **{item['price']} coins**!\n"
        "Use `/inventory` to view your items."
    )


# ---------------- INVENTORY ----------------

@bot.tree.command(
    name="inventory",
    description="View your inventory."
)
@app_commands.describe(
    member="Member whose inventory you want to inspect"
)
async def inventory(
    interaction: discord.Interaction,
    member: discord.Member = None
):

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
        f"• {name} x{qty}"
        for name, qty in counts.items()
    )

    embed = discord.Embed(
        title=f"🎒 {target.name}'s Inventory",
        description=inv_list,
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)


# ---------------- ADMIN COMMAND ----------------

@bot.tree.command(
    name="addmoney",
    description="Give coins to a member (Admin/Owner only)."
)
@app_commands.describe(
    member="Member receiving coins",
    amount="Number of coins"
)
async def addmoney(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):

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

    update_balance(
        member.id,
        wallet_change=amount
    )

    await interaction.response.send_message(
        f"✅ Added **{amount} coins** to {member.mention}'s wallet!"
    )


# ---------------- ERROR HANDLER ----------------

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(error, app_commands.CommandOnCooldown):

        message = (
            f"⏳ Slow down! Try again in "
            f"{error.retry_after:.2f} seconds."
        )

    else:

        print(f"Command error: {error}")

        message = "❌ Something went wrong while executing this command."

    if interaction.response.is_done():

        await interaction.followup.send(
            message,
            ephemeral=True
        )

    else:

        await interaction.response.send_message(
            message,
            ephemeral=True
        )


# ---------------- BACKGROUND RUNNER ----------------

def run_discord_bot():

    token = os.environ.get("DISCORD_TOKEN")

    if not token:
        print("❌ DISCORD_TOKEN environment variable not found.")
        return

    try:
        asyncio.run(bot.start(token))

    except Exception as e:
        print(f"Discord bot error: {e}")


# ---------------- MAIN ----------------

if __name__ == "__main__":

    bot_thread = threading.Thread(
        target=run_discord_bot,
        daemon=True
    )

    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True
    )
