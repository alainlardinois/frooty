import nextcord
from nextcord.ext import commands


class Extensions(commands.Cog):
    """Extension commands"""

    def __init__(self, bot):
        self.bot = bot

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.is_owner()
    async def reload(self, ctx, *, extension):
        """Reload an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = nextcord.Embed(description="**Reloading extension** " + extension, color=0x0066cc)
            await ctx.send(embed=embed)
            try:
                self.bot.reload_extension(extension)
                print('Reloaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to reload extension {}\n{}'.format(extension, exc))
                print('Failed to reload extension {}\n{}'.format(extension, exc))

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.is_owner()
    async def load(self, ctx, *, extension):
        """Load an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = nextcord.Embed(description="**Loading extension** " + extension, color=0x33cc33)
            await ctx.send(embed=embed)
            try:
                self.bot.load_extension(extension)
                print('Loaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to load extension {}\n{}'.format(extension, exc))
                print('Failed to reload extension {}\n{}'.format(extension, exc))

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.is_owner()
    async def unload(self, ctx, *, extension):
        """Unload an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = nextcord.Embed(description="**Unloading extension** " + extension, color=0xff3300)
            await ctx.send(embed=embed)
            try:
                self.bot.unload_extension(extension)
                print('Unloaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to unload extension {}\n{}'.format(extension, exc))
                print('Failed to reload extension {}\n{}'.format(extension, exc))


def setup(bot):
    bot.add_cog(Extensions(bot))
