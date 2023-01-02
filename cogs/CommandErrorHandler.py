import nextcord
from nextcord.ext import commands

from cogs.Music import VoiceNotConnectedException


class CommandErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if hasattr(ctx.command, 'on_error'):
            return

        error = getattr(error, 'original', error)
        instance = error.__class__.__name__
        opts = {'meta': {'user': str(ctx.author), 'guild': str(ctx.guild)}}

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(":offline: `This command is currently disabled.`")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send(":no_entry: `This command can't be used in private messaging.`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(":warning: `Something is wrong with that command. Please try again.`")
            print("{} [{}]".format(error, instance), opts)
        elif isinstance(error, nextcord.errors.HTTPException):
            await ctx.send(str(error))
            print(error)
        elif isinstance(error, commands.MissingRole):
            await ctx.send(":no_entry: `{}`".format(error))
        elif isinstance(error, commands.NotOwner):
            await ctx.send(":no_entry: `You do not have permission to do this!`")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(":warning: `{}`".format(error))
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send(":warning: `{}`".format(error))
        else:
            await ctx.send("DEBUG `{} [{}]`".format(error, instance))
            print("{} [{}]".format(error, instance), opts)


def setup(bot):
    bot.add_cog(CommandErrorHandler(bot))
