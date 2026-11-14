# MONGODB CONNECTION

import certifi

mongo_uri = os.environ.get("MONGODB_URI")

if not mongo_uri:
    raise RuntimeError("MONGODB_URI environment variable is missing.")

client = MongoClient(
    mongo_uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=30000
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
