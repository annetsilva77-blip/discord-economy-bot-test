import os
import random
import threading
import asyncio
import time
import requests
import discord

from discord import app_commands
from discord.ext import commands
from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from supabase import create_client, Client

OWNER_ID = 1327939431608483895

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().strip('"').strip("'")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_KEY in Render Environment Variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

CAR_CATALOG = {
    "starter kart": {
        "name": "Starter Kart",
        "rarity": "COMMON",
        "top_speed": 140,
        "accel": 8.5,
        "handling": 70,
        "braking": 65,
        "hp": 110,
        "drivetrain": "RWD",
        "weight": "420 KG",
        "flag": "🇯🇵",
        "color": 0x95A5A6,
        "pixel_color": "#95a5a6"
    },
    "honda civic type r": {
        "name": "Honda Civic Type R",
        "rarity": "UNCOMMON",
        "top_speed": 225,
        "accel": 5.4,
        "handling": 82,
        "braking": 78,
        "hp": 315,
        "drivetrain": "FWD",
        "weight": "1,430 KG",
        "flag": "🇯🇵",
        "color": 0x2ECC71,
        "pixel_color": "#2ecc71"
    },
    "bmw m4": {
        "name": "BMW M4",
        "rarity": "RARE",
        "top_speed": 252,
        "accel": 4.1,
        "handling": 88,
        "braking": 85,
        "hp": 625,
        "drivetrain": "RWD",
        "weight": "1,575 KG",
        "flag": "🇩🇪",
        "color": 0x3498DB,
        "pixel_color": "#3498db"
    },
    "nissan gt-r": {
        "name": "Nissan GT-R",
        "rarity": "EPIC",
        "top_speed": 315,
        "accel": 2.9,
        "handling": 92,
        "braking": 90,
        "hp": 600,
        "drivetrain": "AWD",
        "weight": "1,750 KG",
        "flag": "🇯🇵",
        "color": 0x9B59B6,
        "pixel_color": "#9b59b6"
    },
    "bugatti chiron": {
        "name": "Bugatti Chiron",
        "rarity": "LEGENDARY",
        "top_speed": 420,
        "accel": 2.4,
        "handling": 95,
        "braking": 96,
        "hp": 1500,
        "drivetrain": "AWD",
        "weight": "1,995 KG",
        "flag": "🇫🇷",
        "color": 0xF1C40F,
        "pixel_color": "#f1c40f"
    }
}

app = Flask(__name__)
RACE_ROOMS = {}
ROOMS_LOCK = threading.RLock()


def is_owner(user_id) -> bool:
    return int(user_id) == OWNER_ID


def can_manage_money(interaction: discord.Interaction) -> bool:
    if is_owner(interaction.user.id):
        return True
    if interaction.guild and isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False


def get_car_specs(item_name: str) -> dict:
    key = item_name.strip().lower()
    if key in CAR_CATALOG:
        return dict(CAR_CATALOG[key])
    for cat_key, specs in CAR_CATALOG.items():
        if cat_key in key or key in cat_key:
            custom = dict(specs)
            custom["name"] = item_name
            return custom
    return {
        "name": item_name,
        "rarity": "CUSTOM",
        "top_speed": 210,
        "accel": 5.8,
        "handling": 75,
        "braking": 74,
        "hp": 280,
        "drivetrain": "RWD",
        "weight": "1,450 KG",
        "flag": "🏁",
        "color": 0xE67E22,
        "pixel_color": "#e67e22"
    }


def make_stat_bar(value: int, max_val: int = 100) -> str:
    filled = max(1, min(10, round((value / max_val) * 10)))
    return "🟪" * filled + "⬛" * (10 - filled)


