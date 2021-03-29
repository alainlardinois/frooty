import asyncio
import json
import logging
import queue
import time

import requests
from async_timeout import timeout

with open('config.json') as config_file:
    config = json.load(config_file)


class AsyncLogger:
    __slots__ = ('key', 'hostname', 'app', 'queue', 'bot')

    def __init__(self, hostname, app, bot):
        self.key = config['logging']['key']
        self.hostname = str(hostname)
        self.app = str(app)
        self.queue = asyncio.Queue()
        self.bot = bot
        self.bot.loop.create_task(self.request_loop())

    async def request_loop(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                async with timeout(.2):
                    data = await self.queue.get()
                    requests.post(url='https://logs.logdna.com/logs/ingest',
                                  auth=('user', self.key),
                                  params={'hostname': self.hostname},
                                  json=data)
            except asyncio.TimeoutError:
                pass

    async def request(self, level, opts, msg):
        data = {
            'lines': [
                {
                    'timestamp': time.time(),
                    'line': msg,
                    'app': self.app,
                    'level': level
                }]}
        if opts is not None:
            data['lines'][0]['meta'] = opts['meta']
        await self.queue.put(data)

    async def info(self, msg, opts=None):
        await self.request('INFO', opts, msg)

    async def warning(self, msg, opts=None):
        await self.request('WARNING', opts, msg)

    async def error(self, msg, opts=None):
        await self.request('ERROR', opts, msg)

    async def exception(self, msg, opts=None):
        await self.request('EXCEPTION', opts, msg)

    async def debug(self, msg, opts=None):
        await self.request('DEBUG', opts, msg)


class Logger(logging.Handler):
    __slots__ = ('hostname', 'app', 'key', 'queue', 'bot')

    def __init__(self, hostname, app, bot):
        super().__init__()
        self.hostname = str(hostname)
        self.app = str(app)
        self.key = config['logging']['key']
        self.queue = queue.Queue()
        self.bot = bot
        bot.loop.create_task(self.queue_handler())

    def emit(self, record):
        msg = self.format(record)
        msg = msg.split('-')
        self.request(msg[0], None, msg[1])

    async def queue_handler(self):
        while True:
            if self.queue.empty() is False:
                data = self.queue.get()
                requests.post(url='https://logs.logdna.com/logs/ingest',
                              auth=('user', self.key),
                              params={'hostname': self.hostname},
                              json=data)
            await asyncio.sleep(.2)

    def request(self, level, opts, msg):
        data = {
            'lines': [
                {
                    'timestamp': time.time(),
                    'line': msg,
                    'app': self.app,
                    'level': level
                }]}
        if opts is not None:
            data['lines'][0]['meta'] = opts['meta']
        self.queue.put(data)

    def info(self, msg, opts=None):
        self.request('INFO', opts, msg)

    def warning(self, msg, opts=None):
        self.request('WARNING', opts, msg)

    def error(self, msg, opts=None):
        self.request('ERROR', opts, msg)

    def exception(self, msg, opts=None):
        self.request('EXCEPTION', opts, msg)

    def debug(self, msg, opts=None):
        self.request('DEBUG', opts, msg)
