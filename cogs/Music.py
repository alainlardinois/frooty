import discord
from discord.ext import commands
import asyncio
from async_timeout import timeout
from functools import partial
from youtube_dl import YoutubeDL
import time
from cogs.Logger import Logger, AsyncLogger
import json
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

ffmpeg_options = {
    'before_options': '-nostdin',
    'options': '-vn'}

with open('/app/config/config.json') as config_file:
    config = json.load(config_file)

client_id = config['spotify']['id']
client_secret = config['spotify']['secret']
client_credentials_manager = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)


def is_guild(ctx):
    if ctx.guild:
        return True
    else:
        raise commands.NoPrivateMessage


class YTDLSource(discord.PCMVolumeTransformer):
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
    async def create_source(cls, author, query: str, *, loop):
        loop = loop or asyncio.get_event_loop()
        execdir = partial(ytdl.extract_info, url=query, download=True)
        data = await loop.run_in_executor(None, execdir)

        if 'entries' in data:
            data = data['entries'][0]

        source = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(source), data=data, requester=author, query=query)


class Player:
    __slots__ = ('bot', 'guild', 'channel', 'cog', 'queue', 'text_queue', 'loop', 'next', 'current', 'last_started',
                 'volume')

    def __init__(self, ctx, bot):
        self.bot = bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog
        self.queue = asyncio.Queue()
        self.text_queue = []
        self.loop = False
        self.next = asyncio.Event()
        self.current = None
        self.volume = .5
        self.last_started = None
        ctx.bot.loop.create_task(self.player_loop())

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
                await log.exception(e)

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
        playlist = sp.user_playlist(playlist_id=playlist_id, user=None)
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
        return self.bot.loop.create_task(self.cog.cleanup(guild))


