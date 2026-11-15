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

# Connect to Supabase using Render Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    inv = profile.get("inventory") or []
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
                
                # Uploads image to Supabase Storage bucket named 'shop-images'
                supabase.storage.from_("shop-images").upload(
                    filename,
                    file_bytes,
                    {"content-type": image_file.mimetype}
                )
                image_url = supabase.storage.from_("shop-images").get_public_url(filename)

        supabase.table("shop").upsert({
            "name": name,
            "price": item_price,
            "image_url": image_url
        }).execute()

        return redirect(url_for("index"))

    shop_items = get_shop_items()
    return render_template("admin.html", shop_items=shop_items)
