import discord.ext
from discord.ext import commands
import datetime
import os
from Logger import AsyncLogger, Logger
import logging
import json
import Chatbot
import asyncio

client = discord.Client()
startup_extensions = ["Music", "BotFunctions", "Extensions", "CommandErrorHandler"]
with open('config.json') as config_file:
    config = json.load(config_file)

os.system('clear')
print("Starting bot...")
print("")


def get_prefix(bot, msg):
    with open('prefixes.json') as prefix_file:
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


bot = commands.AutoShardedBot(command_prefix=get_prefix,
                              description="Frooty is designed for the FrootGaming Community " +
                                          "to support administrative features or help with some fun")

log = AsyncLogger('FrootGaming Bot', 'Bot', bot)
logger = logging.getLogger('discord')
logger.setLevel(logging.NOTSET)
handler = Logger('FrootGaming Bot', 'Discord', bot)
handler.setFormatter(logging.Formatter('%(levelname)s-%(name)s: %(message)s'))
logger.addHandler(handler)

chatbot = Chatbot.Handler(log)


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


class Chat(commands.Cog):
    __slots__ = 'bot'

    def __init__(self):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def list_batches(self, ctx):
        embed = discord.Embed(title="Conversation batches")
        for batch in chatbot.batches:
            embed.add_field(name="#" + str(chatbot.batches.index(batch)),
                            value=batch['messages'],
                            inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.is_owner()
    async def learn_batch(self, ctx, batch_id):
        chatbot.learn_batch(int(batch_id))
        await ctx.send(":ballot_box_with_check: **Batch learned.**")

    @commands.command()
    @commands.is_owner()
    async def remove_batch(self, ctx, batch_id):
        chatbot.remove_batch(int(batch_id))
        await ctx.send(":ballot_box_with_check: **Batch removed.**")

    @commands.command()
    @commands.is_owner()
    async def clear_data(self, ctx):
        chatbot.batches.clear()
        chatbot.cache.clear()
        await ctx.send(":ballot_box_with_check: **Batches and Cache cleared.**")


@bot.event
async def on_member_join(member):
    channel = bot.get_channel(589120991985139733)
    await channel.send(":confetti_ball: Welcome to the community, **" + str(member) + "**!")


@bot.event
async def on_message(message):
    response = chatbot.handle_message(message)
    if response is not None:
        msg = await message.channel.send("**[" + str(response.confidence) + "]** " + str(response))
        chatbot.cache[str(msg.id)] = [response, str(message.content)]
        await msg.add_reaction("👍")
        await asyncio.sleep(5)
        await msg.clear_reactions()

    ctx = await bot.get_context(message)
    if not ctx.valid:
        if "<@!{}>".format(bot.user.id) in message.content:
            with open("prefixes.json") as prefix_read:
                prefix_json = json.load(prefix_read)
            try:
                guild_prefix = prefix_json[str(bot.user.id)][str(ctx.guild.id)]
            except KeyError:
                guild_prefix = '!'
            embed = discord.Embed(title=bot.user.name, description=bot.description, color=0x4F8FF3)
            embed.add_field(name="Prefix", value="Use `{}` or <@{}> in this guild".format(guild_prefix, bot.user.id))
            embed.set_footer(text="Bot made by ParrotLync#2458")
            await ctx.send(embed=embed)
    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    if str(user) != str(bot.user):
        if str(reaction) == "👍" and str(reaction.message.author) == str(bot.user):
            chatbot.learn_response(reaction.message.id)


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
bot.add_cog(Chat())
try:
    bot.run(config['tokens']['FGBot'])
except RuntimeError:
    handler.warning('Closed before completing cleanup')
