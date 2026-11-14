
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

import certifi

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


# FLASK SETUP

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
    authSource="admin",
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=30000,
    retryWrites=True
)

db = client["economy_bot_database"]

shop_collection = db["shop_items"]
economy_collection = db["player_profiles"]

try:
    client.admin.command("ping")

    economy_collection.create_index(
        "user_id",
        unique=True
    )

    print("MongoDB Atlas connected successfully!")

except PyMongoError as e:
    print("MongoDB connection failed:", e)
    raise


# DATABASE FUNCTIONS
