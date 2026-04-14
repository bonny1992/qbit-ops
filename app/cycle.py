import os
import re
import sys
import time
import logging
import getpass

import qbittorrentapi

QBIT_HOST         = os.getenv('QBIT_HOST', '127.0.0.1')
QBIT_PORT         = os.getenv('QBIT_PORT', '8080')
QBIT_SSL          = os.getenv('QBIT_SSL', 'no')
QBIT_USER         = os.getenv('QBIT_USER', '')
QBIT_PASS         = os.getenv('QBIT_PASS', '')

# Base tag prefix. Script will match <CYCLE_TAG>_1, <CYCLE_TAG>_2, …
CYCLE_TAG         = os.getenv('CYCLE_TAG', 'cycle')
# Shared with space.py: paused cycle-torrents get this tag so space.py won't resume them
DO_NOT_RESUME_TAG = os.getenv('DO_NOT_RESUME_TAG', 'do_not_resume')
# Minimum download speed (bytes/s) to consider a torrent "actively downloading" and skip cycling
MIN_DL_SPEED      = int(os.getenv('MIN_DL_SPEED', 10240))   # default: 10 KB/s
# Seconds to wait before force-reannouncing newly resumed torrents
REANNOUNCE_DELAY  = int(os.getenv('REANNOUNCE_DELAY', 600)) # default: 10 min
DRY_RUN           = os.getenv('DRY_RUN', 'no')

DEBUG             = os.getenv('SET_DEBUG', 'no')

log = logging.getLogger('')
log.setLevel(logging.INFO if DEBUG == 'no' else logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(format)
log.addHandler(ch)

log.debug("User: %s", getpass.getuser())

# States in which a torrent is considered "active" (trying to download)
ACTIVE_STATES = {'downloading', 'queuedDL', 'stalledDL', 'checkingDL', 'forcedDL', 'metaDL'}
# States in which a torrent is considered "paused / stopped"
PAUSED_STATES = {'pausedDL', 'stoppedDL', 'paused', 'stopped'}

tag_pattern = re.compile(rf'^{re.escape(CYCLE_TAG)}_(\d+)$')

conn_info = dict(
    host=f"http{'s' if QBIT_SSL != 'no' else ''}://{QBIT_HOST}",
    port=QBIT_PORT,
    username=QBIT_USER,
    password=QBIT_PASS,
)

with qbittorrentapi.Client(**conn_info) as qbt_client:

    # Group all torrents by their cycle tag (cycle_1, cycle_2, …)
    all_torrents = qbt_client.torrents_info()
    groups = {}
    for torrent in all_torrents:
        raw_tags = [t.strip() for t in torrent.get('tags', '').split(',') if t.strip()]
        for tag in raw_tags:
            if tag_pattern.match(tag):
                groups.setdefault(tag, []).append(torrent)
                break  # a torrent could theoretically have two cycle tags; take first match only

    if not groups:
        log.info("No torrents found matching tag pattern '%s_<N>'. Nothing to do.", CYCLE_TAG)
        sys.exit(0)

    log.info("Found %d cycle group(s): %s", len(groups), sorted(groups.keys()))

    resumed_hashes = []

    for group_tag in sorted(groups.keys()):
        torrents = groups[group_tag]
        log.info("Processing group [%s] — %d torrent(s)", group_tag, len(torrents))

        if len(torrents) < 2:
            log.info("Group [%s]: only one torrent, nothing to cycle.", group_tag)
            continue

        # Find the currently active torrent (first one found wins)
        active_index = None
        for idx, t in enumerate(torrents):
            if t['state'] in ACTIVE_STATES:
                active_index = idx
                log.debug("Group [%s]: active torrent at index %d — %s (state: %s, speed: %d B/s)",
                          group_tag, idx, t['name'], t['state'], t['dlspeed'])
                break

        if active_index is not None:
            active_torrent = torrents[active_index]

            # If it is genuinely downloading above threshold, leave it alone this cycle
            if active_torrent['dlspeed'] > MIN_DL_SPEED:
                log.info("Group [%s]: '%s' is actively downloading at %d B/s (> %d B/s threshold), skipping.",
                         group_tag, active_torrent['name'], active_torrent['dlspeed'], MIN_DL_SPEED)
                continue

            # Next torrent to activate (wrap around)
            next_index = (active_index + 1) % len(torrents)

        else:
            # Nothing active — pick the first paused torrent as the one to start
            log.info("Group [%s]: no active torrent found, will start the first paused one.", group_tag)
            next_index = None
            for idx, t in enumerate(torrents):
                if t['state'] in PAUSED_STATES:
                    next_index = idx
                    break
            if next_index is None:
                log.info("Group [%s]: no paused torrent found either, nothing to do.", group_tag)
                continue

        # Pause ALL torrents in the group except next_index,
        # and resume only the chosen one — ensures exactly one is active at a time
        for idx, t in enumerate(torrents):
            if idx == next_index:
                log.debug("Group [%s]: resuming '%s'%s",
                          group_tag, t['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                if DRY_RUN != 'yes':
                    t.remove_tags(tags=DO_NOT_RESUME_TAG)
                    t.resume()
                    resumed_hashes.append(t['hash'])
                log.info("Group [%s]: resumed '%s'%s",
                         group_tag, t['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
            else:
                if t['state'] not in PAUSED_STATES:
                    log.debug("Group [%s]: pausing '%s'%s",
                              group_tag, t['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                    if DRY_RUN != 'yes':
                        t.pause()
                        t.add_tags(tags=DO_NOT_RESUME_TAG)
                    log.info("Group [%s]: paused '%s' and tagged '%s'%s",
                             group_tag, t['name'], DO_NOT_RESUME_TAG,
                             ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                else:
                    # Already paused, just make sure the tag is there
                    log.debug("Group [%s]: '%s' already paused, ensuring tag '%s'%s",
                              group_tag, t['name'], DO_NOT_RESUME_TAG,
                              ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                    if DRY_RUN != 'yes':
                        t.add_tags(tags=DO_NOT_RESUME_TAG)

    # After all groups are processed, wait and force-reannounce every resumed torrent
    if resumed_hashes:
        log.info("Waiting %d seconds before force-reannouncing %d torrent(s)...",
                 REANNOUNCE_DELAY, len(resumed_hashes))
        if DRY_RUN != 'yes':
            time.sleep(REANNOUNCE_DELAY)
        for h in resumed_hashes:
            log.debug("Reannouncing hash %s%s", h, ' [SIMULATED]' if DRY_RUN == 'yes' else '')
            if DRY_RUN != 'yes':
                qbt_client.torrents_reannounce(torrent_hashes=h)
            log.info("Reannounced torrent hash: %s%s", h, ' [SIMULATED]' if DRY_RUN == 'yes' else '')
    else:
        log.info("No torrents were resumed, skipping reannounce step.")

    log.info("Cycle run complete.")