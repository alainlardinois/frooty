import logging

import nextcord
from nextcord.ext import commands
import os

import asyncio
import time
import os
import hashlib
from functools import partial

import nextcord
import spotipy
from async_timeout import timeout
from nextcord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials
from yt_dlp import YoutubeDL
from gtts import gTTS

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

ffmpeg_options = {
    'before_options': '-nostdin',
    'options': '-vn'}

client_credentials_manager = SpotifyClientCredentials(client_id=os.getenv("SPOTIFY_CLIENT_ID"), client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"))
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)


def is_guild(ctx):
    if ctx.guild:
        return True
    else:
        raise commands.NoPrivateMessage


class YTDLSource(nextcord.PCMVolumeTransformer):
    __slots__ = ('data', 'title', 'url', 'thumbnail', 'uploader', 'duration', 'yt_url', 'requester', 'skip_votes',
                 'id', 'ext', 'query')

    def __init__(self, source, *, data, requester, query):
        super().__init__(source)
        self.data = data
        self.title = self.data.get('title')
        self.url = self.data.get('url')
        self.thumbnail = self.data.get('thumbnail')
        self.uploader = self.data.get('uploader')
        self.duration = time.strftime('%H:%M:%S', time.gmtime(data.get('duration')))
        self.yt_url = self.data.get('webpage_url')
        self.requester = requester
        self.skip_votes = []
        self.id = self.data.get('id')
        self.ext = self.data.get('ext')
        self.query = query

    @classmethod
    async def create_source(cls, user, query: str, *, loop):
        loop = loop or asyncio.get_event_loop()
        execdir = partial(ytdl.extract_info, url=query, download=True)
        data = await loop.run_in_executor(None, execdir)

        if 'entries' in data:
            data = data['entries'][0]

        source = ytdl.prepare_filename(data)
        return cls(nextcord.FFmpegPCMAudio(source), data=data, requester=user, query=query)


class Player:
    __slots__ = ('bot', 'guild', 'channel', 'cog', 'queue', 'text_queue', 'loop', 'next', 'current', 'last_started',
                 'volume')

    def __init__(self, ctx, bot):
        self.bot = bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.queue = asyncio.Queue()
        self.text_queue = []
        self.loop = False
        self.next = asyncio.Event()
        self.current = None
        self.volume = .5
        self.last_started = None
        bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        while not self.bot.is_closed():
            self.next.clear()

            try:
                async with timeout(300):
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                return self.destroy(self.guild)

            source.volume = self.volume
            self.current = source

            try:
                self.text_queue.remove(source.title)
            except Exception as e:
                print(e)

            if self.guild.voice_client is not None:
                self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            else:
                self.channel.connect()
                self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))

            self.last_started = time.time()
            await self.channel.send(':headphones: **Now playing:** `{}`'.format(source.title))
            await self.next.wait()
            if self.loop:
                await self.add_to_queue(source.query, source.requester)
            source.cleanup()
            self.current = None

    async def add_playlist(self, url, requester):
        url = url.strip('https://open.spotify.com/playlist/')
        url = url.split('?')
        playlist_id = url[0]
        playlist = sp.playlist(playlist_id=playlist_id)
        for item in playlist['tracks']['items']:
            track = item['track']
            query = track['name'] + ' ' + track['artists'][0]['name']
            await self.add_to_queue(query, requester)
        return {'title': playlist['name'],
                'image': playlist['images'][0]['url'],
                'url': playlist['external_urls']['spotify'],
                'tracks': len(playlist['tracks']['items']),
                'owner': playlist['owner']['display_name']}

    async def add_to_queue(self, query, requester):
        new_source = await YTDLSource.create_source(requester, query, loop=self.bot.loop)
        await self.queue.put(new_source)
        self.text_queue.append(new_source.title)
        return new_source

    def destroy(self, guild):
        pass
        # return self.bot.loop.create_task(self.cog.cleanup(guild))


