import discord.ext
from discord.ext import commands
from igdb.wrapper import IGDBWrapper
import datetime
import os
from cogs.Logger import AsyncLogger, Logger
import logging
import json

client = discord.Client()
startup_extensions = ["cogs.Music", "cogs.BotFunctions", "cogs.Extensions", "cogs.CommandErrorHandler"]
with open('/app/config/config.json') as config_file:
    config = json.load(config_file)

os.system('clear')
print("Starting bot...")
print("")


def get_prefix(bot, msg):
    with open('/app/config/prefixes.json') as prefix_file:
        prefixes = json.load(prefix_file)
    guilds = []
    for guild in prefixes[str(bot.user.id)]:
        guilds.append(str(guild))
    if not msg.guild:
        return commands.when_mentioned_or('!')(bot, msg)
    elif str(msg.guild.id) in guilds:
        return commands.when_mentioned_or(prefixes[str(bot.user.id)][str(msg.guild.id)])(bot, msg)
    else:
        return commands.when_mentioned_or('!')(bot, msg)


def is_guild(ctx):
    if ctx.guild:
        return True
    else:
        raise commands.NoPrivateMessage


wrapper = IGDBWrapper(config['igdb']['client_id'], config['igdb']['access_token'])
bot = commands.AutoShardedBot(command_prefix=get_prefix,
                              description="Frooty is designed for the FrootGaming Community " +
                                          "to support administrative features or help with some fun")

log = AsyncLogger('FrootGaming Bot', 'Bot', bot)
logger = logging.getLogger('discord')
logger.setLevel(logging.NOTSET)
handler = Logger('FrootGaming Bot', 'Discord', bot)
handler.setFormatter(logging.Formatter('%(levelname)s-%(name)s: %(message)s'))
logger.addHandler(handler)


def get_footer(ctx):
    now = datetime.datetime.now()
    date = str(now.day) + '-' + str(now.month) + '-' + str(now.year)
    time = str(now.hour) + ':' + format(str(now.minute), '0>2.2')
    get_footer.footer = str(ctx.author) + " • " + date + ' ' + time


class General(commands.Cog):
    """General commands"""
    __slots__ = 'bot'

    def __init__(self):
        self.bot = bot

    @commands.command()
    @commands.has_role("Bot Controller")
    async def kick(self, ctx, person_to_kick: discord.Member):
        """Kick a player"""
        guild = ctx.message.guild
        try:
            await guild.kick(person_to_kick)
            await ctx.send(":ballot_box_with_check: `" + str(person_to_kick) +
                           "` **was successfully kicked from the server.**")
            await log.info(str(ctx.author) + ' kicked ' + str(person_to_kick))
        except discord.errors.Forbidden:
            await log.info(str(ctx.author) + ' failed to kick ' + str(person_to_kick))
            await ctx.send(":negative_squared_cross_mark: **I don't have permission to do that!**")

    @commands.command(aliases=['e'])
    @commands.has_role("Secure")
    async def encrypt(self, ctx, *, msg):
        await ctx.message.delete()
        new_msg = '**[' + str(ctx.author) + ']** '
        msg = msg.split(' ')
        for word in msg:
            length = len(word)
            new_word = ""
            for i in range(length):
                new_word += word[length - 1]
                length -= 1
            new_msg += new_word + ' '
        await ctx.send(new_msg)
        await log.info(str(ctx.author) + ' used command ENCRYPT')

    @commands.command()
    async def wdem(self, ctx, *, game=None):
        """Ask people to play a game with you"""
        if game is None:
            game = ctx.channel.topic

        if game is None:
            await ctx.send(":negative_squared_cross_mark: **No games were found!**")
            return

        try:
            byte_array = wrapper.api_request('games', 'search "{}"; fields name, cover.image_id;'.format(game))
            result = json.loads(byte_array)[0]
            embed = discord.Embed(title="Wie doet er mee met `{}`?".format(result['name']),
                                  description="\n✅ `Ik doe mee!` \n❎ `Ik doe niet mee.` \n❓ `Ik weet het nog niet.`",
                                  color=0x477FC9)
            embed.set_thumbnail(url="https://images.igdb.com/igdb/image/upload/t_cover_big/{}.jpg"
                                .format(result['cover']['image_id']))
            embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
            message = await ctx.send(embed=embed)
            await message.add_reaction("✅")
            await message.add_reaction("❎")
            await message.add_reaction("❓")
        except IndexError:
            await ctx.send(":negative_squared_cross_mark: **No games were found!**")


@bot.command(usage="<message>")
async def wdone(ctx, *, msg: discord.Message = None):
    """Invalidate a previous game poll"""
    if msg is None:
        messages = await ctx.channel.history(limit=15).flatten()
        for message in messages:
            if message.author == bot.user and (message.embeds is not None or []):
                embed = message.embeds[0]
                if "Wie doet er mee" in embed.title:
                    return await done(message)
    return await done(msg)


async def done(msg):
    await msg.clear_reactions()
    await msg.add_reaction("👍")
    await msg.add_reaction("🇩")
    await msg.add_reaction("🇴")
    await msg.add_reaction("🇳")
    await msg.add_reaction("🇪")


@bot.event
async def on_member_join(member):
    if member.guild.id == 455481676542377995:
        channel = bot.get_channel(589120991985139733)
        await channel.send(":confetti_ball: Welcome to the community, **" + str(member) + "**!")


@bot.event
async def on_message(message):
    ctx = await bot.get_context(message)
    if (not ctx.valid) and "<@!{}>".format(bot.user.id) in message.content:
        if isinstance(message.channel, discord.DMChannel) is False:
            with open("/app/config/prefixes.json") as prefix_read:
                prefix_json = json.load(prefix_read)
            try:
                guild_prefix = prefix_json[str(bot.user.id)][str(ctx.guild.id)]
            except KeyError:
                guild_prefix = '*'
            embed = discord.Embed(title=bot.user.name, description=bot.description, color=0x4F8FF3)
            embed.add_field(name="Prefix", value="Use `{}` or <@{}> in this guild".format(guild_prefix, bot.user.id))
            embed.set_footer(text="Bot made by ParrotLync#2458")
            await ctx.send(embed=embed)
        else:
            await ctx.send(":no_entry: `This function can't be used in private messaging.`")
    await bot.process_commands(message)


@bot.event
async def on_ready():
    print("\n## Logged in as", bot.user.name)
    print("## ID:", bot.user.id)
    print('')
    await log.info(str(bot.user.name) + " is now online!")
    if __name__ == "__main__":
        for extension in startup_extensions:
            try:
                bot.load_extension(extension)
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await log.exception('Failed to load extension {}\n{}'.format(extension, exc))


bot.add_cog(General())
try:
    bot.run(config['tokens']['FGBot'])
except RuntimeError:
    handler.warning('Closed before completing cleanup')
