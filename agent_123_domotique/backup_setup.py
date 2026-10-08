"""Prepare an isolated WebDAV destination without changing backup schedules or keys."""
import fcntl
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.parse


def configure(configuration, call, *, config=Path('/homeassistant_config'), data=Path('/data')):
    identifier = configuration.get('installationId', '')
    values = configuration.get('destination', {})
    if (configuration.get('state') != 'ready' or configuration.get('remoteBackupAllowed') is not True
            or not re.fullmatch(r'installation_[a-f0-9]{32}', identifier)
            or values.get('username') != identifier
            or values.get('url') != 'https://home.123panneaux-solaires.fr/backups'
            or values.get('verify_ssl') is not True or values.get('backup_path') != '/'
            or not isinstance(values.get('password'), str) or len(values['password']) < 40):
        raise RuntimeError('Configuration de sauvegarde invalide.')
    values = {k: values[k] for k in ('url', 'username', 'password', 'verify_ssl', 'backup_path')}
    data = Path(data); data.mkdir(exist_ok=True)
    fd = os.open(data / 'backup-setup.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stored = json.loads((Path(config) / '.storage/core.config_entries').read_text())['data']['entries']
        live = call('/config/config_entries/entry?domain=webdav')
        if not isinstance(live, list):
            raise RuntimeError('Impossible de vérifier les destinations existantes.')
        matching = [e for e in stored if e.get('domain') == 'webdav'
                    and e.get('data', {}).get('username') == identifier]
        if matching:
            if len(matching) != 1 or any(matching[0]['data'].get(k, '/' if k == 'backup_path' else True if k == 'verify_ssl' else None) != v for k,v in values.items()):
                raise RuntimeError('Une destination différente existe déjà. Elle a été conservée.')
            entry_id = matching[0]['entry_id']
            if not any(e.get('entry_id') == entry_id and e.get('state') == 'loaded' for e in live):
                raise RuntimeError('La destination est enregistrée mais pas encore disponible.')
            return {'state': 'destination_ready', 'entryId': entry_id, 'backupVerified': False}
        journal = data / 'backup-setup.json'
        state = json.loads(journal.read_text()) if journal.exists() else {}
        if state and state.get('installationId') != identifier:
            raise RuntimeError('Une autre installation possède cette préparation. Vérification nécessaire.')
        def save(value):
            temp = journal.with_suffix('.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as file:
                json.dump({'installationId': identifier, **value}, file)
            temp.replace(journal)
        flow_id = state.get('flowId')
        if flow_id:
            if not isinstance(flow_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', flow_id):
                raise RuntimeError('Préparation de sauvegarde à vérifier.')
            # Never create a replacement after a lost response; inspect the same flow.
            flow = call('/config/config_entries/flow/' + flow_id)
        else:
            flow = call('/config/config_entries/flow', method='POST', payload={'handler': 'webdav', 'show_advanced_options': False})
            flow_id = flow.get('flow_id')
        if (flow.get('type') != 'form' or flow.get('step_id') != 'user'
                or not isinstance(flow_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', flow_id)
                or flow.get('flow_id') != flow_id):
            raise RuntimeError('Le formulaire de sauvegarde n’est pas prêt.')
        save({'flowId': flow_id, 'submitted': True})
        result = call('/config/config_entries/flow/' + flow_id, method='POST', payload=values)
        if result.get('type') == 'form':
            raise RuntimeError('Connexion au stockage refusée. Un nouvel essai est nécessaire.')
        if result.get('type') != 'create_entry':
            raise RuntimeError('Création de la destination non confirmée.')
        # HA persistence/load can lag behind the response; verify on the next cycle.
        return {'state': 'destination_pending', 'backupVerified': False}


def fetch_configuration(portal_url, token):
    parsed = urllib.parse.urlsplit(portal_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError('Portail de sauvegarde invalide.')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError('Redirection de sauvegarde refusée.')
    request = urllib.request.Request(portal_url.rstrip('/') + '/agent/backup-configuration',
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
        result = json.loads(response.read(16384))
    if not isinstance(result, dict):
        raise RuntimeError('Configuration de sauvegarde invalide.')
    return result
