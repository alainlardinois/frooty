import os
from nextcord.ext import commands
from cogs.Music import Music

print("Starting bot...")
print("")

bot = commands.Bot()
bot.add_cog(Music(bot))


@bot.event
async def on_ready():
    print("\n## Logged in as", bot.user.name)
    print("## ID:", bot.user.id)
    print('')

try:
    bot.run(os.getenv("BOT_TOKEN"))
except RuntimeError:
    print('Closed before completing cleanup')
