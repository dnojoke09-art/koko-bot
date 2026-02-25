# koko_full_voice.py
# =====================================
# Koko AI Discord Bot – Full Voice & Memory
# =====================================

import os
import discord
from discord.ext import commands, tasks
import json
import asyncio
import random
import aiohttp
from datetime import datetime, timedelta
from gtts import gTTS
import tempfile
import threading
import whisper

# =========================
# CONFIG
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

MEMORY_FILE = "memory.json"
RELATIONSHIP_LEVELS = ["Stranger", "Familiar", "Friend", "Close", "Favorite"]

FREE_MESSAGES_PER_DAY = 20
STANDARD_MESSAGES_PER_DAY = 100
PREMIUM_MESSAGES_PER_DAY = float("inf")

# =========================
# MEMORY UTILITIES
# =========================

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=4)

def summarize_memory(user_memory):
    if "conversations" in user_memory and len(user_memory["conversations"]) > 10:
        user_memory["summary"] = "Summary of past conversations..."
        user_memory["conversations"] = user_memory["conversations"][-5:]

def get_relationship_level(xp):
    if xp >= 1000:
        return "Favorite"
    elif xp >= 500:
        return "Close"
    elif xp >= 200:
        return "Friend"
    elif xp >= 50:
        return "Familiar"
    else:
        return "Stranger"

def get_user_memory(memory, user_id):
    if user_id not in memory:
        memory[user_id] = {
            "conversations": [],
            "facts": {},
            "style": {"lowercase_ratio": 0.5, "emoji_usage": 0.2},
            "sentiment": 0,
            "xp": 0,
            "last_active": str(datetime.utcnow()),
            "tier": "free",
            "voice_channel": None
        }
    return memory[user_id]

# =========================
# GROQ AI + URL FETCH
# =========================