def build_car_card_embed(car_name: str, image_url: str = "") -> discord.Embed:
    specs = get_car_specs(car_name)
    speed_score = min(100, int((specs["top_speed"] / 420) * 100))
    accel_score = min(100, max(10, int(((10.0 - specs["accel"]) / 8.0) * 100)))

    embed = discord.Embed(
        title=f"🏎️ {specs['name'].upper()}",
        description=f"**RARITY:** `{specs['rarity']}`  {specs['flag']}",
        color=specs["color"]
    )
    bars = (
        f"⏱️ **TOP SPEED**\n{make_stat_bar(speed_score)}\n"
        f"🚀 **ACCELERATION**\n{make_stat_bar(accel_score)}\n"
        f"🛞 **HANDLING**\n{make_stat_bar(specs['handling'])}\n"
        f"🛑 **BRAKING**\n{make_stat_bar(specs['braking'])}"
    )
    stats = (
        f"🏁 **TOP SPEED:** `{specs['top_speed']} KM/H`\n"
        f"⚡ **0-100 KM/H:** `{specs['accel']} s`\n"
        f"🐎 **HORSEPOWER:** `{specs['hp']} HP`\n"
        f"⚙️ **DRIVETRAIN:** `{specs['drivetrain']}`\n"
        f"⚖️ **WEIGHT:** `{specs['weight']}`"
    )
    embed.add_field(name="PERFORMANCE", value=bars, inline=True)
    embed.add_field(name="SPECIFICATIONS", value=stats, inline=True)
    if image_url:
        embed.set_thumbnail(url=image_url)
    return embed


# --- SUPABASE HELPER FUNCTIONS ---

def get_profile(user_id):
    uid = str(user_id)
    res = supabase.table("users").select("*").eq("user_id", uid).execute()

    if not res.data:
        new_profile = {
            "user_id": uid,
            "wallet": 0,
            "bank": 0,
            "inventory": [],
            "job": "beggar",
            "last_work": 0
        }
        supabase.table("users").insert(new_profile).execute()
        return new_profile

    profile = res.data[0]
    if profile.get("job") not in JOBS_LIST:
        profile["job"] = "beggar"
    if profile.get("inventory") is None:
        profile["inventory"] = []
    return profile


def update_balance(user_id, wallet_change=0, bank_change=0):
    if is_owner(user_id):
        get_profile(user_id)
        return

    profile = get_profile(user_id)
    new_wallet = max(0, profile["wallet"] + wallet_change)
    new_bank = max(0, profile["bank"] + bank_change)

    supabase.table("users").update({
        "wallet": new_wallet,
        "bank": new_bank
    }).eq("user_id", str(user_id)).execute()


def add_to_inventory(user_id, item_name):
    profile = get_profile(user_id)
    inv = list(profile.get("inventory") or [])
    inv.append(item_name)

    supabase.table("users").update({
        "inventory": inv
    }).eq("user_id", str(user_id)).execute()


def set_user_job(user_id, job_name):
    get_profile(user_id)
    supabase.table("users").update({
        "job": job_name
    }).eq("user_id", str(user_id)).execute()


def update_work_timestamp(user_id):
    get_profile(user_id)
    supabase.table("users").update({
        "last_work": int(time.time())
    }).eq("user_id", str(user_id)).execute()


def get_shop_items():
    res = supabase.table("shop").select("*").execute()
    return res.data or []


def get_user_cars(user_id):
    if is_owner(user_id):
        cars = [dict(v) for v in CAR_CATALOG.values()]
        for item in get_shop_items():
            if not any(c["name"].lower() == item["name"].lower() for c in cars):
                cars.append(get_car_specs(item["name"]))
        return cars

    profile = get_profile(user_id)
    inv = profile.get("inventory") or []
    seen = set()
    owned_cars = []
    for item_name in inv:
        low = item_name.lower()
        if low not in seen:
            seen.add(low)
            owned_cars.append(get_car_specs(item_name))

    if not owned_cars:
        owned_cars.append(dict(CAR_CATALOG["starter kart"]))
    return owned_cars


# --- FLASK ADMIN & ACTIVITY ROUTES ---

@app.route("/", methods=["GET", "POST"])
def index():
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
                file_bytes = image_file.read()
                try:
                    supabase.storage.from_("shop-images").upload(
                        filename,
                        file_bytes,
                        {"content-type": image_file.mimetype}
                    )
                    image_url = supabase.storage.from_("shop-images").get_public_url(filename)
                except Exception as e:
                    print(f"Image upload warning: {e}")

        supabase.table("shop").upsert({
            "name": name,
            "price": item_price,
            "image_url": image_url
        }).execute()

        return redirect(url_for("index"))

    shop_items = get_shop_items()
    return render_template("admin.html", shop_items=shop_items)


