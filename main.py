import os
import discord
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

# --- ロギング設定 ---
# ログファイル名
fastapi_log_file = "fastapi_app.log"
discord_log_file = "discord_bot.log"

# フォーマット設定
formatter = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# FastAPIログ設定
fastapi_logger = logging.getLogger("fastapi_logger")
fastapi_logger.setLevel(logging.INFO)
# ファイルハンドラー
fastapi_handler = RotatingFileHandler(fastapi_log_file, maxBytes=1024*1024, backupCount=5)
fastapi_handler.setFormatter(formatter)
fastapi_logger.addHandler(fastapi_handler)
# コンソールハンドラー
console_handler_fastapi = logging.StreamHandler(sys.stdout)
console_handler_fastapi.setFormatter(formatter)
fastapi_logger.addHandler(console_handler_fastapi)

# Discordボットログ設定
discord_logger = logging.getLogger("discord_logger")
discord_logger.setLevel(logging.INFO)
# ファイルハンドラー
discord_handler = RotatingFileHandler(discord_log_file, maxBytes=1024*1024, backupCount=5)
discord_handler.setFormatter(formatter)
discord_logger.addHandler(discord_handler)
# コンソールハンドラー
console_handler_discord = logging.StreamHandler(sys.stdout)
console_handler_discord.setFormatter(formatter)
discord_logger.addHandler(console_handler_discord)

# 既存のライブラリログを抑制
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
    """Discordボットがログインした際に実行されます。"""
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
    """Discordボットが切断された際に実行されます。"""
    discord_logger.warning("🔴 Bot has disconnected.")

# --- FastAPIエンドポイント ---
@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    """ルートURLでHTMLファイルを提供します。"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        fastapi_logger.error("❌ index.html not found.")
        return {"error": "index.html not found"}

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    """アップロードされたファイルをDiscordに送信します。"""
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
if __name__ == "__main__":
    def run_discord_bot():
        client.run(DISCORD_BOT_TOKEN, log_handler=None)

    bot_thread = threading.Thread(target=run_discord_bot)
    bot_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
