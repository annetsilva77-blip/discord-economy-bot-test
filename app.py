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
