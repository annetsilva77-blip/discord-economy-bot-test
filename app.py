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
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

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
        "color": "#95a5a6",
        "top_speed": 145,
        "accel": 8.9,
        "handling": 65,
        "braking": 60,
        "hp": 110,
        "drivetrain": "RWD",
        "weight": 680,
        "flag": "🇯🇵",
        "emoji": "🛺"
    },
    "honda civic type r": {
        "name": "Honda Civic Type R",
        "rarity": "UNCOMMON",
        "color": "#2ecc71",
        "top_speed": 225,
        "accel": 5.4,
        "handling": 78,
        "braking": 76,
        "hp": 315,
        "drivetrain": "FWD",
        "weight": 1430,
        "flag": "🇯🇵",
        "emoji": "🚗"
    },
    "bmw m4": {
        "name": "BMW M4",
        "rarity": "RARE",
        "color": "#3498db",
        "top_speed": 252,
        "accel": 4.1,
        "handling": 84,
        "braking": 82,
        "hp": 625,
        "drivetrain": "RWD",
        "weight": 1575,
        "flag": "🇩🇪",
        "emoji": "🚙"
    },
    "nissan gt-r": {
        "name": "Nissan GT-R",
        "rarity": "EPIC",
        "color": "#9b59b6",
        "top_speed": 315,
        "accel": 2.9,
        "handling": 90,
        "braking": 88,
        "hp": 710,
        "drivetrain": "AWD",
        "weight": 1752,
        "flag": "🇯🇵",
        "emoji": "🏎️"
    },
    "bugatti chiron": {
        "name": "Bugatti Chiron",
        "rarity": "LEGENDARY",
        "color": "#f1c40f",
        "top_speed": 420,
        "accel": 2.4,
        "handling": 95,
        "braking": 96,
        "hp": 1500,
        "drivetrain": "AWD",
        "weight": 1995,
        "flag": "🇫🇷",
        "emoji": "🚀"
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


def get_car_specs(item_name: str):
    key = item_name.strip().lower()
    if key in CAR_CATALOG:
        return CAR_CATALOG[key]
    for k, v in CAR_CATALOG.items():
        if k in key or key in k:
            return v
    return None


def get_user_cars(user_id):
    if is_owner(user_id):
        return list(CAR_CATALOG.values())

    profile = get_profile(user_id)
    inv = profile.get("inventory") or []
    owned = []
    seen = set()
    for item in inv:
        specs = get_car_specs(item)
        if specs and specs["name"] not in seen:
            owned.append(specs)
            seen.add(specs["name"])
    if not owned:
        owned.append(CAR_CATALOG["starter kart"])
    return owned


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


def build_car_card_embed(car: dict, image_url: str = ""):
    def bar(val, max_val):
        filled = max(1, min(10, round((val / max_val) * 10)))
        return "🟪" * filled + "⬛" * (10 - filled)

    accel_score = max(10, min(100, int((10.5 - car["accel"]) * 12)))
    embed = discord.Embed(
        title=f"{car['flag']} {car['name'].upper()}  •  [{car['rarity']}]",
        color=int(car["color"].replace("#", ""), 16)
    )
    stats_text = (
        f"⏱️ **TOP SPEED:** `{car['top_speed']} KM/H`\n{bar(car['top_speed'], 430)}\n"
        f"🚀 **ACCELERATION:** `{car['accel']}s (0-100)`\n{bar(accel_score, 100)}\n"
        f"🛞 **HANDLING:** `{car['handling']}/100`\n{bar(car['handling'], 100)}\n"
        f"🛑 **BRAKING:** `{car['braking']}/100`\n{bar(car['braking'], 100)}\n\n"
        f"🐎 **HORSEPOWER:** `{car['hp']} HP`  |  ⚙️ **DRIVETRAIN:** `{car['drivetrain']}`  |  ⚖️ **WEIGHT:** `{car['weight']} KG`"
    )
    embed.description = stats_text
    if image_url:
        embed.set_thumbnail(url=image_url)
    return embed


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
    room_id = request.args.get("room", "global")
    bet = request.args.get("bet", "0")
    return render_template(
        "activity.html",
        client_id=DISCORD_CLIENT_ID,
        room_id=room_id,
        bet=bet
    )


@app.route("/api/token", methods=["POST"])
def api_token():
    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "Missing OAuth code"}), 400

    resp = requests.post(
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
    return jsonify(resp.json()), resp.status_code


@app.route("/api/player/<user_id>")
def api_player(user_id):
    cars = get_user_cars(user_id)
    if is_owner(user_id):
        wallet = 999999999
    else:
        wallet = get_profile(user_id)["wallet"]
    return jsonify({
        "user_id": str(user_id),
        "wallet": wallet,
        "is_owner": is_owner(user_id),
        "cars": cars
    })


@app.route("/api/room/<room_id>/sync", methods=["POST"])
def api_room_sync(room_id):
    payload = request.get_json(silent=True) or {}
    uid = str(payload.get("user_id", ""))
    username = str(payload.get("username", "Racer"))[:20]
    car_name = str(payload.get("car_name", "Starter Kart"))
    progress = float(payload.get("progress", 0.0))
    speed = int(payload.get("speed", 0))
    bet = int(payload.get("bet", 0))
    action = payload.get("action", "update")
    now = time.time()

    with ROOMS_LOCK:
        room = RACE_ROOMS.setdefault(room_id, {
            "status": "lobby",
            "bet": bet,
            "start_time": 0,
            "winner": None,
            "paid": False,
            "players": {}
        })

        room["players"] = {
            k: v for k, v in room["players"].items()
            if now - v.get("last_seen", 0) < 25
        }

        if not room["players"]:
            room["status"] = "lobby"
            room["winner"] = None
            room["paid"] = False
            room["bet"] = bet

        if uid:
            specs = get_car_specs(car_name) or CAR_CATALOG["starter kart"]
            p = room["players"].setdefault(uid, {
                "user_id": uid,
                "username": username,
                "car": specs,
                "progress": 0.0,
                "speed": 0,
                "ready": False,
                "last_seen": now
            })
            p["username"] = username
            p["car"] = specs
            p["last_seen"] = now

            if action == "ready":
                p["ready"] = not p["ready"]
            elif action == "start" and len(room["players"]) >= 1:
                room["status"] = "racing"
                room["start_time"] = now + 3.0
                room["winner"] = None
                room["paid"] = False
                for pl in room["players"].values():
                    pl["progress"] = 0.0
                    pl["speed"] = 0
            elif action == "reset":
                room["status"] = "lobby"
                room["winner"] = None
                room["paid"] = False
                for pl in room["players"].values():
                    pl["progress"] = 0.0
                    pl["speed"] = 0
                    pl["ready"] = False

            if room["status"] == "racing":
                p["progress"] = max(p["progress"], progress)
                p["speed"] = speed
                if p["progress"] >= 100.0 and not room["winner"]:
                    room["winner"] = uid
                    room["status"] = "finished"

                    if not room["paid"] and room["bet"] > 0 and len(room["players"]) >= 2:
                        room["paid"] = True
                        wager = room["bet"]
                        losers = [k for k in room["players"] if k != uid]
                        pot = wager * len(losers)
                        update_balance(uid, wallet_change=pot)
                        for lid in losers:
                            update_balance(lid, wallet_change=-wager)

        return jsonify({
            "room_id": room_id,
            "status": room["status"],
            "bet": room["bet"],
            "countdown": max(0.0, round(room["start_time"] - now, 2)) if room["status"] == "racing" else 0.0,
            "winner": room["winner"],
            "players": list(room["players"].values())
        })


class EconomyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        existing_commands = await self.http.get_global_commands(self.application_id)
        entry_points = [cmd for cmd in existing_commands if cmd.get("type") == 4]

        if entry_points:
            payload = [cmd.to_dict(self.tree) for cmd in self.tree.get_commands()]
            payload.extend(entry_points)
            await self.http.bulk_upsert_global_commands(self.application_id, payload=payload)
        else:
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

    embed = discord.Embed(title="🛒 Item & Car Dealership", color=discord.Color.green())
    for item in items:
        specs = get_car_specs(item["name"])
        if specs:
            details = f"[{specs['rarity']}] {specs['top_speed']} KM/H • {specs['hp']} HP • Use `/buy`"
        else:
            details = "Use `/buy` to purchase this item."
        embed.add_field(
            name=f"{item['name']} — {item['price']} coins",
            value=details,
            inline=False
        )
    if items[0].get("image_url"):
        embed.set_thumbnail(url=items[0]["image_url"])

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="buy", description="Buy an item or car from the shop.")
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

    specs = get_car_specs(selected["name"])
    embed = build_car_card_embed(specs, selected.get("image_url", "")) if specs else None

    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            content=f"👑 You claimed **{selected['name']}** using your **∞ Unlimited Owner Balance**!",
            embed=embed
        )

    await interaction.response.send_message(
        content=f"🎉 You bought **{selected['name']}** for **{selected['price']} coins**!",
        embed=embed
    )


