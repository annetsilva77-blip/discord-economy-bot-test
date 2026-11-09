
import os
import random
import threading
import asyncio
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from pymongo.errors import PyMongoError


OWNER_ID = 1327939431608483895

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
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# MONGODB CONNECTION

mongo_uri = os.environ.get("MONGODB_URI")

if not mongo_uri:
    raise RuntimeError("MONGODB_URI environment variable is missing.")

client = MongoClient(
    mongo_uri,
    serverSelectionTimeoutMS=5000
)

client.admin.command("ping")

db = client["economy_bot_database"]

shop_collection = db["shop_items"]
economy_collection = db["player_profiles"]

economy_collection.create_index("user_id", unique=True)

print("MongoDB Atlas connected successfully!")


# DATABASE FUNCTIONS

def get_shop_items():
    try:
        return list(shop_collection.find({}, {"_id": 0}))
    except PyMongoError as e:
        print("Error fetching shop:", e)
        return []


def save_shop_item(item):
    try:
        shop_collection.insert_one(item)
        return True
    except PyMongoError as e:
        print("Error saving shop item:", e)
        return False


def get_profile(user_id):
    uid = str(user_id)

    default_profile = {
        "user_id": uid,
        "wallet": 0,
        "bank": 0,
        "inventory": [],
        "job": "beggar",
        "last_work": 0
    }

    try:
        economy_collection.update_one(
            {"user_id": uid},
            {"$setOnInsert": default_profile},
            upsert=True
        )

        profile = economy_collection.find_one({"user_id": uid})

        if not profile:
            return default_profile

        updates = {}

        for key in ["wallet", "bank", "inventory", "job", "last_work"]:
            if key not in profile:
                updates[key] = default_profile[key]

        if updates:
            economy_collection.update_one(
                {"user_id": uid},
                {"$set": updates}
            )
            profile.update(updates)

        return profile

    except PyMongoError as e:
        print("Error getting profile:", e)
        return default_profile


def update_balance(user_id, wallet_change=0, bank_change=0):
    uid = str(user_id)

    try:
        get_profile(user_id)

        economy_collection.update_one(
            {"user_id": uid},
            {
                "$inc": {
                    "wallet": wallet_change,
                    "bank": bank_change
                }
            }
        )

        return True

    except PyMongoError as e:
        print("Error updating balance:", e)
        return False


def transfer_balance(user_id, amount, from_account, to_account):
    uid = str(user_id)

    try:
        get_profile(user_id)

        result = economy_collection.update_one(
            {
                "user_id": uid,
                from_account: {"$gte": amount}
            },
            {
                "$inc": {
                    from_account: -amount,
                    to_account: amount
                }
            }
        )

        return result.modified_count > 0

    except PyMongoError as e:
        print("Error transferring balance:", e)
        return False


def set_user_job(user_id, job_name):
    try:
        get_profile(user_id)

        economy_collection.update_one(
            {"user_id": str(user_id)},
            {"$set": {"job": job_name}}
        )

        return True

    except PyMongoError as e:
        print("Error setting job:", e)
        return False


# FLASK DASHBOARD

@app.route("/", methods=["GET", "POST"])
def index():
    shop_items = get_shop_items()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "").strip()

        image_file = request.files.get("image")
        image_url = ""

        try:
            price = int(price)

            if not name or price <= 0:
                return redirect(url_for("index"))

            if image_file and image_file.filename:
                original_name = secure_filename(image_file.filename)
                extension = original_name.rsplit(".", 1)[-1].lower()

                if extension in ALLOWED_EXTENSIONS:
                    filename = f"{uuid.uuid4().hex}.{extension}"

                    image_file.save(
                        os.path.join(
                            app.config["UPLOAD_FOLDER"],
                            filename
                        )
                    )

                    image_url = url_for(
                        "custom_static",
                        filename=filename,
                        _external=True
                    )

            new_item = {
                "name": name,
                "price": price,
                "image_url": image_url
            }

            save_shop_item(new_item)

        except ValueError:
            pass

        return redirect(url_for("index"))

    return render_template(
        "admin.html",
        shop_items=shop_items
    )


@app.route("/static/uploads/<filename>")
def custom_static(filename):
    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# DISCORD BOT

class EconomyBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        await self.tree.sync()
        print("Discord commands synchronized.")


