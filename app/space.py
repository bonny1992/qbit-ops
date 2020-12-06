import os
import shutil
import subprocess
import logging
import re
from logging.handlers import RotatingFileHandler
from logging import handlers
import sys
import getpass

from qbittorrent import Client

gb = 10 ** 9

QBIT_HOST = os.getenv('QBIT_HOST', '127.0.0.1')
QBIT_PORT = os.getenv('QBIT_PORT', '8080')
QBIT_SSL  = os.getenv('QBIT_SSL', 'no')
QBIT_USER = os.getenv('QBIT_USER', '')
QBIT_PASS = os.getenv('QBIT_PASS', '')

LOGFILE = os.getenv('LOGFILE','/config/logs/space.log')
MIN_SPACE_GB = int(os.getenv('MIN_SPACE_GB', 150))
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR','/')
DRY_RUN = os.getenv('DRY_RUN', 'no')

DEBUG = os.getenv('SET_DEBUG', 'no')

log = logging.getLogger('')
log.setLevel(logging.INFO if DEBUG == 'no' else logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(format)
log.addHandler(ch)

fh = handlers.RotatingFileHandler(LOGFILE, maxBytes=(1048576*5), backupCount=7)
fh.setFormatter(format)
log.addHandler(fh)

log.debug("User: %s", getpass.getuser())

if QBIT_USER == '' or QBIT_PASS == '': 
    log.error('QBIT_USER and QBIT_PASS env vars needed')
    sys.exit('QBIT_USER and QBIT_PASS env vars needed')

total, used, free = shutil.disk_usage(DOWNLOAD_DIR)

free_gb = free / gb

log.info("Free space: %s", free_gb)

qb = Client('http{ssl}://{host}:{port}/'.format(host=QBIT_HOST, port=QBIT_PORT, ssl='s' if QBIT_SSL == 'yes' else ''))

qb.login(QBIT_USER, QBIT_PASS)

if free_gb > MIN_SPACE_GB:
    log.info('Starting paused torrents...')
    torrents = qb.torrents(filter='paused')
    no_of_torrents = len(torrents)
    i = 0
    for torrent in torrents:
        if DRY_RUN != 'yes':
            qb.resume(torrent['hash'])
        log.debug('Torrent name: %s started%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
        i = i + 1
    log.info('Started %d of %d torrents.', i, no_of_torrents)
else:
    log.info('Pausing active torrents...')
    torrents = qb.torrents(filter='downloading')
    no_of_torrents = len(torrents)
    i = 0
    for torrent in torrents:
        if torrent['state'] == 'downloading' or torrent['state'] == 'queuedDL':
            if DRY_RUN != 'yes':
                    qb.pause(torrent['hash'])
            log.debug('Torrent name: %s paused%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
            i = i + 1
    log.info('Paused %d of %d torrents.', i, no_of_torrents)

qb.logout()