@app.route("/activity")
def activity():
    return render_template("activity.html", client_id=DISCORD_CLIENT_ID)


@app.route("/api/token", methods=["POST"])
def api_token():
    data = request.get_json(silent=True) or {}
    code = data.get("code", "")
    if not code or not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET:
        return jsonify({"error": "Missing OAuth credentials"}), 400

    res = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    return jsonify(res.json()), res.status_code


@app.route("/api/player/<user_id>")
def api_player(user_id):
    cars = get_user_cars(user_id)
    profile = get_profile(user_id)
    return jsonify({
        "user_id": str(user_id),
        "is_owner": is_owner(user_id),
        "wallet": 999999999 if is_owner(user_id) else profile["wallet"],
        "cars": cars
    })


@app.route("/api/room/<room_id>/sync", methods=["POST"])
def api_room_sync(room_id):
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    username = data.get("username", "Racer")
    car = data.get("car") or get_car_specs("Starter Kart")
    progress = float(data.get("progress", 0.0))
    speed = int(data.get("speed", 0))
    finished = bool(data.get("finished", False))
    action = data.get("action", "")
    bet = int(data.get("bet", 0))

    now = time.time()
    with ROOMS_LOCK:
        room = RACE_ROOMS.setdefault(room_id, {
            "players": {},
            "status": "racing",
            "winner_id": None,
            "winner_name": None,
            "bet": bet,
            "paid": False,
            "updated_at": now
        })

        if action == "reset":
            room["status"] = "racing"
            room["winner_id"] = None
            room["winner_name"] = None
            room["paid"] = False
            for p in room["players"].values():
                p["progress"] = 0.0
                p["speed"] = 0
                p["finished"] = False

        if uid:
            room["players"][uid] = {
                "user_id": uid,
                "username": username,
                "car": car,
                "progress": min(100.0, max(0.0, progress)),
                "speed": speed,
                "finished": finished,
                "last_seen": now
            }

            if finished and room["winner_id"] is None:
                room["winner_id"] = uid
                room["winner_name"] = username
                room["status"] = "finished"

                if room["bet"] > 0 and not room["paid"]:
                    room["paid"] = True
                    pot = room["bet"] * max(1, len(room["players"]) - 1)
                    if pot > 0:
                        update_balance(uid, wallet_change=pot)
                    for pid in room["players"]:
                        if pid != uid:
                            update_balance(pid, wallet_change=-room["bet"])

        # Remove inactive players after 15 seconds
        stale = [k for k, v in room["players"].items() if now - v["last_seen"] > 15]
        for k in stale:
            del room["players"][k]

        room["updated_at"] = now
        return jsonify({
            "room_id": room_id,
            "status": room["status"],
            "winner_id": room["winner_id"],
            "winner_name": room["winner_name"],
            "bet": room["bet"],
            "players": list(room["players"].values())
        })


# --- DISCORD BOT SETUP ---

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


@bot.tree.command(name="addmoney", description="Admin/Owner only: Add coins to a user's wallet.")
@app_commands.describe(member="The member to give coins to", amount="Amount of coins to add")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not can_manage_money(interaction):
        return await interaction.response.send_message(
            "❌ Only server administrators or the bot owner can use this command.",
            ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if is_owner(member.id):
        return await interaction.response.send_message(
            "👑 The bot owner already has **∞ unlimited coins**!",
            ephemeral=True
        )

    update_balance(member.id, wallet_change=amount)
    await interaction.response.send_message(
        f"💸 Added **{amount} coins** to **{member.display_name}**'s wallet!"
    )


@bot.tree.command(name="bal", description="Checks your wallet and bank balances.")
@app_commands.describe(member="The member whose balance you want to check")
async def bal(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user

    if is_owner(target.id):
        embed = discord.Embed(
            title=f"👑 {target.name}'s Financial Portfolio (OWNER)",
            color=discord.Color.gold()
        )
        embed.add_field(name="👛 Wallet", value="∞ Unlimited coins")
        embed.add_field(name="🏛️ Bank", value="∞ Unlimited coins")
        embed.add_field(name="📊 Net Worth", value="∞ Unlimited coins", inline=False)
        return await interaction.response.send_message(embed=embed)

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
    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            "👑 As the bot owner, you already have **∞ unlimited coins** in both your wallet and bank!"
        )

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
    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            "👑 As the bot owner, you already have **∞ unlimited coins** in your wallet!"
        )

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
        f"📤 Withdrew **{target_amount} coins** from your bank!"
    )


