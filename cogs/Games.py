import json

import discord
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from igdb.wrapper import IGDBWrapper

with open('/app/config/config.json') as config_file:
    config = json.load(config_file)
wrapper = IGDBWrapper(config['igdb']['client_id'], config['igdb']['access_token'])


def remove_member_from_embed(embed: discord.Embed, member: discord.Member):
    new_value_0 = get_new_value(embed, 0, member)
    embed.set_field_at(0, name='Doet mee', value=new_value_0)
    new_value_1 = get_new_value(embed, 1, member)
    embed.set_field_at(1, name='Doet niet mee', value=new_value_1)
    new_value_2 = get_new_value(embed, 2, member)
    embed.set_field_at(2, name='Weet het nog niet', value=new_value_2)
    return embed


def get_new_value(embed: discord.Embed, index: int, member: discord.Member):
    new_value = embed.fields[index].value.replace(member.display_name, '')
    if new_value != "":
        return new_value
    else:
        return "-"


class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @cog_ext.cog_slash(name="wdem", description="Ask people to play a game with you", guild_ids=[455481676542377995])
    async def wdem(self, ctx: SlashContext, game = None):
        if game is None and ctx.channel.topic is None:
            return await ctx.send(":negative_squared_cross_mark: **No games were found!**", hidden=True)

        if game is None:
            game = ctx.channel.topic

        message = await ctx.send(":gear: *Finding your game...*")

        try:
            byte_array = wrapper.api_request('games', 'search "{}"; fields name, cover.image_id;'.format(game))
            result = json.loads(byte_array)[0]

            embed = discord.Embed(title="Wie doet er mee met `{}`?".format(result['name']),
                                  description="\n✅ `Ik doe mee!` \n❎ `Ik doe niet mee.` \n❓ `Ik weet het nog niet.`",
                                  color=0x477FC9)
            embed.set_thumbnail(url="https://images.igdb.com/igdb/image/upload/t_cover_big/{}.jpg"
                                .format(result['cover']['image_id']))
            embed.add_field(name="Doet mee", value=ctx.author.display_name)
            embed.add_field(name="Doet niet mee", value="-")
            embed.add_field(name="Weet het nog niet", value="-")

            embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
            await message.edit(embed=embed, content="")
            await message.add_reaction("✅")
            await message.add_reaction("❎")
            await message.add_reaction("❓")
        except IndexError:
            return await ctx.send(":negative_squared_cross_mark: **No games were found!**", hidden=True)

    @cog_ext.cog_slash(name="wdone", description="Mark a previous game poll as done", guild_ids=[455481676542377995])
    async def wdone(self, ctx: SlashContext, message_id: int = 0):
        message = None
        if message_id == 0:
            messages = await ctx.channel.history(limit=30).flatten()
            for msg_looped in messages:
                if self.is_active_game_poll(msg_looped):
                    message = msg_looped
                    break
        else:
            message = await self.bot.fetch_channel(message)

        if message is None:
            return await ctx.send(":negative_squared_cross_mark: **No valid polls found!**")

        await ctx.send(":white_check_mark: **Game Poll marked as done!** `({})`".format(message.id))
        await message.clear_reactions()
        await message.add_reaction("👍")
        await message.add_reaction("🇩")
        await message.add_reaction("🇴")
        await message.add_reaction("🇳")
        await message.add_reaction("🇪")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        message: discord.Message = await (await self.bot.fetch_channel(payload.channel_id)).fetch_message(payload.message_id)
        user: discord.User = await self.bot.fetch_user(payload.user_id)
        emoji: discord.Emoji = payload.emoji

        if user.id == self.bot.user.id:
            return

        if self.is_active_game_poll(message):
            await message.remove_reaction(emoji=emoji, member=payload.member)
            embed: discord.Embed = message.embeds[0]
            if emoji.name == '✅':
                if payload.member.display_name not in embed.fields[0].value:
                    remove_member_from_embed(embed, payload.member)
                    new_value = embed.fields[0].value + '\n' + payload.member.display_name
                    embed.set_field_at(0, name='Doet mee', value=new_value.replace("-", ""))
                    await message.edit(embed=embed)
            elif emoji.name == '❎':
                if payload.member.display_name not in embed.fields[1].value:
                    remove_member_from_embed(embed, payload.member)
                    new_value = embed.fields[1].value + '\n' + payload.member.display_name
                    embed.set_field_at(1, name='Doet niet mee', value=new_value.replace("-", ""))
                    await message.edit(embed=embed)
            elif emoji.name == '❓':
                if payload.member.display_name not in embed.fields[2].value:
                    remove_member_from_embed(embed, payload.member)
                    new_value = embed.fields[2].value + '\n' + payload.member.display_name
                    embed.set_field_at(2, name='Weet het nog niet', value=new_value.replace("-", ""))
                    await message.edit(embed=embed)

    def is_active_game_poll(self, message: discord.Message):
        if message.author.id != self.bot.user.id:
            return False

        if message.embeds is None or len(message.embeds) == 0:
            return False

        embed: discord.Embed = message.embeds[0]
        if 'Wie doet er mee' not in embed.title:
            return False

        for reaction in message.reactions:
            if reaction.emoji == '👍':
                return False

        return True


def setup(bot):
    bot.add_cog(Games(bot))
