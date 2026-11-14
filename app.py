

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

    if not update_balance(
        member.id,
        wallet_change=amount
    ):
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

    asyncio.run(
        bot.start(token)
    )


# START APPLICATION

if __name__ == "__main__":

    bot_thread = threading.Thread(
        target=run_discord_bot,
        daemon=True
    )

    bot_thread.start()

    port = int(
        os.environ.get("PORT", 10000)
