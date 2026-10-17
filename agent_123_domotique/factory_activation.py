"""First-party prepared-box activation. No LAN server, credentials in URLs, or identity replacement."""
import hashlib
import re
import secrets

PORTAL = 'https://home.123panneaux-solaires.fr/api'

def configured(options):
    identity=options.get('factory_id','');token=options.get('factory_token','')
    if not identity and not token:return False
    if (not isinstance(identity,str) or not re.fullmatch(r'factory_[a-f0-9]{32}',identity)
            or not isinstance(token,str) or not re.fullmatch(r'[a-f0-9]{64}',token)
            or options.get('portal_url','').rstrip('/')!=PORTAL):
        raise ValueError('La préparation atelier de cette box doit être vérifiée.')
    return True

def poll(options,read_state,write_state,request):
    state=read_state()
    if state.get('token'):return state
    if not configured(options):raise ValueError('Box non préparée pour cette activation.')
    context=hashlib.sha256(options['factory_id'].encode()).hexdigest()
    pending=state.get('pending_factory_activation')
    if pending is not None and (not isinstance(pending,dict) or pending.get('context')!=context):
        raise ValueError('L’identité atelier a changé. Reprise accompagnée nécessaire.')
    if pending is None:
        pending={'context':context,'token':secrets.token_hex(32)}
        state['pending_factory_activation']=pending;write_state(state)
    if not isinstance(pending.get('token'),str) or not re.fullmatch(r'[a-f0-9]{64}',pending['token']):
        raise ValueError('La clé de reprise doit être vérifiée.')
    result=request(PORTAL+'/agent/factory',method='POST',token=options['factory_token'],payload={'factoryId':options['factory_id'],'enrollmentToken':pending['token']})
    if not isinstance(result,dict):raise ValueError('Réponse d’activation invalide.')
    if result.get('status')=='awaiting_activation':return state
    if result.get('status')!='associated' or not isinstance(result.get('agentId'),str) or not re.fullmatch(r'box_[a-f0-9]{32}',result['agentId']):
        raise ValueError('Association non confirmée.')
    state.update(agent_id=result['agentId'],token=pending['token']);state.pop('pending_factory_activation',None);write_state(state)
    return state
