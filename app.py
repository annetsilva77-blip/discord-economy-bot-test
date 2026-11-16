                view=None
            )

        # Reserve both bets before the race begins.
        update_balance(interaction.user.id, wallet_change=-bet)
        update_balance(opponent.id, wallet_change=-bet)

    track_len = 14
    p1_pos = 0
    p2_pos = 0
    msg = await interaction.original_response()

    await msg.edit(
        embed=build_pixel_track(
            interaction.user.display_name,
            p1_pos,
            opponent.display_name,
            p2_pos,
            track_len,
            "🔴 RED LIGHT... GET READY!"
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
        p1_pos += random.randint(1, 3)
        p2_pos += random.randint(1, 3)

        status = f"🟢 GO! {random.choice(events)}"

        await msg.edit(
            embed=build_pixel_track(
                interaction.user.display_name,
                p1_pos,
                opponent.display_name,
                p2_pos,
                track_len,
                status
            )
        )

        await asyncio.sleep(1.2)

    # Determine the winner.
    if p1_pos >= track_len and p2_pos >= track_len:
        if p1_pos > p2_pos:
            winner, loser = interaction.user, opponent
        elif p2_pos > p1_pos:
            winner, loser = opponent, interaction.user
        else:
            winner = None
            loser = None
    elif p1_pos >= track_len:
        winner, loser = interaction.user, opponent
    else:
        winner, loser = opponent, interaction.user

    if winner is None:
        if bet > 0:
            update_balance(interaction.user.id, wallet_change=bet)
            update_balance(opponent.id, wallet_change=bet)

        result_text = "🤝 PHOTO FINISH! It's a tie — bets refunded!"
    else:
        if bet > 0:
            update_balance(winner.id, wallet_change=bet * 2)

        result_text = (
            f"🏆 {winner.display_name} WINS and takes "
            f"{bet * 2} coins total pot!"
            if bet > 0
            else f"🏆 {winner.display_name} WINS the race!"
        )

    final_embed = build_pixel_track(
        interaction.user.display_name,
        p1_pos,
        opponent.display_name,
        p2_pos,
        track_len,
        result_text
    )
    final_embed.color = discord.Color.gold()

    await msg.edit(
        content=f"🏁 Race Finished! {result_text}",
        embed=final_embed
    )


# ==========================================
# START FLASK AND DISCORD BOT TOGETHER
# ==========================================

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "Missing DISCORD_TOKEN in Render Environment Variables."
        )

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )
    flask_thread.start()

    bot.run(DISCORD_TOKEN)