@bot.tree.command(name="garage", description="View your owned cars and full spec cards.")
@app_commands.describe(member="The member whose garage you want to inspect")
async def garage(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    cars = get_user_cars(target.id)
    embeds = [build_car_card_embed(c) for c in cars[:5]]
    await interaction.response.send_message(
        content=f"🏎️ **{target.display_name}'s Garage** ({len(cars)} vehicle(s)):",
        embeds=embeds
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


@bot.tree.command(name="race", description="Start an online 2D pixel race in your Voice Channel (Phone & PC)!")
@app_commands.describe(bet="Optional coin wager per racer (default 0)")
async def race(interaction: discord.Interaction, bet: int = 0):
    if bet < 0:
        return await interaction.response.send_message(
            "❌ Bet cannot be negative.",
            ephemeral=True
        )

    if bet > 0 and not is_owner(interaction.user.id):
        if get_profile(interaction.user.id)["wallet"] < bet:
            return await interaction.response.send_message(
                f"❌ You don't have **{bet} coins** in your wallet!",
                ephemeral=True
            )

    vc = interaction.user.voice.channel if interaction.user.voice else None
    if not vc:
        return await interaction.response.send_message(
            "🔊 **Join a Voice Channel first**, then run `/race` to play together on Phone or PC!",
            ephemeral=True
        )

    room_id = str(vc.id)
    base_url = RENDER_EXTERNAL_URL or ""
    play_url = f"{base_url}/activity?room={room_id}&bet={bet}&uid={interaction.user.id}&name={interaction.user.display_name}"

    view = discord.ui.View()
    if play_url.startswith("http"):
        view.add_item(discord.ui.Button(
            label="📱 Play on Phone / Browser",
            url=play_url,
            style=discord.ButtonStyle.link
        ))

    embed = discord.Embed(
        title="🏎️ PIXEL-GP 2D // VOICE CHANNEL RACE",
        description=(
            f"🔊 **Voice Channel:** {vc.mention}\n"
            f"💰 **Entry Bet:** `{bet} coins`\n"
            f"📱 **Devices:** iPhone, Android, iPad, PC & Mac\n\n"
            f"Everyone in **{vc.name}** can join the race! Tap **Launch Activity** below or open the **Phone / Browser** link."
        ),
        color=discord.Color.red()
    )

    try:
        await interaction.response.launch_activity()
        await interaction.followup.send(embed=embed, view=view)
    except Exception:
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