bot = EconomyBot()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# BALANCE

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

    wallet = profile.get("wallet", 0)
    bank = profile.get("bank", 0)

    embed = discord.Embed(
        title=f"🏦 {target.name}'s Financial Portfolio",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="👛 Wallet",
        value=f"{wallet} coins",
        inline=True
    )

    embed.add_field(
        name="🏛️ Bank",
        value=f"{bank} coins",
        inline=True
    )

    embed.add_field(
        name="📊 Net Worth",
        value=f"{wallet + bank} coins",
        inline=False
    )

    await interaction.response.send_message(embed=embed)


# DEPOSIT

@bot.tree.command(
    name="deposit",
    description="Deposits wallet coins into your bank."
)
@app_commands.describe(
    amount="Amount to deposit, or all"
)
async def deposit(
    interaction: discord.Interaction,
    amount: str
):
    profile = get_profile(interaction.user.id)
    wallet = profile.get("wallet", 0)

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

    if not transfer_balance(
        interaction.user.id,
        target_amount,
        "wallet",
        "bank"
    ):
        return await interaction.response.send_message(
            "❌ You do not have enough coins in your wallet.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"📥 Deposited **{target_amount} coins** into your bank!"
    )


# WITHDRAW

@bot.tree.command(
    name="withdraw",
    description="Withdraws bank coins into your wallet."
)
@app_commands.describe(
    amount="Amount to withdraw, or all"
)
async def withdraw(
    interaction: discord.Interaction,
    amount: str
):
    profile = get_profile(interaction.user.id)
    bank = profile.get("bank", 0)

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

    if not transfer_balance(
        interaction.user.id,
        target_amount,
        "bank",
        "wallet"
    ):
        return await interaction.response.send_message(
            "❌ You do not have enough coins in your bank.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"📤 Withdrew **{target_amount} coins** into your wallet!"
    )


# SLOTS

