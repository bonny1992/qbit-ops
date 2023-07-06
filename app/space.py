import os
import shutil
import logging
from logging.handlers import RotatingFileHandler
from logging import handlers
import sys
import getpass
import requests

from qbittorrent import Client

gb = 10 ** 9

QBIT_HOST = os.getenv('QBIT_HOST', '127.0.0.1')
QBIT_PORT = os.getenv('QBIT_PORT', '8080')
QBIT_SSL  = os.getenv('QBIT_SSL', 'no')
QBIT_USER = os.getenv('QBIT_USER', '')
QBIT_PASS = os.getenv('QBIT_PASS', '')

LOGFILE = os.getenv('LOGFILE','/config/logs/space.log')
MIN_SPACE_GB = int(os.getenv('MIN_SPACE_GB', 150))
SWEET_SPOT_GB = int(os.getenv('SWEET_SPOT_GB', 25))
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR','/')
DO_NOT_RESUME_TAG = os.getenv('DO_NOT_RESUME_TAG', 'do_not_resume')
DO_NOT_PAUSE_TAG = os.getenv('DO_NOT_PAUSE_TAG', 'do_not_pause')
DRY_RUN = os.getenv('DRY_RUN', 'no')

DEBUG = os.getenv('SET_DEBUG', 'no')

def fetch_env_variables():
    # Creo una lista vuota per i dizionari
    lista_dizionari = []
    flavours = ['SONARR', 'RADARR', 'LIDARR']
    
    # Utilizzo un ciclo infinito, che si interrompe quando non trovo più variabili d'ambiente
    i = 0
    while True:
        temp_list = []
        for flavour in flavours:
            try:
                # Costruisco il nome delle variabili d'ambiente
                url_var_name = f"{flavour}_{i}_URL"
                api_key_var_name = f"{flavour}_{i}_API_KEY"
                
                # Ottengo i valori delle variabili d'ambiente
                url_var_value = os.environ[url_var_name]
                api_key_var_value = os.environ[api_key_var_name]
                
                # Creo un nuovo dizionario
                dizionario = {"flavour": flavour.lower(), "url": url_var_value, "api_key": api_key_var_value}
                temp_list.append(dizionario)
                
            except KeyError:
                # Se le variabili d'ambiente non esistono, ignoro quel flavour
                pass
            
        # Se temp_list è vuota, significa che non ci sono più variabili d'ambiente con l'indice i
        if not temp_list:
            break
            
        lista_dizionari.extend(temp_list)
        
        # Incremento l'indice
        i += 1

    return lista_dizionari


def manage_torrent_clients(toBePaused, lista_dizionari):
    # Itera su tutti i dizionari nella lista
    for item in lista_dizionari:
        flavour = item['flavour']
        url = item['url']
        api_key = item['api_key']

        # Crea l'endpoint per ottenere i client di download
        endpoint = f"https://{url}/api/v3/downloadclient"
        headers = {"X-Api-Key": api_key}

        # Fai una richiesta GET per ottenere la lista dei client di download
        response = requests.get(endpoint, headers=headers)

        # Converte la risposta in un oggetto JSON
        data = response.json()

        # Itera su tutti i client di download
        for client in data:
            # Controlla se il client è qBittorrent
            if client['implementation'] == "QBittorrent":
                # Ottieni l'ID del client
                client_id = client['id']

                # Crea l'endpoint per ottenere la configurazione del client
                config_endpoint = f"https://{url}/api/v3/downloadclient/{client_id}"

                # Fai una richiesta GET per ottenere la configurazione del client
                config_response = requests.get(config_endpoint, headers=headers)

                # Converte la risposta in un oggetto JSON
                config_data = config_response.json()

                # Trova il campo initialState e controlla se deve essere cambiato
                for field in config_data['fields']:
                    if field['name'] == 'initialState':
                        if toBePaused:  # Se i torrent dovrebbero essere messi in pausa
                            if field['value'] == 0:  # Se è impostato su "Start"
                                field['value'] = 2  # Cambia in "Pause"
                                # Fai una richiesta PUT per aggiornare la configurazione del client
                                if DRY_RUN == 'no':
                                    requests.put(config_endpoint, headers=headers, json=config_data)
                        else:  # Se i torrent dovrebbero essere avviati
                            if field['value'] == 2:  # Se è impostato su "Pause"
                                field['value'] = 0  # Cambia in "Start"
                                # Fai una richiesta PUT per aggiornare la configurazione del client
                                if DRY_RUN == 'no':
                                    requests.put(config_endpoint, headers=headers, json=config_data)

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

lista_dizionari = fetch_env_variables()

total, used, free = shutil.disk_usage(DOWNLOAD_DIR)

free_gb = free / gb

log.info("Free space: %s", free_gb)

qb = Client('http{ssl}://{host}:{port}/'.format(host=QBIT_HOST, port=QBIT_PORT, ssl='s' if QBIT_SSL == 'yes' else ''))

qb.login(QBIT_USER, QBIT_PASS)

if free_gb > (MIN_SPACE_GB + SWEET_SPOT_GB):
    log.info('Instructing QBittorrent to enable auto start for new torrents...')
    qb.set_preferences(start_paused_enabled=False)
    log.info('Starting paused torrents...')
    torrents = qb.torrents(filter='paused')
    no_of_torrents = len(torrents)
    i = 0
    for torrent in torrents:
        if torrent['category'] != '':
            if torrent['state'] != 'pausedUP':
                if DO_NOT_RESUME_TAG not in torrent['tags']:
                    if DRY_RUN != 'yes':
                        qb.resume(torrent['hash'])
                    log.debug('Torrent name: %s started%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                    i = i + 1
                else:
                    log.debug('Torrent name: %s not resumed as tag %s avoids it%s', torrent['name'], DO_NOT_RESUME_TAG, ' [SIMULATED]' if DRY_RUN == 'yes' else '')
            else:
                log.debug('Torrent name: %s not resumed as it is seeding%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
        else:
            log.debug('Torrent name: %s not resumed as it has no category%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
    log.info('Started %d of %d torrents.', i, no_of_torrents)
    log.info('Instructing *arr softares to add new torrents as normael...')
    manage_torrent_clients(False, lista_dizionari)
else:
    log.info('Instructing QBittorrent to disable auto start for new torrents...')
    qb.set_preferences(start_paused_enabled=True)
    log.info('Pausing active torrents...')
    torrents = qb.torrents(filter='downloading')
    no_of_torrents = len(torrents)
    i = 0
    for torrent in torrents:
        if torrent['state'] == 'downloading' or torrent['state'] == 'queuedDL' or torrent['state'] == 'stalledDL':
            if DO_NOT_PAUSE_TAG not in torrent['tags']:
                if DRY_RUN != 'yes':
                    qb.pause(torrent['hash'])
                log.debug('Torrent name: %s paused%s', torrent['name'], ' [SIMULATED]' if DRY_RUN == 'yes' else '')
                i = i + 1
            else:
                log.debug('Torrent name: %s not paused as tag %s avoids it%s', torrent['name'], DO_NOT_PAUSE_TAG, ' [SIMULATED]' if DRY_RUN == 'yes' else '')
    log.info('Paused %d of %d torrents.', i, no_of_torrents)
    log.info('Instructing *arr softares to add new torrents as paused...')
    manage_torrent_clients(True, lista_dizionari)

# qb.logout() Not working anymore? Idk