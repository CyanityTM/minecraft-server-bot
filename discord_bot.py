import subprocess
import discord
from discord.ext import commands
import discord_token
import asyncio
import os

CHANNEL_ID = 1506740165534683317

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
minecraft_process = None

@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)


def is_control_channel(ctx):
    return ctx.channel.id == CHANNEL_ID

async def monitor_server_startup(channel):
    """Monitor the server log until it's fully started"""
    log_file = os.path.expanduser("~/papermc/logs/latest.log")
    max_wait = 300  # 5 minutes timeout
    elapsed = 0
    last_position = 0
    
    # Start from the END of the current log file
    if os.path.exists(log_file):
        last_position = os.path.getsize(log_file)
        print(f"[Monitor] Starting from position {last_position} in existing log file")
    else:
        print(f"[Monitor] Log file doesn't exist yet, will wait for it")
    
    while elapsed < max_wait:
        try:
            if os.path.exists(log_file):
                current_size = os.path.getsize(log_file)
                # If file got smaller, it was recreated - reset position
                if current_size < last_position:
                    print(f"[Monitor] Log file was recreated (was {last_position}, now {current_size})")
                    last_position = 0
                
                # Read from last position to current end
                if current_size > last_position:
                    with open(log_file, "r") as f:
                        f.seek(last_position)
                        new_content = f.read()
                        print(f"[Monitor] Read {len(new_content)} new bytes from log")
                        if "Done (" in new_content:
                            print("[Monitor] Found 'Done (' in log - server is ready!")
                            await channel.send("✅ Minecraft server is fully up and running!")
                            return
                    last_position = current_size
                else:
                    print(f"[Monitor] No new data yet: {current_size} bytes (elapsed: {elapsed}s)")
        except Exception as e:
            print(f"[Monitor] Error monitoring log: {e}")
        
        await asyncio.sleep(2)
        elapsed += 2
    
    print("[Monitor] Timeout reached")
    await channel.send("⏱️ Server startup is taking longer than expected. Check logs manually.")

async def monitor_server_shutdown(channel):
    """Monitor if the server is still running and alert when it stops"""
    while True:
        try:
            result = subprocess.run(
                "screen -ls minecraft-server",
                shell=True,
                capture_output=True,
                text=True
            )
            # If "No Sockets found" appears, the screen session is dead
            if "minecraft-server" not in result.stdout:
                await channel.send("⚠️ Minecraft server has stopped!")
                return
        except Exception as e:
            print(f"Error monitoring shutdown: {e}")
        
        await asyncio.sleep(10)

@bot.command(name="start")
@commands.check(is_control_channel)
async def start_server(ctx):
    global minecraft_process
    if minecraft_process is not None and minecraft_process.poll() is None:
        await ctx.send("Minecraft server is already running.")
        return

    try:
        command = "cd ~/papermc; screen -S minecraft-server -dm sh start.sh; exit"
        minecraft_process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        await ctx.send("Starting Minecraft server...")
        # Monitor server startup in background
        bot.loop.create_task(monitor_server_startup(ctx.channel))
        # Monitor server shutdown in background
        bot.loop.create_task(monitor_server_shutdown(ctx.channel))
    except FileNotFoundError:
        await ctx.send("Unable to start the server: Java was not found. Make sure Java is installed.")
    except Exception as exc:
        await ctx.send(f"Failed to start the Minecraft server: {exc}")

@bot.command(name="status")
@commands.check(is_control_channel)
async def status(ctx):
    try:
        result = subprocess.run(
            "screen -ls minecraft-server",
            shell=True,
            capture_output=True,
            text=True
        )
        if "minecraft-server" in result.stdout:
            await ctx.send("Minecraft server is running.")
        else:
            await ctx.send("Minecraft server is not running.")
    except Exception as exc:
        await ctx.send(f"Failed to check server status: {exc}")

@bot.command(name="count")
@commands.check(is_control_channel)
async def player_count(ctx):
    try:
        from mcstatus import JavaServer
        server = JavaServer.lookup("127.0.0.1:25565")
        status = server.status()
        await ctx.send(f"Players online: {status.players.online}/{status.players.max}")
        if status.players.online > 0 and status.players.sample:
            player_list = ", ".join([player.name for player in status.players.sample])
            await ctx.send(f"Online players: {player_list}")
    except ImportError:
        await ctx.send("mcstatus library not installed. Install with: pip install mcstatus")
    except Exception as exc:
        await ctx.send(f"Failed to get player count: {exc}")

@start_server.error
@status.error
async def command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You can only use this command in the configured control channel.")
    else:
        await ctx.send(f"Command error: {error}")

bot.run(discord_token.get())
