import discord
from discord.ext import commands
from Logger import AsyncLogger


class Extensions(commands.Cog):
    """Extension commands"""
    __slots__ = ('bot', 'log')

    def __init__(self, bot, log):
        self.bot = bot
        self.log = log

    @commands.command(hidden=True)
    @commands.is_owner()
    async def reload(self, ctx, *, extension):
        """Reload an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = discord.Embed(description="**Reloading extension** " + extension, color=0x0066cc)
            await ctx.send(embed=embed)
            try:
                self.bot.reload_extension(extension)
                await self.log.info('Reloaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to reload extension {}\n{}'.format(extension, exc))
                await self.log.exception('Failed to reload extension {}\n{}'.format(extension, exc))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def load(self, ctx, *, extension):
        """Load an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = discord.Embed(description="**Loading extension** " + extension, color=0x33cc33)
            await ctx.send(embed=embed)
            try:
                self.bot.load_extension(extension)
                await self.log.info('Loaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to load extension {}\n{}'.format(extension, exc))
                await self.log.exception('Failed to reload extension {}\n{}'.format(extension, exc))

    @commands.command(hidden=True)
    @commands.is_owner()
    async def unload(self, ctx, *, extension):
        """Unload an extension"""
        await ctx.message.delete()
        async with ctx.typing():
            embed = discord.Embed(description="**Unloading extension** " + extension, color=0xff3300)
            await ctx.send(embed=embed)
            try:
                self.bot.unload_extension(extension)
                await self.log.info('Unloaded extension ' + str(extension))
            except Exception as e:
                exc = '{}: {}'.format(type(e).__name__, e)
                await ctx.send('Failed to unload extension {}\n{}'.format(extension, exc))
                await self.log.exception('Failed to reload extension {}\n{}'.format(extension, exc))


def setup(bot):
    log = AsyncLogger(str(bot.user.name), 'Extensions', bot)
    bot.add_cog(Extensions(bot, log))