@bot.tree.command(name="work", description="Work your current job to earn coins.")
async def work(interaction: discord.Interaction):
    profile = get_profile(interaction.user.id)
    job_key = profile["job"]
    job_info = JOBS_LIST[job_key]

    now = int(time.time())
    elapsed = now - profile["last_work"]

    if elapsed < job_info["cooldown"] and not is_owner(interaction.user.id):
        remaining = job_info["cooldown"] - elapsed
        return await interaction.response.send_message(
            f"⏳ You are tired! Wait **{remaining} seconds** before working again.",
            ephemeral=True
        )

    earnings = random.randint(job_info["salary_min"], job_info["salary_max"])
    update_balance(interaction.user.id, wallet_change=earnings)
    update_work_timestamp(interaction.user.id)

    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            f"💼 You worked as a **{job_key.title()}**! (Balance remains **∞ Unlimited**)"
        )

    await interaction.response.send_message(
        f"💼 You worked as a **{job_key.title()}** and earned **{earnings} coins**!"
    )


@bot.tree.command(name="jobs", description="Lists all available jobs.")
async def jobs(interaction: discord.Interaction):
    embed = discord.Embed(title="💼 Available Jobs", color=discord.Color.blue())
    for name, info in JOBS_LIST.items():
        desc_text = info["description"] + " (Cooldown: " + str(info["cooldown"]) + "s)"
        embed.add_field(
            name=f"{name.title()} ({info['salary_min']}–{info['salary_max']} coins)",
            value=desc_text,
            inline=False
        )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="apply", description="Apply for a new job.")
@app_commands.describe(job="Name of the job (beggar, gamer, developer)")
async def apply(interaction: discord.Interaction, job: str):
    job_key = job.lower().strip()
    if job_key not in JOBS_LIST:
        return await interaction.response.send_message(
            "❌ Invalid job. Choose from: `beggar`, `gamer`, `developer`.",
            ephemeral=True
        )

    set_user_job(interaction.user.id, job_key)
    await interaction.response.send_message(
        f"✅ You are now employed as a **{job_key.title()}**!"
    )


@bot.tree.command(name="shop", description="View items and cars available in the shop.")
async def shop(interaction: discord.Interaction):
    items = get_shop_items()
    if not items:
        return await interaction.response.send_message("🛒 The shop is currently empty!")

    embed = discord.Embed(title="🛒 Car & Item Shop", color=discord.Color.green())
    for item in items:
        specs = get_car_specs(item["name"])
        embed.add_field(
            name=f"{item['name']} ({specs['rarity']}) — {item['price']} coins",
            value=f"Top Speed: `{specs['top_speed']} KM/H` | 0-100: `{specs['accel']}s` | `{specs['hp']} HP`",
            inline=False
        )
    if items[0].get("image_url"):
        embed.set_thumbnail(url=items[0]["image_url"])

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="buy", description="Buy a car or item from the shop.")
@app_commands.describe(item_name="The exact name of the item you want to buy")
async def buy(interaction: discord.Interaction, item_name: str):
    items = get_shop_items()
    selected = next(
        (i for i in items if i["name"].lower() == item_name.strip().lower()),
        None
    )

    if not selected:
        return await interaction.response.send_message(
            "❌ That item does not exist in the shop.",
            ephemeral=True
        )

    if not is_owner(interaction.user.id):
        profile = get_profile(interaction.user.id)
        if profile["wallet"] < selected["price"]:
            return await interaction.response.send_message(
                "❌ You don't have enough coins in your wallet to buy this item.",
                ephemeral=True
            )

    update_balance(interaction.user.id, wallet_change=-selected["price"])
    add_to_inventory(interaction.user.id, selected["name"])
    card_embed = build_car_card_embed(selected["name"], selected.get("image_url", ""))

    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            content=f"👑 You claimed **{selected['name']}** with your **∞ Unlimited Owner Balance**!",
            embed=card_embed
        )

    await interaction.response.send_message(
        content=f"🎉 You bought **{selected['name']}** for **{selected['price']} coins**!",
        embed=card_embed
    )


