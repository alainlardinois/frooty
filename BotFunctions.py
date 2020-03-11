import discord
from discord.ext import commands
import asyncio
from Logger import AsyncLogger
import json


def is_guild(ctx):
    if ctx.guild:
        return True
    else:
        raise commands.NoPrivateMessage


class Bot(commands.Cog):
    """General bot commands"""
    __slots__ = ('bot', 'log')

    def __init__(self, bot, log):
        self.bot = bot
        self.log = log
        
    @commands.command(aliases=['bc'])
    @commands.has_role("Bot Controller")
    async def broadcast(self, ctx, *, message):
        """Broadcast a message in your current channel"""
        await ctx.message.delete()
        await ctx.send(":loudspeaker: " + message)
        await self.log.info(str(ctx.author) + ' used command BROADCAST')
    
    @commands.command()
    @commands.has_role("Bot Controller")
    async def embed(self, ctx, title, *, description):
        """Send an embed in your current channel"""
        await ctx.message.delete()
        embed = discord.Embed(title=title, description=description, color=0x00ff00)
        await ctx.send(embed=embed)
        await self.log.info(str(ctx.author) + ' used command EMBED')

    @commands.command()
    @commands.has_role("Bot Controller")
    async def clear(self, ctx, *, number=100):
        """Delete messages from a text channel."""
        await ctx.message.delete()
        if number <= 100:
            deleted = await ctx.channel.purge(limit=number)
            message = await ctx.send(':ballot_box_with_check:  Deleted {} message(s)'.format(len(deleted)))
            await asyncio.sleep(5)
            await message.delete()
        else:
            await ctx.send(':negative_squared_cross_mark: You can delete a maximum of 100 messages at one!')
        await self.log.info(str(ctx.author) + ' used command CLEAR')

    @commands.command()
    async def ping(self, ctx):
        """Ping the bot"""
        await ctx.message.delete()
        await ctx.send("Pong! {0}ms".format(round(self.bot.latency, 1)))
        await self.log.info(str(ctx.author) + ' used command PING')

    @commands.command()
    @commands.check(is_guild)
    async def prefix(self, ctx, guild_prefix=None):
        """Get the current prefix for this guild or choose another one"""
        with open("/config/prefixes.json") as prefix_read:
            prefix_json = json.load(prefix_read)
        if not guild_prefix:
            try:
                guild_prefix = prefix_json[str(self.bot.user.id)][str(ctx.guild.id)]
            except KeyError:
                guild_prefix = '!'
            description = ""
        else:
            prefix_json[str(self.bot.user.id)][str(ctx.guild.id)] = guild_prefix
            with open("/config/prefixes.json", "w+") as prefix_write:
                prefix_write.write(json.dumps(prefix_json))
            description = "Prefix changed!"
        embed = discord.Embed(description="{} Use `{}` or <@{}> in this guild".format(description, guild_prefix,
                                                                                      self.bot.user.id))
        await ctx.send(embed=embed)


def setup(bot):
    log = AsyncLogger(str(bot.user.name), 'BotFunctions', bot)
    bot.add_cog(Bot(bot, log))
