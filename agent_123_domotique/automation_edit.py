"""Edit a supported portal-owned automation, never execute its actions."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

SERVICES = {"light": {"turn_on", "turn_off"}, "switch": {"turn_on", "turn_off"},
            "fan": {"turn_on", "turn_off"}, "climate": {"turn_on", "turn_off"},
            "lock": {"lock", "unlock"}, "cover": {"open_cover", "close_cover"},
            "input_boolean": {"turn_on", "turn_off"}}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DESCRIPTION = "Créée depuis le portail Ma Maison"

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def save(path, value):
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY); os.fsync(fd); os.close(fd)
    finally:
        if temporary.exists(): temporary.unlink()

def items(config, key):
    plural = {"trigger": "triggers", "condition": "conditions", "action": "actions"}[key]
    if key in config and plural in config: raise ValueError("Configuration ambiguë.")
    value = config.get(plural, config.get(key, []))
    return value if isinstance(value, list) else [value]

def target(action):
    if not isinstance(action, dict) or set(action) - {"service", "action", "target"}: raise ValueError("Action non représentable.")
    if "service" in action and "action" in action: raise ValueError("Action ambiguë.")
    service = action.get("service", action.get("action", ""))
    if not isinstance(service, str) or "." not in service: raise ValueError("Action invalide.")
    domain, name = service.split(".", 1)
    entity = action.get("target", {})
    if not isinstance(entity, dict) or set(entity) != {"entity_id"}: raise ValueError("Cible non représentable.")
    entity = entity["entity_id"]
    if not isinstance(entity, str) or not re.fullmatch(re.escape(domain) + r"\.[a-z0-9_]+", entity) or name not in SERVICES.get(domain, set()): raise ValueError("Action refusée.")
    return entity, domain, name

def validate_existing(config):
    if not isinstance(config, dict): raise ValueError("Configuration indisponible.")
    identifier = config.get("id", "")
    if not re.fullmatch(r"ma_maison_[0-9]+_[a-f0-9]{6}", str(identifier)) or config.get("description") != DESCRIPTION or not re.match(r"^1\.2\.3\.? Home · .+", str(config.get("alias", ""))):
        raise ValueError("Cette automatisation n’est pas une règle simple créée par le portail.")
    if set(config) - {"id", "alias", "description", "trigger", "triggers", "condition", "conditions", "action", "actions", "mode", "initial_state"} or config.get("mode", "single") != "single": raise ValueError("Configuration non représentable.")
    if "initial_state" in config and not isinstance(config["initial_state"], bool): raise ValueError("État initial invalide.")
    triggers, conditions, actions = items(config, "trigger"), items(config, "condition"), items(config, "action")
    if len(triggers) != 1 or len(actions) != 1 or len(conditions) > 1: raise ValueError("Règle complexe non modifiable ici.")
    trigger = triggers[0]
    if not isinstance(trigger, dict) or ("platform" in trigger and "trigger" in trigger): raise ValueError("Déclencheur ambigu.")
    kind = trigger.get("trigger", trigger.get("platform"))
    if kind == "time":
        if set(trigger) - {"platform", "trigger", "at"} or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9](?::00)?", str(trigger.get("at", ""))): raise ValueError("Horaire non représentable.")
    elif kind == "sun":
        if set(trigger) - {"platform", "trigger", "event"} or trigger.get("event") not in ("sunrise", "sunset"): raise ValueError("Déclencheur solaire non représentable.")
    else: raise ValueError("Déclencheur non représentable.")
    if conditions:
        condition = conditions[0]
        if not isinstance(condition, dict) or set(condition) != {"condition", "weekday"} or condition["condition"] != "time" or not isinstance(condition["weekday"], list) or not condition["weekday"] or any(day not in DAYS for day in condition["weekday"]): raise ValueError("Condition non représentable.")
    target(actions[0])
    return identifier

def replacement(config, payload):
    validate_existing(config)
    if set(payload) - {"entityId", "name", "triggerType", "time", "weekdays", "targetEntityId", "domain", "service", "expectedDigest"}: raise ValueError("Paramètre inconnu.")
    name = payload.get("name")
    if not isinstance(name, str) or name != name.strip() or not 3 <= len(name) <= 80 or any(ord(char) < 32 for char in name): raise ValueError("Nom invalide.")
    days = payload.get("weekdays")
    if not isinstance(days, list) or any(day not in DAYS for day in days) or len(days) != len(set(days)): raise ValueError("Jours invalides.")
    kind = payload.get("triggerType")
    if kind == "time":
        at = payload.get("time")
        if not isinstance(at, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", at): raise ValueError("Horaire invalide.")
        trigger = {"platform": "time", "at": at + ":00"}
    elif kind in ("sunrise", "sunset"):
        if payload.get("time") is not None: raise ValueError("Horaire incompatible.")
        trigger = {"platform": "sun", "event": kind}
    else: raise ValueError("Déclencheur invalide.")
    entity, domain, service = payload.get("targetEntityId"), payload.get("domain"), payload.get("service")
    target({"service": f"{domain}.{service}", "target": {"entity_id": entity}})
    result = {k: copy.deepcopy(v) for k, v in config.items() if k not in ("alias", "trigger", "triggers", "condition", "conditions", "action", "actions")}
    result.update(alias="1.2.3 Home · " + name, trigger=[trigger], condition=[{"condition": "time", "weekday": [d for d in DAYS if d in days]}] if days else [], action=[{"service": domain + "." + service, "target": {"entity_id": entity}}])
    return result

def read(payload, call, ws):
    if set(payload) != {"entityId"} or not isinstance(payload.get("entityId"), str) or not re.fullmatch(r"automation\.[a-z0-9_]+", payload["entityId"]): raise ValueError("Automatisation invalide.")
    entity = payload["entityId"]
    state = call("/states/" + entity)
    if state.get("entity_id") != entity or state.get("state") not in ("on", "off"): raise ValueError("Automatisation indisponible.")
    response = ws({"type": "automation/config", "entity_id": entity})
    if response.get("success") is not True: raise ValueError("Lecture native refusée.")
    config = response.get("result", {}).get("config")
    identifier = validate_existing(config)
    if digest(call("/config/automation/config/" + identifier)) != digest(config): raise RuntimeError("La configuration a changé ; rechargez la règle.")
    trigger = items(config, "trigger")[0]; conditions = items(config, "condition")
    target_entity, domain, service = target(items(config, "action")[0])
    kind = trigger.get("trigger", trigger.get("platform"))
    return {"entityId": entity, "name": re.sub(r"^1\.2\.3\.? Home · ", "", config["alias"]),
            "triggerType": "time" if kind == "time" else trigger["event"],
            "time": trigger["at"][:5] if kind == "time" else None,
            "weekdays": conditions[0]["weekday"] if conditions else [],
            "targetEntityId": target_entity, "domain": domain, "service": service,
            "enabled": state["state"] == "on", "configDigest": digest(config)}

def restore_enabled_state(call, entity, expected):
    current = call('/states/' + entity)
    if current.get('entity_id') != entity or current.get('state') not in ('on', 'off') or expected not in ('on', 'off'):
        raise RuntimeError('État précédent de la règle non vérifiable.')
    if current['state'] != expected:
        # Restore the automation enable flag only; never trigger its actions.
        call('/services/automation/' + ('turn_on' if expected == 'on' else 'turn_off'),
             method='POST', payload={'entity_id': entity})
    verified = call('/states/' + entity)
    if verified.get('entity_id') != entity or verified.get('state') != expected:
        raise RuntimeError('Restauration de l’état de la règle non confirmée.')


def update(payload, call, ws, *, operation_id, data=Path("/data")):
    entity = payload.get("entityId")
    if not isinstance(entity, str) or not re.fullmatch(r"automation\.[a-z0-9_]+", entity): raise ValueError("Automatisation invalide.")
    if not isinstance(operation_id, str) or not operation_id: raise ValueError("Identité de commande absente.")
    folder = data / "automation-edits"; folder.mkdir(mode=0o700, exist_ok=True)
    lock = os.open(folder / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, "w") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal_path = folder / (hashlib.sha256(operation_id.encode()).hexdigest() + ".json")
        request_hash = digest(payload)
        if journal_path.exists():
            journal = json.loads(journal_path.read_text())
            if journal.get("requestHash") != request_hash: raise ValueError("Identité de commande réutilisée.")
            if journal.get("phase") == "verified": return journal["result"]
            raise RuntimeError("La modification précédente doit être vérifiée ; aucun nouvel envoi automatique.")
        state = call("/states/" + entity)
        if state.get("entity_id") != entity or state.get("state") not in ("on", "off"): raise ValueError("Automatisation indisponible.")
        native = ws({"type": "automation/config", "entity_id": entity})
        if native.get("success") is not True: raise ValueError("Lecture native refusée.")
        original = native.get("result", {}).get("config")
        identifier = validate_existing(original)
        if payload.get("expectedDigest") != digest(original): raise RuntimeError("La règle a changé depuis sa lecture. Rechargez-la avant de confirmer.")
        endpoint = "/config/automation/config/" + identifier
        file_config = call(endpoint)
        if digest(file_config) != digest(original): raise RuntimeError("La configuration a changé ; rechargez la règle.")
        planned = replacement(original, payload)
        actual_target = call("/states/" + payload["targetEntityId"])
        if actual_target.get("entity_id") != payload["targetEntityId"] or actual_target.get("state") in (None, "unavailable", "unknown"): raise ValueError("Équipement cible indisponible.")
        journal = {"phase": "prepared", "requestHash": request_hash, "entityId": entity, "original": original, "planned": planned, "enabledState": state["state"]}
        save(journal_path, journal)
        if digest(call(endpoint)) != digest(original): raise RuntimeError("Modification concurrente détectée ; aucun envoi.")
        try:
            call(endpoint, method="POST", payload=planned)
            journal["phase"] = "written"; save(journal_path, journal)
            call("/services/automation/reload", method="POST", payload={})
            if digest(call(endpoint)) != digest(planned) or call("/states/" + entity).get("state") != state["state"]: raise RuntimeError("Confirmation de modification indisponible.")
            result = {"updated": True, "entityId": entity, "configurationId": identifier, "configDigest": digest(planned)}
            journal.update(phase="verified", result=result); save(journal_path, journal)
            return result
        except Exception as error:
            try:
                current = call(endpoint)
                if digest(current) == digest(planned):
                    call(endpoint, method="POST", payload=original)
                    call("/services/automation/reload", method="POST", payload={})
                    if digest(call(endpoint)) != digest(original): raise RuntimeError("Restauration non confirmée.")
                    restore_enabled_state(call, entity, journal["enabledState"])
                    journal["phase"] = "rolled_back"
                elif digest(current) == digest(original):
                    restore_enabled_state(call, entity, journal["enabledState"])
                    journal["phase"] = "unchanged"
                else: journal["phase"] = "attention_required"
            except Exception: journal["phase"] = "attention_required"
            save(journal_path, journal)
            raise RuntimeError("Modification non confirmée. " + ("Configuration précédente conservée." if journal["phase"] in ("rolled_back", "unchanged") else "Vérification opérateur nécessaire.")) from error


def delete(payload, call, ws, *, operation_id, data=Path('/data')):
    if set(payload) != {'entityId', 'expectedDigest'}: raise ValueError('Relisez la règle avant de confirmer sa suppression.')
    if not isinstance(operation_id, str) or not operation_id: raise ValueError('Identité de commande absente.')
    prior_path = data/'automation-edits'/(hashlib.sha256(operation_id.encode()).hexdigest()+'.json')
    if prior_path.exists():
        prior=json.loads(prior_path.read_text())
        if prior.get('operation')=='delete' and prior.get('requestHash')==digest(payload) and prior.get('phase')=='verified':return prior['result']
        raise RuntimeError('La suppression précédente doit être vérifiée ; aucun nouvel envoi.')
    snapshot = read({'entityId': payload['entityId']}, call, ws)
    if snapshot['configDigest'] != payload['expectedDigest']: raise RuntimeError('La règle a changé depuis sa lecture.')
    entity = payload['entityId']; response = ws({'type': 'automation/config', 'entity_id': entity})
    if response.get('success') is not True: raise ValueError('Lecture native refusée.')
    original = response.get('result', {}).get('config'); identifier = validate_existing(original)
    if digest(original) != payload['expectedDigest']: raise RuntimeError('La règle a changé depuis sa lecture.')
    if not isinstance(operation_id, str) or not operation_id: raise ValueError('Identité de commande absente.')
    folder = data/'automation-edits'; folder.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(folder/'.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = folder/(hashlib.sha256(operation_id.encode()).hexdigest()+'.json')
        if path.exists(): raise RuntimeError('La suppression précédente doit être vérifiée ; aucun nouvel envoi.')
        endpoint = '/config/automation/config/'+identifier
        if digest(call(endpoint)) != payload['expectedDigest']: raise RuntimeError('Modification concurrente détectée.')
        journal = {'phase': 'prepared', 'operation': 'delete', 'entityId': entity, 'original': original, 'requestHash': digest(payload), 'enabledState': 'on' if snapshot['enabled'] else 'off'}
        save(path, journal)
        try:
            call(endpoint, method='DELETE')
            journal['phase']='deleted'; save(path,journal)
            call('/services/automation/reload', method='POST', payload={})
            # Confirm file absence via the native API, never infer it from the DELETE acknowledgement.
            try: call(endpoint)
            except Exception as error:
                if getattr(error,'code',None) != 404: raise
            else: raise RuntimeError('Suppression non confirmée.')
            result={'deleted':True,'entityId':entity,'configurationId':identifier}
            journal.update(phase='verified',result=result);save(path,journal);return result
        except Exception as error:
            try:
                try: current=call(endpoint)
                except Exception as missing:
                    if getattr(missing,'code',None)!=404:raise
                    current=None
                if current is None:
                    call(endpoint,method='POST',payload=original)
                    call('/services/automation/reload',method='POST',payload={})
                    if digest(call(endpoint))!=digest(original):raise RuntimeError('Restauration non confirmée.')
                    restore_enabled_state(call, entity, journal['enabledState'])
                    journal['phase']='rolled_back'
                elif digest(current)==digest(original):
                    restore_enabled_state(call, entity, journal['enabledState'])
                    journal['phase']='unchanged'
                else:journal['phase']='attention_required'
            except Exception:journal['phase']='attention_required'
            save(path,journal)
            raise RuntimeError('Suppression non confirmée. '+('Configuration précédente conservée.' if journal['phase'] in ('rolled_back','unchanged') else 'Vérification opérateur nécessaire.')) from error


def create(payload, call, *, operation_id, data=Path('/data'), clock=None):
    """Create one explicitly requested schedule in HA's actual local timezone."""
    import time
    from zoneinfo import ZoneInfo
    allowed={'name','triggerType','time','weekdays','entityId','domain','service','timeZone'}
    if set(payload)!=allowed or not isinstance(operation_id,str) or not operation_id: raise ValueError('Demande de création incomplète.')
    zone=payload['timeZone']
    if not isinstance(zone,str) or not zone or len(zone)>100:raise ValueError('Fuseau horaire invalide.')
    try:ZoneInfo(zone)
    except Exception as error:raise ValueError('Fuseau horaire invalide.') from error
    config=call('/config')
    if config.get('time_zone')!=zone:raise RuntimeError('Le fuseau horaire de Home Assistant diffère de la confirmation. Rechargez la maison.')
    entity,domain,service=payload['entityId'],payload['domain'],payload['service']
    target({'service':str(domain)+'.'+str(service),'target':{'entity_id':entity}})
    state=call('/states/'+entity)
    if state.get('entity_id')!=entity or state.get('state') in (None,'unknown','unavailable'):raise ValueError('Équipement cible indisponible.')
    folder=data/'automation-edits';folder.mkdir(mode=0o700,exist_ok=True)
    lock=os.open(folder/'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=folder/(hashlib.sha256(operation_id.encode()).hexdigest()+'.json')
        request_hash=digest(payload)
        if path.exists():
            prior=json.loads(path.read_text())
            if prior.get('operation')=='create' and prior.get('requestHash')==request_hash and prior.get('phase')=='verified':return prior['result']
            raise RuntimeError('La création précédente doit être vérifiée ; aucun doublon n’est créé.')
        stamp=int((clock or time.time)())
        identifier='ma_maison_'+str(stamp)+'_'+hashlib.sha256(operation_id.encode()).hexdigest()[:6]
        seed={'id':identifier,'alias':'1.2.3 Home · Nouvelle règle','description':DESCRIPTION,'trigger':[{'platform':'time','at':'00:00:00'}],'condition':[],'action':[{'service':domain+'.'+service,'target':{'entity_id':entity}}],'mode':'single'}
        planned=replacement(seed,{'entityId':entity,'name':payload['name'],'triggerType':payload['triggerType'],'time':payload['time'],'weekdays':payload['weekdays'],'targetEntityId':entity,'domain':domain,'service':service})
        endpoint='/config/automation/config/'+identifier
        try:call(endpoint)
        except Exception as missing:
            if getattr(missing,'code',None)!=404:raise
        else:raise RuntimeError('Identifiant de règle déjà utilisé. Aucune modification.')
        journal={'operation':'create','phase':'prepared','requestHash':request_hash,'planned':planned,'timeZone':zone}
        save(path,journal)
        if call('/config').get('time_zone')!=zone:raise RuntimeError('Le fuseau horaire a changé avant la création.')
        try:
            call(endpoint,method='POST',payload=planned)
            journal['phase']='written';save(path,journal)
            call('/services/automation/reload',method='POST',payload={})
            matches=[row for row in call('/states') if row.get('entity_id','').startswith('automation.') and row.get('attributes',{}).get('id')==identifier]
            if len(matches)!=1 or matches[0].get('state') not in ('on','off') or digest(call(endpoint))!=digest(planned):raise RuntimeError('Identité de la règle créée non confirmée.')
            result={'created':True,'entityId':matches[0]['entity_id'],'configurationId':identifier,'configDigest':digest(planned),'timeZone':zone,'enabled':matches[0]['state']=='on'}
            journal.update(phase='verified',result=result);save(path,journal);return result
        except Exception as error:
            try:
                try:current=call(endpoint)
                except Exception as missing:
                    if getattr(missing,'code',None)!=404:raise
                    current=None
                if current is None:journal['phase']='unchanged'
                elif digest(current)==digest(planned):
                    call(endpoint,method='DELETE');call('/services/automation/reload',method='POST',payload={})
                    try:call(endpoint)
                    except Exception as missing:
                        if getattr(missing,'code',None)!=404:raise
                    else:raise RuntimeError('Retour arrière non confirmé.')
                    journal['phase']='rolled_back'
                else:journal['phase']='attention_required'
            except Exception:journal['phase']='attention_required'
            save(path,journal)
            raise RuntimeError('Création non confirmée. '+('Aucune nouvelle règle conservée.' if journal['phase'] in ('rolled_back','unchanged') else 'Vérification opérateur nécessaire.')) from error