@bot.tree.command(name="garage", description="View your car spec cards from your inventory.")
@app_commands.describe(car_name="Optional car name to inspect its full stat card")
async def garage(interaction: discord.Interaction, car_name: str = None):
    cars = get_user_cars(interaction.user.id)
    shop_map = {i["name"].lower(): i.get("image_url", "") for i in get_shop_items()}

    if car_name:
        chosen = next((c for c in cars if car_name.lower() in c["name"].lower()), cars[0])
    else:
        chosen = max(cars, key=lambda c: c["top_speed"])

    img = shop_map.get(chosen["name"].lower(), "")
    embed = build_car_card_embed(chosen["name"], img)
    all_names = ", ".join(f"`{c['name']}`" for c in cars)
    embed.set_footer(text=f"Owned Vehicles: {len(cars)} • Use /garage car_name:<name> to inspect others")

    await interaction.response.send_message(
        content=f"🚘 **Your Garage:** {all_names}",
        embed=embed
    )


@bot.tree.command(name="inventory", description="View your purchased items.")
@app_commands.describe(member="The member whose inventory you want to check")
async def inventory(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    profile = get_profile(target.id)
    inv = profile.get("inventory") or []

    if not inv:
        return await interaction.response.send_message(
            f"🎒 **{target.name}** has no items in their inventory."
        )

    counts = {}
    for item in inv:
        counts[item] = counts.get(item, 0) + 1

    lines = [f"• **{name}** x{qty}" for name, qty in counts.items()]
    embed = discord.Embed(
        title=f"🎒 {target.name}'s Inventory",
        description="\n".join(lines),
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="race", description="Play live 2D pixel car racing in Voice Channel (Phone & PC)!")
@app_commands.describe(bet="Optional coins to wager per racer (default 0)")
async def race(interaction: discord.Interaction, bet: int = 0):
    if bet < 0:
        return await interaction.response.send_message(
            "❌ Bet cannot be negative.",
            ephemeral=True
        )

    if bet > 0 and not is_owner(interaction.user.id):
        profile = get_profile(interaction.user.id)
        if profile["wallet"] < bet:
            return await interaction.response.send_message(
                f"❌ You need **{bet} coins** in your wallet to host a wager race!",
                ephemeral=True
            )

    vc_id = str(interaction.user.voice.channel.id) if (interaction.user.voice and interaction.user.voice.channel) else str(interaction.channel_id)
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://discord-economy-bot-test.onrender.com").rstrip("/")
    game_url = f"{render_url}/activity?room={vc_id}&uid={interaction.user.id}&name={interaction.user.display_name}&bet={bet}"

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="📱 Play on Phone / Browser",
        style=discord.ButtonStyle.link,
        url=game_url
    ))

    try:
        await interaction.response.launch_activity()
        await interaction.followup.send(
            content=f"🏁 **VC Multiplayer Race Launched!** (Wager: `{bet} coins`)\nAnyone on **Phone, Tablet, or PC** can also join via the link below:",
            view=view
        )
    except Exception:
        embed = discord.Embed(
            title="🕹️ PIXEL-GP 2D // VOICE CHANNEL MULTIPLAYER RACE",
            description=(
                f"**Host:** {interaction.user.mention}\n"
                f"**Wager:** `{bet} coins`\n\n"
                "Tap **Play on Phone / Browser** below (or launch the Activity in your Voice Channel) to pick your car from your Supabase inventory and race live on **iPhone, Android, iPad, or PC**!"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=view)


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN in Render Environment Variables.")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.run(DISCORD_TOKEN)