@bot.tree.command(
    name="slots",
    description="Play the virtual coin slot machine."
)
@app_commands.describe(
    bet="Number of coins to bet"
)
@app_commands.checks.cooldown(1, 10.0)
async def slots(
    interaction: discord.Interaction,
    bet: int
):
    get_profile(interaction.user.id)

    if bet <= 0:
        return await interaction.response.send_message(
            "❌ Bet must be greater than zero.",
            ephemeral=True
        )

    if not transfer_balance(
        interaction.user.id,
        bet,
        "wallet",
        "wallet"
    ):
        return await interaction.response.send_message(
            "❌ You do not have enough coins.",
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

        await interaction.response.send_message(
            f"{slot_display}\n🎉 **JACKPOT!** You won **{winnings} coins**!"
        )

    elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
        winnings = bet

        update_balance(
            interaction.user.id,
            wallet_change=winnings
        )

        await interaction.response.send_message(
            f"{slot_display}\n🙂 **Match 2!** You got your **{winnings} coins** back!"
        )

    else:
        await interaction.response.send_message(
            f"{slot_display}\n😢 **You lost!** You lost **{bet} coins**."
        )


# JOBS

@bot.tree.command(
    name="jobs",
    description="View available jobs or choose a job."
)
@app_commands.describe(
    join_job="Name of the job you want"
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

        set_user_job(interaction.user.id, target_job)

        return await interaction.response.send_message(
            f"💼 You are now working as **{target_job.capitalize()}**!"
        )

    embed = discord.Embed(
        title="💼 Job Market Dashboard",
        description=f"Your Active Position: **{current_job.capitalize()}**\n\nUse `/jobs join_job:[Name]` to select a job.",
        color=discord.Color.blue()
    )

    for job_name, data in JOBS_LIST.items():
        embed.add_field(
            name=f"🛠️ {job_name.capitalize()}",
            value=(
                f"Pay: {data['salary_min']} - {data['salary_max']} coins\n"
                f"Cooldown: {data['cooldown']} seconds\n"
                f"*{data['description']}*"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


# WORK

@bot.tree.command(
    name="work",
    description="Work at your selected job to earn coins."
)
async def work(interaction: discord.Interaction):
    profile = get_profile(interaction.user.id)

    current_job = profile.get("job", "beggar")
    last_work = profile.get("last_work", 0)

    if current_job not in JOBS_LIST:
        current_job = "beggar"

    job_info = JOBS_LIST[current_job]

    current_time = int(time.time())
    elapsed = current_time - last_work

    if elapsed < job_info["cooldown"]:
        remaining = job_info["cooldown"] - elapsed

        return await interaction.response.send_message(
            f"⏳ Come back in **{remaining} seconds**.",
            ephemeral=True
        )

    earnings = random.randint(
        job_info["salary_min"],
        job_info["salary_max"]
    )

    try:
        result = economy_collection.update_one(
            {
                "user_id": str(interaction.user.id),
                "last_work": last_work
            },
            {
                "$set": {"last_work": current_time},
                "$inc": {"wallet": earnings}
            }
        )

        if result.modified_count == 0:
            return await interaction.response.send_message(
                "⏳ Your work cooldown is already being processed. Try again.",
                ephemeral=True
            )

    except PyMongoError as e:
        print("Work error:", e)

        return await interaction.response.send_message(
            "❌ Database error. Please try again.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"💰 You worked as a **{current_job.capitalize()}** and earned **{earnings} coins**!"
    )


# SHOP

@bot.tree.command(
    name="shop",
    description="Displays all available shop items."
)
async def shop(interaction: discord.Interaction):
    shop_items = get_shop_items()

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

    embed.description = shop_list_text

    if last_image_url:
        embed.set_thumbnail(url=last_image_url)

    await interaction.response.send_message(embed=embed)


# BUY

@bot.tree.command(
    name="buy",
    description="Purchase an item from the shop."
)
@app_commands.describe(
    item_name="Exact name of the item"
)
async def buy(
    interaction: discord.Interaction,
    item_name: str
):
    shop_items = get_shop_items()

    item = next(
        (
            i for i in shop_items
            if i["name"].lower() == item_name.strip().lower()
        ),
        None
    )

    if not item:
        return await interaction.response.send_message(
            "❌ Item not found! Check the /shop command.",
            ephemeral=True
        )

    price = item["price"]

    try:
        get_profile(interaction.user.id)

        result = economy_collection.update_one(
            {
                "user_id": str(interaction.user.id),
                "wallet": {"$gte": price}
            },
            {
                "$inc": {"wallet": -price},
                "$push": {"inventory": item["name"]}
            }
        )

        if result.modified_count == 0:
            return await interaction.response.send_message(
                f"❌ You need **{price} coins** in your wallet.",
                ephemeral=True
            )

    except PyMongoError as e:
        print("Purchase error:", e)

        return await interaction.response.send_message(
            "❌ Database error. Please try again.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"🎉 You bought **{item['name']}** for **{price} coins**!\n"
        "Check your items using `/inventory`."
    )


# INVENTORY

@bot.tree.command(
    name="inventory",
    description="View your inventory."
)
@app_commands.describe(
    member="Member whose inventory you want to view"
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
        [
            f"🎒 **{name}** `x{qty}`"
            for name, qty in counts.items()
        ]
    )

    embed = discord.Embed(
        title=f"🎒 {target.name}'s Storage Inventory",
        description=inv_list,
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)


# ADMIN ADD MONEY

@bot.tree.command(
    name="addmoney",
    description="Give coins to a member. Admins and owner only."
)
@app_commands.describe(
    member="Member receiving coins",
    amount="Amount of coins to give"
)
async def addmoney(
    interaction: discord.Interaction,
    member: discord.Member,
    amount: int
):
    is_owner = interaction.user.id == OWNER_ID
    is_admin = (
        interaction.guild is not None
        and interaction.permissions.administrator
    )

    if not (is_owner or is_admin):
        return await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if not update_balance(member.id, wallet_change=amount):
        return await interaction.response.send_message(
            "❌ Database error. Coins were not added.",
            ephemeral=True
        )

    await interaction.response.send_message(
        f"✅ Added **{amount} coins** to {member.mention}'s wallet!"
    )


# COMMAND ERROR HANDLER

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

    else:
        print("Discord command error:", error)

        message = "❌ Something went wrong while running that command."

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


# BACKGROUND BOT RUNNER

def run_discord_bot():
    token = os.environ.get("DISCORD_TOKEN")

    if not token:
        print("DISCORD_TOKEN environment variable is missing.")
        return

    asyncio.run(bot.start(token))


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
        use_reloader=False
    )
