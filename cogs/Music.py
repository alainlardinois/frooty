import asyncio
import hashlib
import time
import os
from functools import partial

import nextcord
import spotipy
from async_timeout import timeout
from gtts import gTTS
from nextcord import Interaction
from nextcord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp as youtube_dl

ffmpeg_options = {"options": "-vn"}
youtube_dl.utils.bug_reports_message = lambda: ""
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

client_credentials_manager = SpotifyClientCredentials(client_id=os.getenv("SPOTIFY_CLIENT_ID"), client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"))
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)


class ResultNotFoundException(Exception):
    pass


class YTDLSource(nextcord.PCMVolumeTransformer):
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

        if data is None:
            raise ResultNotFoundException

        source = ytdl.prepare_filename(data)
        return cls(nextcord.FFmpegPCMAudio(source), data=data, requester=user, query=query)


class Player:
    def __init__(self, interaction: Interaction, bot, cog):
        self.bot = bot
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.cog = cog
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
        return self.bot.loop.create_task(self.cog.cleanup(guild))


class VoiceNotConnectedException(Exception):
    pass


class Music(commands.Cog):
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

    def get_player(self, interaction: Interaction):
        try:
            player = self.players[interaction.guild.id]
        except KeyError:
            player = Player(interaction, self.bot, self)
            self.players[interaction.guild.id] = player
        return player

    def is_voice_connected(self):
        return len(self.bot.voice_clients) > 0

    def get_voice_client(self):
        return self.bot.voice_clients[0]

    async def ensure_voice(self, interaction: Interaction):
        if self.is_voice_connected():
            return
        if interaction.user.voice is not None:
            await interaction.user.voice.channel.connect()
        else:
            raise VoiceNotConnectedException

    @nextcord.slash_command(force_global=True)
    async def join(self, interaction: Interaction):
        """Connect the bot to your current voice channel"""
        if interaction.user.voice.channel is None:
            return await interaction.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')

        channel = interaction.user.voice.channel
        if interaction.user.voice is not None:
            return await interaction.user.voice.channel.move(channel)
        player = self.get_player(interaction)
        await channel.connect()
        await interaction.send(':checkered_flag: **Connected to** `' + str(channel) + '` **and bound to** `#' + str(player.channel) + '`')

    @nextcord.slash_command(force_global=True)
    async def play(self, interaction: Interaction, *, query):
        """Request a song and add it to the queue"""
        if interaction.user.voice.channel is None:
            return await interaction.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')

        await interaction.response.defer()
        await self.ensure_voice(interaction)
        player = self.get_player(interaction)

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

        try:
            source = await player.add_to_queue(query, interaction.user)
        except ResultNotFoundException:
            return await interaction.send(":search: Failed to find a suitable result!")

        embed = nextcord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Added to queue", icon_url=interaction.user.avatar.url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        await interaction.send(embed=embed)

    @nextcord.slash_command(force_global=True)
    async def pause(self, interaction: Interaction):
        """Pause or resume the current song"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)

        if not voice.is_paused():
            voice.pause()
            await interaction.send(':play_pause: The music has been paused!')
        elif voice.is_paused():
            voice.resume()
            await interaction.send(':play_pause: Rock on! The music is being resumed.')

    @nextcord.slash_command(force_global=True)
    async def skip(self, interaction: Interaction):
        """Skip the current song"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)
        elif not voice.is_playing():
            return await interaction.send(':negative_squared_cross_mark: **Not playing any music right now.**', ephemeral=True)
        elif interaction.user.voice.channel.id != voice.channel.id:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)

        source = voice.source
        if str(interaction.user) == str(source.requester):
            voice.stop()
            await interaction.send(':fast_forward: **Skipping the current song!**')
        else:
            if str(interaction.user) not in source.skip_votes:
                source.skip_votes.append(str(interaction.user))
                await interaction.send(':ballot_box: `{}` **voted to skip this song**.'.format(interaction.user))
                members_in_channel = len(voice.channel.members) - 1
                members_voted_skip = len(source.skip_votes)
                if (members_voted_skip / members_in_channel) > 0.55:
                    voice.stop()
                    await interaction.send(':fast_forward: **The crowd has decided! Skipping the current song...**')
            else:
                await interaction.send(':negative_squared_cross_mark: **You already voted to skip this song.**', ephemeral=True)

    @nextcord.slash_command(force_global=True)
    async def loop(self, interaction: Interaction):
        """Play the queue in a loop"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)

        player = self.get_player(interaction)
        if player.loop:
            player.loop = False
            await interaction.send(":repeat_one: **Queue loop is now `disabled`**")
        else:
            player.loop = True
            await interaction.send(":repeat: **Queue loop is now `enabled`**")

    @nextcord.slash_command(force_global=True)
    async def queue(self, interaction: Interaction):
        """View the queue"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)

        await interaction.response.defer()
        player = self.get_player(interaction)
        if player.queue.empty():
            return await interaction.send(':negative_squared_cross_mark: **The queue is empty!**')
        count = 0
        chars = 0
        upcoming = ''
        while count < len(player.text_queue) and chars < 1900:
            count += 1
            chars += len(str(count)) + 8 + len(player.text_queue[count - 1])
            upcoming += '**' + str(count) + '. **' + player.text_queue[count - 1] + '\n'
        embed = nextcord.Embed(title='Queue - next {} songs'.format(count), description=upcoming, color=0x32cd32)
        embed.set_footer(text="Total queue length: {} songs • Queue loop: {}".format(len(player.text_queue), player.loop))
        await interaction.send(embed=embed)

    @nextcord.slash_command(force_global=True)
    async def now(self, interaction: Interaction):
        """Check which song is currently playing"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)
        elif not voice.is_playing():
            return await interaction.send(':negative_squared_cross_mark: **Not playing any music right now.**', ephemeral=True)

        source = voice.source
        player = self.get_player(interaction)
        embed = nextcord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Now playing", icon_url=source.requester.avatar.url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        elapsed = time.time() - player.last_started
        hours = int(elapsed // 3600)
        minutes = int((elapsed // 60) % 60)
        seconds = int(elapsed % 60)
        elapsed_time = "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)
        embed.add_field(name='Elapsed Time', value=elapsed_time)
        await interaction.send(embed=embed)

    @nextcord.slash_command(force_global=True)
    async def remove(self, interaction: Interaction, index: int):
        """Remove a song from the queue"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)
        player = self.get_player(interaction)
        if player.queue.empty():
            return await interaction.send(':negative_squared_cross_mark: **The queue is empty!**', ephemeral=True)

        songs = len(player.text_queue)
        if 0 < index <= songs:
            new_queue = asyncio.Queue()
            new_text_queue = []
            source_name = player.text_queue[index - 1]
            while not player.queue.empty():
                source = await player.queue.get()
                if source.title != source_name:
                    await new_queue.put(source)
                    new_text_queue.append(source.title)
            player.queue = new_queue
            player.text_queue = new_text_queue
            await interaction.send(":white_check_mark: Removed `" + source_name + "` from the queue")
        else:
            return await interaction.send(':negative_squared_cross_mark: **Please enter a value between 1 and ' + str(songs) + '**', ephemeral=True)

    @nextcord.slash_command(force_global=True)
    async def volume(self, interaction: Interaction, *, volume: float):
        """Change the volume"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        voice = self.get_voice_client()
        if interaction.user.voice is None:
            return await interaction.send(':negative_squared_cross_mark: **You have to be connected to `{}` to do this!**'.format(voice.channel), ephemeral=True)
        elif not voice.is_playing():
            return await interaction.send(':negative_squared_cross_mark: **Not playing any music right now.**', ephemeral=True)
        if not 0 < volume <= 100:
            return await interaction.send(':negative_squared_cross_mark: **Please enter a value between 1 and 100**', ephemeral=True)

        player = self.get_player(interaction)
        if voice.source:
            voice.source.volume = volume / 100
        player.volume = volume / 100
        await interaction.send(":loud_sound: Changed volume to **{}%**".format(volume))

    @nextcord.slash_command(force_global=True)
    async def stop(self, interaction: Interaction):
        """Stop the music and leave the channel"""
        if not self.is_voice_connected():
            return await interaction.send(':negative_squared_cross_mark: **Not connected to a voice channel.**', ephemeral=True)
        await self.cleanup(interaction.guild)
        await interaction.send(":wave: Bye!")

    @nextcord.slash_command(force_global=True)
    async def download(self, interaction: Interaction, *, query: str):
        """Download a song in discord"""
        await interaction.response.defer()
        source = await YTDLSource.create_source(interaction.user, query, loop=self.bot.loop)
        await interaction.send(file=nextcord.File('/var/www/html/temp/' + str(source.id) + '.' + str(source.ext)))

    @nextcord.slash_command(force_global=True)
    async def link(self, interaction: Interaction, *, query: str):
        """Download a song to our web server"""
        await interaction.response.defer()
        source = await YTDLSource.create_source(interaction.user, query, loop=self.bot.loop)
        embed = nextcord.Embed(title=source.title, url=source.yt_url, color=0x00bfff)
        if source.thumbnail is None:
            embed.set_thumbnail(url='https://drive.ipictserver.nl/frootcraft/mp3.png')
        else:
            embed.set_thumbnail(url=source.thumbnail)
        embed.set_author(name="Youtube to link", icon_url=interaction.user.avatar.url)
        embed.add_field(name='Uploaded by', value=source.uploader)
        embed.add_field(name='Duration', value=source.duration)
        embed.add_field(name='Link', value="https://drive.ipictserver.nl/temp/" + source.id + '.' + source.ext)
        await interaction.send(embed=embed)

    @nextcord.slash_command(force_global=True)
    async def playtts(self, interaction: Interaction, *, message: str):
        """Play a tts message in a voice call"""
        if interaction.user.voice.channel is None:
            return await interaction.send(':negative_squared_cross_mark: **You are not connected to a voice channel!**')

        await interaction.response.defer()
        await self.ensure_voice(interaction)
        filename = 'tts-{}.mp3'.format(hashlib.md5(message.encode()).hexdigest())
        path = "/var/www/html/temp/{}".format(filename)
        if not os.path.isfile(path):
            tts = gTTS(message, lang='nl')
            tts.save(path)

        player = self.get_player(interaction)

        try:
            source = await player.add_to_queue("https://drive.ipictserver.nl/temp/{}".format(filename), interaction.user)
        except ResultNotFoundException:
            return await interaction.send(":search: Failed to find a suitable result!")

        embed = nextcord.Embed(title="Voice TTS Message",
                               url=source.yt_url,
                               color=0x00bfff)
        embed.set_thumbnail(url='https://cdn-icons-png.flaticon.com/512/5256/5256064.png')
        embed.set_author(name="Added to queue", icon_url=interaction.user.avatar.url)
        if len(message) > 1000:
            embed.add_field(name='Message', value=message[:1000] + "...")
        else:
            embed.add_field(name='Message', value=message)
        await interaction.send(embed=embed)

    @nextcord.slash_command(force_global=True)
    async def tts(self, interaction: Interaction, *, message: str):
        """Generate a tts message and get the link"""
        await interaction.response.defer()
        filename = 'tts-{}.mp3'.format(hashlib.md5(message.encode()).hexdigest())
        path = "/var/www/html/temp/{}".format(filename)
        if not os.path.isfile(path):
            tts = gTTS(message, lang='nl')
            tts.save(path)
        await interaction.send(file=nextcord.File(path))


def setup(bot):
    global ytdl
    ytdl = youtube_dl.YoutubeDL(ytdl_options)
    bot.add_cog(Music(bot))
