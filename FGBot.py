import logging

import nextcord
from nextcord.ext import commands
import os

startup_extensions = ["cogs.CommandErrorHandler", "cogs.Extensions", "cogs.Music"]

print("Starting bot...")
print("")


# logger = logging.getLogger('nextcord')
# logger.setLevel(logging.DEBUG)
# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
# logger.addHandler(handler)


def is_guild(ctx):
    if ctx.guild:
        return True
    else:
        raise commands.NoPrivateMessage


bot = commands.Bot()


@bot.event
async def on_ready():
    print("\n## Logged in as", bot.user.name)
    print("## ID:", bot.user.id)
    print('')
    if __name__ == "__main__":
        for extension in startup_extensions:
            try:
                bot.load_extension(extension)
                print("Loaded extension {}".format(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                print('Failed to load extension {}\n{}'.format(extension, exc))


try:
    bot.run(os.getenv("BOT_TOKEN"))
except RuntimeError:
    print('Closed before completing cleanup')