class Music(commands.Cog):
    __slots__ = ('bot', 'players')

    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except Exception as e:
            print(str(e))

        try:
            del self.players[guild.id]
        except Exception as e:
            print(str(e))

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = Player(ctx, self.bot)
            self.players[ctx.guild.id] = player
        return player

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def join(self, ctx):
        """Connect the bot to your current voice channel"""
        if ctx.user.voice.channel is None:
            await ctx.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')
        else:
            channel = ctx.user.voice.channel
            if ctx.user.voice.channel is not None:
                return await ctx.user.voice.channel.connect()
            player = self.get_player(ctx)
            await channel.connect()
            await ctx.send(':checkered_flag: **Connected to** `' + str(channel) + '` **and bound to** `#' +
                           str(player.channel) + '`')

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def play(self, ctx, *, query: str):
        """Request a song and add it to the queue"""
        if ctx.user.voice.channel is None:
            return await ctx.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')

        # await ctx.invoke(self.join)
        player = self.get_player(ctx)

        if 'spotify' in query and 'http' in query:
            try:
                uri = query.strip('https://open.spotify.com/track/')
                uri = uri.split('?')
                uri = 'spotify:track:' + uri[0]
                track_info = sp.track(uri)
                query = track_info['name'] + ' ' + track_info['artists'][0]['name']
            except Exception as e:
                print(str(e))
        elif 'spotify:track:' in query:
            track_info = sp.track(query)
            query = track_info['name'] + ' ' + track_info['artists'][0]['name']
        source = await player.add_to_queue(query, ctx.user)
        embed = nextcord.Embed(title=source.title,
                               url=source.yt_url,
                               color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Added to queue", icon_url=ctx.user.avatar_url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        await ctx.send(embed=embed)

        opts = {
            'meta': {
                'guild': str(ctx.guild),
                'search_url': query,
                'title': str(source.title),
                'origin_url': str(source.yt_url),
                'url': str(source.url),
                'file': str(source.id) + '.' + str(source.ext)}}
        await ctx.message.delete()

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def pause(self, ctx):
        """Pause or resume the current song"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        if not ctx.user.voice.channel.is_paused():
            ctx.user.voice.channel.pause()
            await ctx.send(':play_pause: The music has been paused!')
        elif ctx.user.voice.channel.is_paused():
            ctx.user.voice.channel.resume()
            await ctx.send(':play_pause: Rock on! The music is being resumed.')

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.is_owner()
    async def forceskip(self, ctx):
        """Force skip the current song"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        # elif not ctx.user.voice.channel.is_playing():
        #     return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))
        elif ctx.user.voice.channel.id != ctx.user.voice.channel.id:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        source = ctx.user.voice.channel.source
        ctx.user.voice.channel.stop()
        await ctx.send(':fast_forward: **Skipping the current song!**')

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def skip(self, ctx):
        """Skip the current song"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        # elif not ctx.user.voice.channel.is_playing():
        #     return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))
        elif ctx.user.voice.channel.id != ctx.user.voice.channel.id:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        source = ctx.user.voice.channel.source
        if str(ctx.user) == str(source.requester):
            ctx.user.voice.channel.stop()
            await ctx.send(':fast_forward: **Skipping the current song!**')
        else:
            if str(ctx.user) not in source.skip_votes:
                source.skip_votes.append(str(ctx.user))
                await ctx.send(':ballot_box: `{}` **voted to skip this song**.'.format(ctx.user))
                users_in_channel = len(ctx.user.voice.channel.users) - 1
                users_voted_skip = len(source.skip_votes)
                if (users_voted_skip / users_in_channel) > 0.55:
                    ctx.user.voice.channel.stop()
                    await ctx.send(':fast_forward: **The crowd has decided! Skipping the current song...**')
            else:
                await ctx.send(':negative_squared_cross_mark: **You already voted to skip this song.**')

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def loop(self, ctx):
        """Play the queue in a loop"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        player = self.get_player(ctx)
        if player.loop:
            player.loop = False
            await ctx.send(":repeat_one: **Queue loop is now `disabled`**")
        else:
            player.loop = True
            await ctx.send(":repeat: **Queue loop is now `enabled`**")

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def playlist(self, ctx, url):
        """Add a spotify playlist to the queue. Take the Spotify playlist URL"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        if "https://open.spotify.com/playlist/" in url:
            await ctx.send(":hourglass_flowing_sand: **Now processing your playlist. This may take a moment...**")
            player = self.get_player(ctx)
            data = await player.add_playlist(url, ctx.user)
            embed = nextcord.Embed(title=data['title'],
                                  url=data['url'],
                                  color=0x0be37f)
            embed.set_thumbnail(url=data['image'])
            embed.set_author(name="Playlist processed", icon_url=ctx.user.avatar_url)
            embed.set_footer(text="Playlist is now in the queue! You can view the next 5 songs with the queue command.")
            embed.add_field(name='# Songs', value=data['tracks'])
            embed.add_field(name="Playlist owner", value=data['owner'])
            await ctx.send(embed=embed)
        else:
            await ctx.send(":negative_squared_cross_mark: **Invalid format. Your URL should start with"
                           " `https://open.spotify.com/playlist/`**")

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def queue(self, ctx):
        """View the queue"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send(':negative_squared_cross_mark: **The queue is empty!**')
        count = 0
        chars = 0
        upcoming = ''
        while count < len(player.text_queue) and chars < 1900:
            count += 1
            chars += len(str(count)) + 8 + len(player.text_queue[count - 1])
            upcoming += '**' + str(count) + '. **' + player.text_queue[count - 1] + '\n'
        embed = nextcord.Embed(title='Queue - next {} songs'.format(count),
                              description=upcoming, color=0x32cd32)
        embed.set_footer(text="Total queue length: {} songs • Queue loop: {}".format(len(player.text_queue),
                                                                                     player.loop))
        await ctx.send(embed=embed)

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def now(self, ctx):
        """Check which song is currently playing"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        # elif not ctx.user.voice.channel.is_playing():
        #     return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))

        source = ctx.user.voice.channel.source
        player = self.get_player(ctx)
        embed = nextcord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Now playing", icon_url=source.requester.avatar_url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        elapsed = time.time() - player.last_started
        hours = int(elapsed // 3600)
        minutes = int((elapsed // 60) % 60)
        seconds = int(elapsed % 60)
        elapsed_time = "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)
        embed.add_field(name='Elapsed Time', value=elapsed_time)
        await ctx.send(embed=embed)

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def remove(self, ctx, queue_number: int):
        """Remove a song from the queue"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))
        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send(':negative_squared_cross_mark: **The queue is empty!**')

        songs = len(player.text_queue)
        if 0 < queue_number <= songs:
            new_queue = asyncio.Queue()
            new_text_queue = []
            source_name = player.text_queue[queue_number - 1]
            while not player.queue.empty():
                source = await player.queue.get()
                if source.title != source_name:
                    await new_queue.put(source)
                    new_text_queue.append(source.title)
            player.queue = new_queue
            player.text_queue = new_text_queue
            await ctx.send(":white_check_mark: Removed `" + source_name + "` from the queue")
        else:
            return await ctx.send(':negative_squared_cross_mark: **Please enter a value between 1 and ' +
                                  str(songs) + '**')

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def volume(self, ctx, *, vol: float):
        """Change the volume"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        # elif not ctx.user.voice.channel.is_playing():
        #     return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.user.voice.channel is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.user.voice.channel))
        if not 0 < vol <= 100:
            return await ctx.send(':negative_squared_cross_mark: **Please enter a value between 1 and 100**')

        player = self.get_player(ctx)
        if ctx.user.voice.channel.source:
            ctx.user.voice.channel.source.volume = vol / 100
        player.volume = vol / 100
        await ctx.send(":loud_sound: Changed volume to **{}%**".format(vol))

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def stop(self, ctx):
        """Stop the music and leave the channel"""
        if not ctx.user.voice.channel:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')

        await self.cleanup(ctx.guild)
        await ctx.message.delete()

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    async def download(self, ctx, *, query: str):
        """Download a song in nextcord"""
        source = await YTDLSource.create_source(ctx.user, query, loop=self.bot.loop)
        path = '/var/www/html/temp/' + str(source.id) + '.' + str(source.ext)
        with open(path, 'rb') as file:
            await ctx.send(file=nextcord.File(file, filename=source.title + '.' + source.ext))

        opts = {
            'meta': {
                'guild': str(ctx.guild),
                'search_url': query,
                'title': str(source.title),
                'origin_url': str(source.yt_url),
                'url': str(source.url),
                'file': str(source.id) + '.' + str(source.ext)}}

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    async def link(self, ctx, *, query: str):
        """Download a song to our web server"""
        source = await YTDLSource.create_source(ctx.user, query, loop=self.bot.loop)
        embed = nextcord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/frootcraft/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Youtube to link", icon_url=ctx.user.avatar_url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        link = "http://drive.ipictserver.nl/temp/" + source.id + '.' + source.ext
        embed.add_field(name='Link', value=link)
        await ctx.send(embed=embed)

        opts = {
            'meta': {
                'guild': str(ctx.guild),
                'search_url': query,
                'title': str(source.title),
                'origin_url': str(source.yt_url),
                'url': str(source.url),
                'file': str(source.id) + '.' + str(source.ext)}}

    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    @commands.check(is_guild)
    async def playtts(self, ctx, *, message: str):
        """Play a tts message in a voice call"""
        if ctx.user.voice.channel is None:
            return await ctx.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')

        filename = 'tts-{}.mp3'.format(hashlib.md5(message.encode()).hexdigest())
        path = "/var/www/html/temp/{}".format(filename)
        if not os.path.isfile(path):
            tts = gTTS(message, lang='nl')
            tts.save(path)

        await ctx.invoke(self.join)
        player = self.get_player(ctx)
        source = await player.add_to_queue("https://drive.ipictserver.nl/temp/{}".format(filename), ctx.user)
        embed = nextcord.Embed(title="Voice TTS Message",
                               url=source.yt_url,
                               color=0x00bfff)
        embed.set_thumbnail(url='https://cdn-icons-png.flaticon.com/512/5256/5256064.png')
        embed.set_author(name="Added to queue", icon_url=ctx.user.avatar_url)
        if len(message) > 1000:
            embed.add_field(name='Message', value=message[:1000] + "...")
        else:
            embed.add_field(name='Message', value=message)
        await ctx.message.delete()
        await ctx.send(embed=embed)


    @nextcord.slash_command(guild_ids=[484345041935138816, 1059214747406434455])
    async def tts(self, ctx, *, message: str):
        """Generate a tts message and get the link"""
        filename = 'tts-{}.mp3'.format(hashlib.md5(message.encode()).hexdigest())
        path = "/var/www/html/temp/{}".format(filename)
        if not os.path.isfile(path):
            tts = gTTS(message, lang='nl')
            tts.save(path)
        with open(path, 'rb') as file:
            await ctx.send(file=nextcord.File(file, filename=filename))


ytdl_options = {
        'format': 'bestaudio/best',
        'outtmpl': '/var/www/html/temp/%(id)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': False,
        'no_warnings': True,
        'noprogress': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0'
    }

ytdl = YoutubeDL(ytdl_options)
bot.add_cog(Music(bot))


try:
    bot.run(os.getenv("BOT_TOKEN"))
except RuntimeError:
    print('Closed before completing cleanup')