async def fetch_url_content(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                text = await resp.text()
                return text[:4000]
    except:
        return "Could not fetch content."

async def groq_request(prompt):
    url = "https://api.groq.com/v1/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {"model": MODEL, "prompt": prompt, "max_tokens": 150}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, timeout=15) as resp:
                result = await resp.json()
                return result.get("completion", "Hmm… I’m confused 😅")
    except:
        return "Oops, Groq API error 😵"

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

client = commands.Bot(command_prefix="!", intents=intents)
memory = load_memory()

# =========================
# TTS / VC FUNCTIONS
# =========================

async def tts_play(vc, text):
    """Play anime-style TTS in VC"""
    tts = gTTS(text=text, lang="en", tld="com")
    with tempfile.NamedTemporaryFile(delete=True, suffix=".mp3") as tmp:
        tts.save(tmp.name)
        if vc.is_connected():
            vc.play(discord.FFmpegPCMAudio(tmp.name))
            while vc.is_playing():
                await asyncio.sleep(0.5)

# Load Whisper model once at startup
whisper_model = whisper.load_model("base")

def stt_transcribe(audio_file):
    """Transcribe speech to text using Whisper"""
    result = whisper_model.transcribe(audio_file)
    return result["text"]

async def vc_listener(vc, user_id):
    """Continuously listen to VC for a single user (simulated)"""
    while vc.is_connected():
        await asyncio.sleep(10)
        simulated_text = None
        if simulated_text:
            reply = await generate_koko_reply(user_id, simulated_text)
            await tts_play(vc, reply)

async def generate_koko_reply(user_id, message_text):
    """Generate reply from Groq AI based on user memory and style"""
    user_memory = get_user_memory(memory, str(user_id))
    relationship = get_relationship_level(user_memory["xp"])
    prompt = f"""
You are Koko, a playful, sassy anime older sister AI.
You reply ONLY to {user_id}.
Personality: sarcastic, funny, expressive.
Memory: {user_memory.get('summary','')}
Style: lowercase_ratio={user_memory['style']['lowercase_ratio']}, emoji_usage={user_memory['style']['emoji_usage']}
Relationship Level: {relationship}
Message: {message_text}
Reply in 1-2 short sentences in a playful anime style.
"""
    reply = await groq_request(prompt)
    # Update memory
    user_memory["conversations"].append({"timestamp": str(datetime.utcnow()), "message": message_text})
    user_memory["xp"] += 5
    summarize_memory(user_memory)
    save_memory(memory)
    return reply

# =========================
# ASYNC TASKS
# =========================

@tasks.loop(minutes=random.randint(15,30))
async def idle_task():
    for guild in client.guilds:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(random.choice([
                    "Hehe… anyone here? 😏",
                    "I’m bored… entertain me! 😂",
                    "Just thinking about dark stuff… wanna hear? 🫣"
                ]))

@tasks.loop(minutes=random.randint(15,30))
async def rel_ping_task():
    for user_id, user_data in memory.items():
        last = datetime.fromisoformat(user_data.get("last_active", str(datetime.utcnow())))
        if (datetime.utcnow() - last) > timedelta(minutes=30):
            user = client.get_user(int(user_id))
            if user:
                await user.send("Heyyy 😏 Koko remembers you!")

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print(f"Koko online as {client.user}")
    idle_task.start()
    rel_ping_task.start()

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    user_id = str(message.author.id)
    user_memory = get_user_memory(memory, user_id)
    user_memory["last_active"] = str(datetime.utcnow())
    total_chars = len(message.content)
    if total_chars > 0:
        lowercase = sum(1 for c in message.content if c.islower())
        emoji_count = sum(1 for c in message.content if c in "😀😂🤣😅😎😏🙃😉")
        user_memory["style"]["lowercase_ratio"] = (user_memory["style"]["lowercase_ratio"] + lowercase/total_chars)/2
        user_memory["style"]["emoji_usage"] = (user_memory["style"]["emoji_usage"] + emoji_count/total_chars)/2
    user_memory["xp"] += 5
    user_memory["conversations"].append({"timestamp": str(datetime.utcnow()), "message": message.content})
    summarize_memory(user_memory)
    save_memory(memory)
    reply = await generate_koko_reply(user_id, message.content)
    await message.channel.send(reply)
    await client.process_commands(message)

# =========================
# COMMANDS
# =========================

@client.command()
async def joinvc(ctx):
    """Join user's VC"""
    if ctx.author.voice and ctx.author.voice.channel:
        vc = await ctx.author.voice.channel.connect()
        get_user_memory(memory, str(ctx.author.id))["voice_channel"] = ctx.author.voice.channel.id
        await ctx.send("Koko joined VC! 🎤")
        asyncio.create_task(vc_listener(vc, ctx.author.id))
    else:
        await ctx.send("You must be in a VC 😏")

@client.command()
async def leavevc(ctx):
    """Leave VC"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Koko left the VC 😎")
    else:
        await ctx.send("I’m not in a VC 😅")

@client.command()
async def speak(ctx, *, text):
    """Speak in VC"""
    if ctx.voice_client:
        await tts_play(ctx.voice_client, text)
    else:
        await ctx.send("Join a VC first 😏")

@client.command()
async def listen(ctx):
    """Listen and respond in VC"""
    if ctx.voice_client:
        await ctx.send("Listening… (simulated)")
    else:
        await ctx.send("Join a VC first 😏")

# =========================
# Existing Commands
# =========================

@client.command()
async def setup(ctx):
    user_id = str(ctx.author.id)
    user_memory = get_user_memory(memory, user_id)
    tier = user_memory.get("tier","free")
    daily_limit = {"free":FREE_MESSAGES_PER_DAY,"standard":STANDARD_MESSAGES_PER_DAY,"premium":PREMIUM_MESSAGES_PER_DAY}[tier]
    await ctx.send(f"Setup complete! You can send {daily_limit} messages per day.")

@client.command()
async def personality(ctx, *, choice=None):
    user_id = str(ctx.author.id)
    tier = get_user_memory(memory, user_id)["tier"]
    if tier == "free":
        await ctx.send("Free tier uses pre-set personality 😏")
    else:
        await ctx.send(f"Personality set to {choice}")

@client.command()
async def relationship(ctx, user: discord.User):
    user_id = str(user.id)
    level = get_relationship_level(get_user_memory(memory, user_id)["xp"])
    await ctx.send(f"Relationship with {user.name}: {level}")

@client.command()
async def ping(ctx):
    await ctx.send(random.choice(["Yes? 😏","I’m here, don’t waste my time 😎","Sup? 😜"]))

@client.command()
async def funfact(ctx):
    facts = [
        "Did you know some anime villains were based on real people? 🫣",
        "Dark fact: Some cats can recognize humans but ignore them 😼",
        "Anime twist: every 'slice of life' anime has secretly dramatic backstories 😏"
    ]
    await ctx.send(random.choice(facts))

@client.command()
async def mimic(ctx, user: discord.User):
    user_memory = get_user_memory(memory, str(user.id))
    style = user_memory["style"]
    await ctx.send(f"Mimicking {user.name}'s style: lowercase_ratio={style['lowercase_ratio']:.2f}, emoji_usage={style['emoji_usage']:.2f} 😏")

@client.command()
async def forget(ctx, count:int=1):
    user_id = str(ctx.author.id)
    user_memory = get_user_memory(memory, user_id)
    tier = user_memory.get("tier","free")
    limits = {"free":5,"standard":20,"premium":len(user_memory["conversations"])}
    forget_count = min(count, limits[tier])
    user_memory["conversations"] = user_memory["conversations"][:-forget_count]
    save_memory(memory)
    await ctx.send(f"Forgot last {forget_count} messages 😏")

@client.command()
async def gift(ctx):
    user_id = str(ctx.author.id)
    user_memory = get_user_memory(memory, user_id)
    user_memory["xp"] += 20
    save_memory(memory)
    await ctx.send(f"Yay! Gift received 😍 Relationship XP increased!")

@client.command()
async def url(ctx, *, link:str):
    user_id = str(ctx.author.id)
    tier = get_user_memory(memory, user_id)["tier"]
    if tier == "free":
        await ctx.send("URL summarization unlocked for Standard+ only 😏")
    else:
        content = await fetch_url_content(link)
        await ctx.send(f"Summary of URL: {content[:500]}...")

# =========================
# START BOT
# =========================

client.run(DISCORD_TOKEN)
