
# --- JOBS AND WORK SHIFT MODULE ---

@bot.tree.command(name="jobs", description="Lists jobs and lets you choose a career.")
@app_commands.describe(join_job="Name of the job you want to join (optional)")
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
            "To apply for a vacancy, type: `/jobs join_job:[Name]`\n"
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


# --- WORK SHIFT MODULE ---

@bot.tree.command(name="work", description="Complete work shifts to receive salary.")
async def work(interaction: discord.Interaction):

    profile = get_profile(interaction.user.id)

    current_job = profile.get("job", "beggar")
    last_work = profile.get("last_work", 0)

    job_info = JOBS_LIST.get(current_job, JOBS_LIST["beggar"])

    current_time = int(time.time())
    elapsed = current_time - last_work

    if elapsed < job_info["cooldown"]:
        remaining = job_info["cooldown"] - elapsed

        return await interaction.response.send_message(
            f"⏳ Shift constraints active! Return to work in {remaining} seconds.",
            ephemeral=True
        )

    earnings = random.randint(
        job_info["salary_min"],
        job_info["salary_max"]
    )

    update_balance(interaction.user.id, wallet_change=earnings)
    update_work_timestamp(interaction.user.id)

    await interaction.response.send_message(
        f"💰 You completed a work shift as a {current_job.capitalize()} "
        f"and received **{earnings} coins**!"
    )


# --- SHOPPING ENGINE PROTOCOLS ---

@bot.tree.command(name="shop", description="Displays all available shop items.")
async def shop(interaction: discord.Interaction):

    shop_items = load_json(SHOP_FILE)

    if not shop_items:
        return await interaction.response.send_message(
            "🛒 The item stock rooms are empty! Use the web dashboard to list products.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="🛒 Active Economy Shop",
        description="Browse items available for purchase:",
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

    embed.description = shop_list_text or "No items currently listed."

    if last_image_url:
        embed.set_thumbnail(url=last_image_url)

    await interaction.response.send_message(embed=embed)


# --- BUY COMMAND ---

@bot.tree.command(name="buy", description="Purchase items from the shop.")
@app_commands.describe(item_name="Exact product name shown in /shop")
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
            "❌ Product not located! Ensure the name matches the /shop listing exactly.",
            ephemeral=True
        )

    if profile["wallet"] < item["price"]:
        return await interaction.response.send_message(
            f"❌ Transaction failed. You require {item['price']} coins in your wallet.",
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
        f"🎉 Acquisition confirmed! **{item['name']}** bought for "
        f"**{item['price']} coins**. Review your items via `/inventory`."
    )


# --- INVENTORY COMMAND ---

@bot.tree.command(name="inventory", description="Checks your storage inventory.")
@app_commands.describe(member="Member whose inventory you want to inspect (optional)")
async def inventory(interaction: discord.Interaction, member: discord.Member = None):

    target = member or interaction.user

    profile = get_profile(target.id)

    user_inventory = profile.get("inventory", [])

    if not user_inventory:
        return await interaction.response.send_message(
            f"🎒 {target.name}'s inventory ledger is empty!",
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
        description=inv_list,
        color=discord.Color.blue()
    )

    await interaction.response.send_message(embed=embed)


# --- OVERRIDE ADMINISTRATIVE TOOLS ---

@bot.tree.command(name="addmoney", description="Grants coins to a member (Admins/Owner Only).")
@app_commands.describe(
    member="The player receiving coins",
    amount="Number of coins to transfer"
)
async def addmoney(interaction: discord.Interaction, member: discord.Member, amount: int):

    is_owner = interaction.user.id == OWNER_ID

    is_admin = (
        interaction.permissions.administrator
        if interaction.guild else False
    )

    if not (is_owner or is_admin):
        return await interaction.response.send_message(
            "❌ Command execution rejected. Insufficient security credentials.",
            ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Transaction error: Amount must exceed 0.",
            ephemeral=True
        )

    update_balance(member.id, wallet_change=amount)

    await interaction.response.send_message(
        f"✅ Secure injection complete! **{amount} coins** deposited to {member.mention}'s wallet."
    )


# --- APPLICATION COOLDOWN ERROR HANDLER ---

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(error, app_commands.CommandOnCooldown):

        message = (
            f"⏳ Slow down! Try again in "
            f"{error.retry_after:.2f}s."
        )

    else:

        print(f"Command error: {error}")

        message = "❌ An unexpected command error occurred."

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


# --- BACKGROUND RUNNER ENGINES ---

def run_discord_bot():

    token = os.environ.get("DISCORD_TOKEN")

    if not token:
        print("❌ CRITICAL ERROR: DISCORD_TOKEN was not found.")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(bot.start(token))
    except Exception as error:
        print(f"Discord bot startup error: {error}")
    finally:
        loop.close()


# --- MAIN ---

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
