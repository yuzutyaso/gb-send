import os
import discord
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import HTMLResponse
import uvicorn
import logging
import sys
import asyncio
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
if not DISCORD_BOT_TOKEN:
    discord_logger.error("❌ DISCORD_BOT_TOKEN is not set.")
    sys.exit(1)

# --- DiscordクライアントとFastAPIアプリ ---
intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True 
client = discord.Client(intents=intents)
app = FastAPI()

# --- Discordイベント ---
@client.event
async def on_ready():
    discord_logger.info(f"✅ Bot is online! Logged in as: {client.user.name}#{client.user.discriminator}")
    discord_logger.info("📝 Connected to:")
    for guild in client.guilds:
        discord_logger.info(f"  - Guild: {guild.name} (ID: {guild.id})")

@client.event
async def on_disconnect():
    discord_logger.warning("🔴 Bot has disconnected.")

# --- FastAPIエンドポイント ---
@app.on_event("startup")
async def start_discord_bot():
    try:
        asyncio.create_task(client.start(DISCORD_BOT_TOKEN))
        discord_logger.info("✅ Discord bot task created!")
    except Exception as e:
        discord_logger.error(f"❌ Failed to start Discord bot: {e}")
        sys.exit(1)

@app.get("/", response_class=HTMLResponse)
async def read_root_html():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return html_content
    except FileNotFoundError:
        fastapi_logger.error("❌ index.html not found.")
        return {"error": "index.html not found"}

@app.get("/channels")
async def get_channels():
    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Discord bot is not ready.")

    channels = []
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                channels.append({"id": str(channel.id), "name": f"#{channel.name} ({guild.name})"})
    
    return channels

@app.get("/messages/{channel_id}")
async def get_messages(channel_id: str):
    """指定されたチャンネルのメッセージ履歴（最新50件）を返します。"""
    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Discord bot is not ready.")

    try:
        channel = client.get_channel(int(channel_id))
        if not channel:
            raise HTTPException(status_code=404, detail="Discord channel not found.")

        messages = []
        async for msg in channel.history(limit=50):
            messages.append({
                "author": msg.author.name,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat(),
                # 添付ファイル情報を追加
                "attachments": [{"url": att.url, "filename": att.filename} for att in msg.attachments],
            })
        return messages

    except Exception as e:
        fastapi_logger.error(f"❌ Failed to fetch messages for channel {channel_id}: {e}")
        raise HTTPException(status_code=500, detail=f"メッセージの取得に失敗しました: {e}")


@app.post("/upload/")
async def upload_file(channel_id: str = Form(...), message: str | None = Form(None), file: UploadFile | None = File(None)):
    """指定されたチャンネルにファイルとメッセージをアップロードします。"""
    
    if not message and not file:
        raise HTTPException(status_code=400, detail="メッセージまたはファイルを送信してください。")

    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Discord bot is not ready.")
    
    content = message if message is not None else ""
    
    file_path = None
    try:
        fastapi_logger.info(f"📤 Sending to Discord...")
        channel = client.get_channel(int(channel_id))
        if not channel:
            fastapi_logger.error(f"❌ Discord channel with ID {channel_id} not found.")
            raise HTTPException(status_code=404, detail="Discord channel not found.")
        
        if file and file.filename:
            file_path = f"/tmp/{file.filename}"
            with open(file_path, "wb") as f:
                f.write(await file.read())
            
            await channel.send(content=content, file=discord.File(file_path))
            
        else:
            await channel.send(content=content)

        fastapi_logger.info(f"✅ Message and/or file successfully sent to Discord.")
        return {"message": "投稿が完了しました！"}
    except Exception as e:
        fastapi_logger.error(f"❌ Failed to process request: {e}")
        raise HTTPException(status_code=500, detail=f"投稿に失敗しました: {e}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
