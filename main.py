import os
import discord
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import logging
import sys
from logging.handlers import RotatingFileHandler

# --- ロギング設定 ---
fastapi_log_file = "fastapi_app.log"
discord_log_file = "discord_bot.log"
formatter = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

fastapi_logger = logging.getLogger("fastapi_logger")
fastapi_logger.setLevel(logging.INFO)
fastapi_handler = RotatingFileHandler(fastapi_log_file, maxBytes=1024*1024, backupCount=5)
fastapi_handler.setFormatter(formatter)
fastapi_logger.addHandler(fastapi_handler)
console_handler_fastapi = logging.StreamHandler(sys.stdout)
console_handler_fastapi.setFormatter(formatter)
fastapi_logger.addHandler(console_handler_fastapi)

discord_logger = logging.getLogger("discord_logger")
discord_logger.setLevel(logging.INFO)
discord_handler = RotatingFileHandler(discord_log_file, maxBytes=1024*1024, backupCount=5)
discord_handler.setFormatter(formatter)
discord_logger.addHandler(discord_handler)
console_handler_discord = logging.StreamHandler(sys.stdout)
console_handler_discord.setFormatter(formatter)
discord_logger.addHandler(console_handler_discord)

logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

# --- 環境変数取得 ---
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
try:
    DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID'))
except (ValueError, TypeError):
    discord_logger.error("❌ DISCORD_CHANNEL_ID is not set or is invalid.")
    sys.exit(1)

# --- DiscordクライアントとFastAPIアプリ ---
intents = discord.Intents.default()
client = discord.Client(intents=intents)
app = FastAPI()

# --- Discordイベント ---
@client.event
async def on_ready():
    discord_logger.info(f"✅ Bot is online! Logged in as: {client.user.name}#{client.user.discriminator}")
    discord_logger.info("📝 Connected to:")
    for guild in client.guilds:
        discord_logger.info(f"  - Guild: {guild.name} (ID: {guild.id})")
        channel = guild.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            discord_logger.info(f"    - Target Channel: {channel.name} (ID: {channel.id})")
        else:
            discord_logger.warning(f"    - Target Channel with ID {DISCORD_CHANNEL_ID} not found in this guild.")
    
@client.event
async def on_disconnect():
    discord_logger.warning("🔴 Bot has disconnected.")

# --- FastAPIエンドポイント ---
@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        fastapi_logger.error("❌ index.html not found.")
        return {"error": "index.html not found"}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    if not DISCORD_BOT_TOKEN or DISCORD_CHANNEL_ID is None:
        fastapi_logger.error("❌ Discord token or channel ID not set.")
        raise HTTPException(status_code=500, detail="Discord token or channel ID not set.")

    file_path = f"/tmp/{file.filename}"
    try:
        fastapi_logger.info(f"🔄 Receiving file: {file.filename}")
        with open(file_path, "wb") as f:
            f.write(await file.read())
        
        fastapi_logger.info(f"📤 Sending file to Discord...")
        channel = client.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            fastapi_logger.error(f"❌ Discord channel with ID {DISCORD_CHANNEL_ID} not found.")
            raise HTTPException(status_code=404, detail="Discord channel not found.")
        
        await channel.send(f"ファイルがアップロードされました: `{file.filename}`", file=discord.File(file_path))
        fastapi_logger.info(f"✅ File successfully sent to Discord.")
        return {"message": "File uploaded successfully!"}
    except Exception as e:
        fastapi_logger.error(f"❌ Failed to process file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# --- サーバー起動 ---
# Uvicornの起動時にDiscordボットを非同期で起動する
@app.on_event("startup")
async def start_discord_bot():
    """アプリケーションの起動時にDiscordボットをログインさせます。"""
    try:
        await client.login(DISCORD_BOT_TOKEN)
        discord_logger.info("✅ Discord bot login successful!")
    except Exception as e:
        discord_logger.error(f"❌ Failed to login Discord bot: {e}")
        sys.exit(1)
