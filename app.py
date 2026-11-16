import os
import random
import threading
import asyncio
import time
import discord

from discord import app_commands
from discord.ext import commands
from flask import Flask, render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from supabase import create_client, Client

OWNER_ID = 1327939431608483895

# Read and clean environment variables from Render
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
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

app = Flask(__name__)


def is_owner(user_id) -> bool:
    return int(user_id) == OWNER_ID


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


# --- FLASK ADMIN WEB DASHBOARD ---

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


@bot.tree.command(name="addmoney", description="Owner only: Add coins to a user's wallet.")
@app_commands.describe(member="The member to give coins to", amount="Amount of coins to add")
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not is_owner(interaction.user.id):
        return await interaction.response.send_message(
            "❌ Only the bot owner can use this command.",
            ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Amount must be greater than zero.",
            ephemeral=True
        )

    if is_owner(member.id):
        return await interaction.response.send_message(
            "👑 You already have **∞ unlimited coins**!",
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
        embed.add_field(
            name=f"{name.title()} ({info['salary_min']}–{info['salary_max']} coins)",
            value=f"{info['description']}\nCooldown: {info['cooldown']}s",
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


@bot.tree.command(name="shop", description="View items available in the shop.")
async def shop(interaction: discord.Interaction):
    items = get_shop_items()
    if not items:
        return await interaction.response.send_message("🛒 The shop is currently empty!")

    embed = discord.Embed(title="🛒 Item Shop", color=discord.Color.green())
    for item in items:
        embed.add_field(
            name=f"{item['name']} — {item['price']} coins",
            value="Use `/buy` to purchase this item.",
            inline=False
        )
    if items[0].get("image_url"):
        embed.set_thumbnail(url=items[0]["image_url"])

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="buy", description="Buy an item from the shop.")
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

    if is_owner(interaction.user.id):
        return await interaction.response.send_message(
            f"👑 You claimed **{selected['name']}** using your **∞ Unlimited Owner Balance**!"
        )

    await interaction.response.send_message(
        f"🎉 You bought **{selected['name']}** for **{selected['price']} coins**!"
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


# --- 1V1 PIXEL RACING COMMAND ---

class RaceAcceptView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, bet: int):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.accepted = False

    @discord.ui.button(label="🏁 Accept Race", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message(
                "❌ Only the challenged player can accept this race!",
                ephemeral=True
            )

        self.accepted = True
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=f"🚦 **{self.challenger.mention} vs {self.opponent.mention}** — Engines revving!",
            view=self
        )
        self.stop()

    @discord.ui.button(label="✖️ Decline", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message(
                "❌ Only the challenged player can decline!",
                ephemeral=True
            )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=f"🚫 **{self.opponent.display_name}** declined the race.",
            embed=None,
            view=self
        )
        self.stop()


def build_pixel_track(p1_name, p1_pos, p2_name, p2_pos, track_len=14, status_text=""):
    def render_lane(pos, car_emoji):
        pos = min(pos, track_len)
        road_before = "⬛" * pos
        road_after = "▫️" * (track_len - pos)
        return f"🚦{road_before}{car_emoji}{road_after}🏁"

    lane1 = render_lane(p1_pos, "🏎️")
    lane2 = render_lane(p2_pos, "🚗")
    border = "🟦" * (track_len + 3)

    track_display = (
        f"{border}\n"
        f"**P1 • {p1_name}**\n"
        f"{lane1}\n"
        f"⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜\n"
        f"**P2 • {p2_name}**\n"
        f"{lane2}\n"
        f"{border}"
    )

    embed = discord.Embed(
        title="🕹️ PIXEL-GP 2D // 1v1 DRAG RACE",
        description=track_display,
        color=discord.Color.red()
    )
    if status_text:
        embed.set_footer(text=status_text)
    return embed


@bot.tree.command(name="race", description="Challenge another player to a 1v1 2D pixel car race!")
@app_commands.describe(opponent="The player you want to race", bet="Coins to bet on the race (default 0)")
async def race(interaction: discord.Interaction, opponent: discord.Member, bet: int = 0):
    if opponent.bot or opponent.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You must challenge another real player!",
            ephemeral=True
        )

    if bet < 0:
        return await interaction.response.send_message(
            "❌ Bet cannot be negative.",
            ephemeral=True
        )

    if bet > 0:
        if not is_owner(interaction.user.id) and get_profile(interaction.user.id)["wallet"] < bet:
            return await interaction.response.send_message(
                f"❌ You don't have **{bet} coins** in your wallet!",
                ephemeral=True
            )
        if not is_owner(opponent.id) and get_profile(opponent.id)["wallet"] < bet:
            return await interaction.response.send_message(
                f"❌ **{opponent.display_name}** doesn't have **{bet} coins** in their wallet!",
                ephemeral=True
            )

    challenge_embed = discord.Embed(
        title="🏁 1v1 Pixel Race Challenge!",
        description=(
            f"**{interaction.user.display_name}** (🏎️) challenged **{opponent.display_name}** (🚗)!\n"
            f"💰 **Wager:** `{bet} coins`\n\n"
            f"{opponent.mention}, click **Accept Race** within 30 seconds!"
        ),
        color=discord.Color.orange()
    )

    view = RaceAcceptView(interaction.user, opponent, bet)
    await interaction.response.send_message(
        content=opponent.mention,
        embed=challenge_embed,
        view=view
    )

    await view.wait()
    if not view.accepted:
        return

    if bet > 0:
        p1_ok = is_owner(interaction.user.id) or get_profile(interaction.user.id)["wallet"] >= bet
        p2_ok = is_owner(opponent.id) or get_profile(opponent.id)["wallet"] >= bet
        if not p1_ok or not p2_ok:
            return await interaction.edit_original_response(
                content="❌ Race cancelled because one player no longer has enough coins.",
                embed=None,
                view=None
            )

    track_len = 14
    p1_pos = 0
    p2_pos = 0

    msg = await interaction.original_response()
    await msg.edit(
        embed=build_pixel_track(
            interaction.user.display_name, p1_pos,
            opponent.display_name, p2_pos,
            track_len, "🔴 RED LIGHT... GET READY!"
        ),
        view=None
    )
    await asyncio.sleep(1.5)

    events = [
        "🔥 Turbo boost activated!",
        "💨 Drafting behind rival!",
        "⚡ Perfect gear shift!",
        "🛞 Tires screeching on asphalt!"
    ]

    while p1_pos < track_len and p2_pos < track_len:
        p1_step = random.randint(1, 3)
        p2_step = random.randint(1, 3)
        p1_pos += p1_step
        p2_pos += p2_step

        status = f"🟢 GO! {random.choice(events)}"
        await msg.edit(
            embed=build_pixel_track(
                interaction.user.display_name, p1_pos,
                opponent.display_name, p2_pos,
                track_len, status
            )
        )
        await asyncio.sleep(1.2)

    if p1_pos >= track_len and p2_pos >= track_len:
        if p1_pos > p2_pos:
            winner, loser = interaction.user, opponent
        elif p2_pos > p1_pos:
            winner, loser = opponent, interaction.user
        else:
            winner = None
    elif p1_pos >= track_len:
        winner, loser = interaction.user, opponent
    else:
        winner, loser = opponent, interaction.user

    if winner is None:
        result_text = "🤝 PHOTO FINISH! It's a tie — no coins lost!"
    else:
        if bet > 0:
            update_balance(winner.id, wallet_change=bet)
            update_balance(loser.id, wallet_change=-bet)
            result_text = f"🏆 {winner.display_name} WINS and takes {bet * 2} coins total pot!"
        else:
            result_text = f"🏆 {winner.display_name} WINS the race!"

    final_embed = build_pixel_track(
        interaction.user.display_name, p1_pos,
        opponent.display_name, p2_pos,
        track_len, result_text
    )
    final_embed.color = discord.Color.gold()
    await msg.edit(content=f"🏁 **Race Finished!** {result_text}", embed=final_embed)


# --- START FLASK & DISCORD BOT TOGETHER ---

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Missing DISCORD_TOKEN in Render Environment Variables.")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    bot.run(DISCORD_TOKEN)