class Music(commands.Cog):
    __slots__ = ('bot', 'players', 'log')

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.log = log

    async def cleanup(self, guild):
        try:
            await guild.voice_client.disconnect()
        except Exception as e:
            await self.log.exception(str(e))

        try:
            del self.players[guild.id]
        except Exception as e:
            await self.log.exception(str(e))

    def get_player(self, ctx):
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = Player(ctx, self.bot)
            self.players[ctx.guild.id] = player
        return player

    @commands.command(aliases=['connect'])
    @commands.check(is_guild)
    async def join(self, ctx):
        """Connect the bot to your current voice channel"""
        if ctx.author.voice is None:
            await ctx.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')
        else:
            channel = ctx.author.voice.channel
            if ctx.voice_client is not None:
                return await ctx.voice_client.move_to(channel)
            player = self.get_player(ctx)
            await channel.connect()
            await ctx.send(':checkered_flag: **Connected to** `' + str(channel) + '` **and bound to** `#' +
                           str(player.channel) + '`')
            await self.log.info(str(ctx.author) + ' used command JOIN')

    @commands.command()
    @commands.check(is_guild)
    async def play(self, ctx, *, query: str):
        """Request a song and add it to the queue"""
        if ctx.author.voice is None:
            return await ctx.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')
        async with ctx.typing():
            await ctx.invoke(self.join)
            player = self.get_player(ctx)

            if 'spotify' in query and 'http' in query:
                try:
                    uri = query.strip('https://open.spotify.com/track/')
                    uri = uri.split('?')
                    uri = 'spotify:track:' + uri[0]
                    track_info = sp.track(uri)
                    query = track_info['name'] + ' ' + track_info['artists'][0]['name']
                except Exception as e:
                    await self.log.exception(str(e))
            elif 'spotify:track:' in query:
                track_info = sp.track(query)
                query = track_info['name'] + ' ' + track_info['artists'][0]['name']
            source = await player.add_to_queue(query, ctx.author)
            embed = discord.Embed(title=source.title,
                                  url=source.yt_url,
                                  color=0x00bfff)
            if source.thumbnail is None:
                embed.set_thumbnail(url='https://drive.ipictserver.nl/mp3.png')
            else:
                embed.set_thumbnail(url=source.thumbnail)
            embed.set_author(name="Added to queue", icon_url=ctx.author.avatar_url)
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
        await self.log.info(str(ctx.author) + ' used command PLAY', opts)
        await ctx.message.delete()

    @commands.command(aliases=['resume'])
    @commands.check(is_guild)
    async def pause(self, ctx):
        """Pause or resume the current song"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        if not ctx.voice_client.is_paused():
            ctx.voice_client.pause()
            await ctx.send(':play_pause: The music has been paused!')
        elif ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send(':play_pause: Rock on! The music is being resumed.')
        await self.log.info(str(ctx.author) + ' used command PAUSE')

    @commands.command(aliases=['s', 'next'])
    @commands.check(is_guild)
    async def skip(self, ctx, *, args=None):
        """Skip the current song"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif not ctx.voice_client.is_playing():
            return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))
        elif ctx.author.voice.channel.id != ctx.voice_client.channel.id:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        source = ctx.voice_client.source
        if str(ctx.author) == str(source.requester):
            ctx.voice_client.stop()
            await ctx.send(':fast_forward: **Skipping the current song!**')
        else:
            if str(ctx.author) not in source.skip_votes:
                source.skip_votes.append(str(ctx.author))
                await ctx.send(':ballot_box: `{}` **voted to skip this song**.'.format(ctx.author))
                members_in_channel = len(ctx.voice_client.channel.members) - 1
                members_voted_skip = len(source.skip_votes)
                if (members_voted_skip / members_in_channel) > 0.55:
                    ctx.voice_client.stop()
                    await ctx.send(':fast_forward: **The crowd has decided! Skipping the current song...**')
            else:
                await ctx.send(':negative_squared_cross_mark: **You already voted to skip this song.**')
        await self.log.info(str(ctx.author) + ' used command SKIP')

    @commands.command()
    @commands.check(is_guild)
    async def loop(self, ctx):
        """Play the queue in a loop"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        player = self.get_player(ctx)
        if player.loop:
            player.loop = False
            await ctx.send(":repeat_one: **Queue loop is now `disabled`**")
        else:
            player.loop = True
            await ctx.send(":repeat: **Queue loop is now `enabled`**")
        await self.log.info(str(ctx.author) + ' used command LOOP')

    @commands.command()
    @commands.check(is_guild)
    async def playlist(self, ctx, url):
        """Add a spotify playlist to the queue. Take the Spotify playlist URL"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        if "https://open.spotify.com/playlist/" in url:
            await ctx.message.delete()
            await ctx.send(":hourglass_flowing_sand: **Now processing your playlist. This may take a moment...**")
            player = self.get_player(ctx)
            data = await player.add_playlist(url, ctx.author)
            embed = discord.Embed(title=data['title'],
                                  url=data['url'],
                                  color=0x0be37f)
            embed.set_thumbnail(url=data['image'])
            embed.set_author(name="Playlist processed", icon_url=ctx.author.avatar_url)
            embed.set_footer(text="Playlist is now in the queue! You can view the next 5 songs with the queue command.")
            embed.add_field(name='# Songs', value=data['tracks'])
            embed.add_field(name="Playlist owner", value=data['owner'])
            await ctx.send(embed=embed)
        else:
            await ctx.send(":negative_squared_cross_mark: **Invalid format. Your URL should start with"
                           " `https://open.spotify.com/playlist/`**")

    @commands.command(name='queue', aliases=['q'])
    @commands.check(is_guild)
    async def queue_info(self, ctx):
        """View the queue"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send(':negative_squared_cross_mark: **The queue is empty!**')
        count = 0
        upcoming = ''
        while count < 5 and count < len(player.text_queue):
            count += 1
            upcoming += '**' + str(count) + '. **' + player.text_queue[count - 1] + '\n'
        embed = discord.Embed(title='Queue - next {} songs'.format(count),
                              description=upcoming, color=0x32cd32)
        embed.set_footer(text="Total queue length: {} songs • Queue loop: {}".format(len(player.text_queue),
                                                                                     player.loop))
        await ctx.send(embed=embed)
        await self.log.info(str(ctx.author) + ' used command QUEUE')

    @commands.command()
    @commands.check(is_guild)
    async def now(self, ctx):
        """Check which song is currently playing"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif not ctx.voice_client.is_playing():
            return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))

        source = ctx.voice_client.source
        player = self.get_player(ctx)
        embed = discord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
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
        await self.log.info(str(ctx.author) + ' used command NOW')

    @commands.command(aliases=['rm'])
    @commands.check(is_guild)
    async def remove(self, ctx, queue_number: int):
        """Remove a song from the queue"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))
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
        await self.log.info(str(ctx.author) + ' used command REMOVE')

    @commands.command(aliases=['vol'])
    @commands.check(is_guild)
    async def volume(self, ctx, *, vol: float):
        """Change the volume"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')
        elif not ctx.voice_client.is_playing():
            return await ctx.send(':negative_squared_cross_mark: **Not playing any music right now.**')
        elif ctx.author.voice is None:
            return await ctx.send(
                ':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(
                    ctx.voice_client.channel))
        if not 0 < vol <= 100:
            return await ctx.send(':negative_squared_cross_mark: **Please enter a value between 1 and 100**')

        player = self.get_player(ctx)
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = vol / 100
        player.volume = vol / 100
        await ctx.send(":loud_sound: Changed volume to **{}%**".format(vol))
        await self.log.info(str(ctx.author) + ' used command VOLUME')

    @commands.command(aliases=['leave'])
    @commands.check(is_guild)
    async def stop(self, ctx):
        """Stop the music and leave the channel"""
        if not ctx.voice_client:
            return await ctx.send(':negative_squared_cross_mark: **Not connected to a voice channel.**')

        await self.cleanup(ctx.guild)
        await self.log.info(str(ctx.author) + ' used command STOP')
        await ctx.message.delete()

    @commands.command()
    async def download(self, ctx, *, query: str):
        """Download a song in discord"""
        async with ctx.typing():
            source = await YTDLSource.create_source(ctx.author, query, loop=self.bot.loop)
            path = '/var/www/html/temp/' + str(source.id) + '.' + str(source.ext)
            with open(path, 'rb') as file:
                await ctx.send(file=discord.File(file, filename=source.title + '.' + source.ext))
        opts = {
            'meta': {
                'guild': str(ctx.guild),
                'search_url': query,
                'title': str(source.title),
                'origin_url': str(source.yt_url),
                'url': str(source.url),
                'file': str(source.id) + '.' + str(source.ext)}}
        await self.log.info(str(ctx.author) + ' used command DOWNLOAD', opts)
        await ctx.message.delete()

    @commands.command()
    async def link(self, ctx, *, query: str):
        """Download a song to our web server"""
        async with ctx.typing():
            source = await YTDLSource.create_source(ctx.author, query, loop=self.bot.loop)
            embed = discord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
            if source.thumbnail is None:
                embed.set_thumbnail(url='https://drive.ipictserver.nl/frootcraft/mp3.png')
            else:
                embed.set_thumbnail(url=source.thumbnail)
            embed.set_author(name="Youtube to link", icon_url=ctx.author.avatar_url)
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
        await self.log.info(str(ctx.author) + ' used command LINK', opts)
        await ctx.message.delete()


def setup(bot):
    global ytdl, log
    log = AsyncLogger(str(bot.user.name), 'Music', bot)

    ytdl_options = {
        'format': 'bestaudio/best',
        'outtmpl': '/var/www/html/temp/%(id)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': False,
        'logger': Logger(str(bot.user.name), 'YTDL', bot),
        'no_warnings': True,
        'noprogress': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0'
    }

    ytdl = YoutubeDL(ytdl_options)
    bot.add_cog(Music(bot))
