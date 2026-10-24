"""Owner-bound access to HA configuration flows, never to services or options.

HA remains responsible for discovery, credentials, pairing and model support.
Only schema-described values can be submitted to a flow opened by this owner.
No credentials, defaults, authorization URLs or provider error bodies are saved.
"""
import fcntl
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.error
from urllib.parse import urlparse, parse_qs, urlencode
import hmac

ID=re.compile(r'^[A-Za-z0-9_-]{1,100}$')
FIELD=re.compile(r'^[A-Za-z0-9_]{1,100}$')
UUID=re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
OWNER=re.compile(r'^[a-f0-9]{64}$')
SECRET=re.compile(r'password|passwd|secret|token|(^|_)key($|_)|pin|pairing_code|bindkey|otp|verification_code',re.I)
TTL=1200


def scalar(value):
    return isinstance(value,(str,bool,int,float)) and not isinstance(value,float) or isinstance(value,float) and math.isfinite(value)


def choices(value):
    if isinstance(value,dict):value=list(value.items())
    if not isinstance(value,list) or len(value)>500:raise ValueError('Liste native invalide.')
    out=[]
    for option in value:
        if isinstance(option,dict):key=option.get('value');label=option.get('label',key)
        elif isinstance(option,(list,tuple)) and len(option)==2:key,label=option
        else:key=label=option
        if not scalar(key) or len(str(key))>500 or len(str(label))>500:raise ValueError('Choix natif invalide.')
        out.append({'value':key,'label':str(label)})
    return out


def schema_fields(flow):
    schema=flow.get('data_schema',[])
    if not isinstance(schema,list) or len(schema)>40:raise ValueError('Formulaire natif trop complexe.')
    out=[]
    for item in schema:
        if not isinstance(item,dict) or not FIELD.fullmatch(str(item.get('name',''))):raise ValueError('Champ natif invalide.')
        name=item['name'];selector=item.get('selector') or {};kind=item.get('type','string')
        if not isinstance(selector,dict):raise ValueError('Sélecteur natif invalide.')
        text=selector.get('text',{});text=text if isinstance(text,dict) else {}
        secret=bool(SECRET.search(name) or text.get('type')=='password')
        spec={'name':name,'label':name.replace('_',' ').capitalize(),'required':item.get('required') is True,'kind':'secret' if secret else 'text','options':[]}
        if 'select'in selector:
            select=selector['select'];select=select if isinstance(select,dict)else{}
            spec.update(kind='multi' if select.get('multiple')else'select',options=choices(select.get('options',[])))
        elif item.get('options') is not None:
            spec.update(kind='multi' if kind=='multi_select'else'select',options=choices(item['options']))
        elif 'boolean'in selector or kind in ('boolean','bool'):spec['kind']='boolean'
        elif 'number'in selector or kind in ('integer','float','number'):
            spec['kind']='number';number=selector.get('number',{});number=number if isinstance(number,dict)else{}
            for key in ('min','max','step'):
                if type(number.get(key))in(int,float)and math.isfinite(number[key]):spec[key]=number[key]
        elif selector and not any(key in selector for key in ('text','object')):
            # These are native structured selectors, not stringified instructions.
            spec['kind']='json';spec['label']+=' (sélection avancée Home Assistant)'
        elif 'object'in selector or kind in ('dict','list','object'):spec['kind']='json'
        if spec['kind']in('boolean','number')and type(item.get('default'))in(bool,int,float)and scalar(item['default']):spec['default']=item['default']
        out.append(spec)
    if len({x['name']for x in out})!=len(out):raise ValueError('Champs natifs dupliqués.')
    return out


def authorization_url(value):
    if not isinstance(value,str)or len(value)>12000:return None
    p=urlparse(value)
    if p.scheme!='https'or not p.hostname or p.username or p.password:return None
    try:
        if not ipaddress.ip_address(p.hostname).is_global:return None
    except ValueError:
        if '.'not in p.hostname or p.hostname.endswith('.local'):return None
    return value


def public_flow(flow,domain):
    if not isinstance(flow,dict)or flow.get('handler',domain)!=domain:raise RuntimeError('Le parcours natif a changé de connexion.')
    kind=flow.get('type');fid=flow.get('flow_id','');step=flow.get('step_id','')
    if fid and(not isinstance(fid,str)or not ID.fullmatch(fid)):raise RuntimeError('Session native invalide.')
    if not isinstance(step,str)or len(step)>100:raise RuntimeError('Étape native invalide.')
    result={'flowId':fid,'step':step,'kind':kind,'fields':[],'choices':[],'retry':bool(flow.get('errors'))}
    if kind=='form':result['fields']=schema_fields(flow)
    elif kind=='menu':
        options=flow.get('menu_options',[])
        if not isinstance(options,list)or len(options)>50 or any(not isinstance(x,str)or not FIELD.fullmatch(x)for x in options):raise RuntimeError('Menu natif invalide.')
        result['choices']=[{'value':x,'label':x.replace('_',' ').capitalize()}for x in options]
    elif kind in ('external','show_progress','show_progress_done','external_done'):
        placeholders=flow.get('description_placeholders',{});placeholders=placeholders if isinstance(placeholders,dict)else{}
        url=authorization_url(flow.get('url')or placeholders.get('url')or placeholders.get('auth_url'))
        if url:result['authorizationUrl']=url
        code=placeholders.get('user_code')
        if isinstance(code,str)and re.fullmatch(r'[A-Z0-9 -]{4,30}',code):result['authorizationCode']=code
    elif kind=='abort':
        reason=flow.get('reason','unknown')
        result['reason']=reason if isinstance(reason,str)and re.fullmatch('[a-z_]{1,100}',reason)else'unknown'
    elif kind!='create_entry':raise RuntimeError('Ce type de parcours natif doit être vérifié.')
    return result


def validate_values(flow,values):
    if not isinstance(values,dict)or len(json.dumps(values))>16000:raise ValueError('Formulaire invalide.')
    if flow.get('type')=='menu':
        if set(values)!={'next_step_id'}or values['next_step_id']not in flow.get('menu_options',[]):raise ValueError('Choix natif invalide.')
        return values
    if flow.get('type')!='form':raise ValueError('Aucun formulaire ne doit être envoyé à cette étape.')
    fields=schema_fields(flow);names={f['name']for f in fields}
    if not set(values)<=names or any(f['required']and f['name']not in values for f in fields):raise ValueError('Complétez uniquement les champs demandés par l’intégration.')
    for f in fields:
        if f['name']not in values:continue
        v=values[f['name']];kind=f['kind']
        if kind in ('text','secret')and(not isinstance(v,str)or len(v)>4096):raise ValueError('Texte invalide.')
        if kind=='boolean'and type(v)is not bool:raise ValueError('Choix invalide.')
        if kind=='number'and(type(v)not in(int,float)or not math.isfinite(v)or v<f.get('min',-math.inf)or v>f.get('max',math.inf)):raise ValueError('Nombre hors limites.')
        allowed=[x['value']for x in f['options']]
        if kind=='select'and not any(type(v)is type(x)and v==x for x in allowed):raise ValueError('Choix non proposé par l’intégration.')
        if kind=='multi'and(not isinstance(v,list)or len(v)>500 or any(not any(type(y)is type(x)and y==x for x in allowed)for y in v)):raise ValueError('Sélection invalide.')
        if f['name']in('host','ip_address')and v not in ('auto',''):
            # Manual device entry is useful; public endpoints / Supervisor aren't.
            try:address=ipaddress.ip_address(v)
            except ValueError:
                if not isinstance(v,str)or not re.fullmatch(r'[a-zA-Z0-9-]+\.local',v):raise ValueError('Utilisez l’adresse IP locale ou le nom .local de votre appareil.')from None
            else:
                if address.version!=4 or not any(address in ipaddress.ip_network(n)for n in('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))or address in ipaddress.ip_network('172.30.32.0/23'):raise ValueError('L’adresse doit désigner un appareil du réseau de la maison.')
    return values


def configure(payload,call,*,registry,data=Path('/data'),clock=time.time):
    from equipment_setup import DOMAINS,active_entries,device_list
    operation=payload.get('operation');domain=payload.get('connector');owner=payload.get('ownerScope');session=payload.get('session')
    fields={'flow_start':{'session','cloudConsent'},'flow_resume':{'session'},'flow_advance':{'session','flowId','step','values','cloudConsent'},'flow_cancel':{'session'},'flow_authorize':{'session','flowId','state','code'}}
    if operation not in fields or set(payload)!={'operation','connector','ownerScope'}|fields[operation]or domain not in DOMAINS or not isinstance(owner,str)or not OWNER.fullmatch(owner)or not isinstance(session,str)or not UUID.fullmatch(session):raise ValueError('Parcours de connexion invalide.')
    cloud=domain in('netatmo','tado','home_connect','melcloud','panasonic_cc','smartthings','ring','overkiz','midea','tuya','wallbox','melcloud_home','growatt_server','solaredge')
    if operation in('flow_start','flow_advance')and(type(payload.get('cloudConsent'))is not bool or cloud and payload['cloudConsent']is not True):raise ValueError('Autorisez la connexion initiale au compte du fabricant.')
    data=Path(data);data.mkdir(exist_ok=True);path=data/'native-integration-flows.json'
    fd=os.open(data/'native-integration-flows.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);journal=json.loads(path.read_text())if path.exists()else{};state=journal.get(domain)
        def save():
            tmp=path.with_suffix('.tmp');fd=os.open(tmp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w')as f:json.dump(journal,f)
            tmp.replace(path)
        def view(flow):
            native=active_entries(call)
            return {'connector':domain,'status':'ready','entries':[e for e in native if e['domain']==domain],'devices':device_list(native,call,registry,domain),'discoveries':[],'pairingReady':any(e['domain']==domain and e['state']=='loaded'and not e['disabled']for e in native),'flow':flow}
        def credentials_form():
            return {'flowId':'application_credentials','step':'application_credentials','kind':'form','fields':[{'name':'client_id','label':'Identifiant d’application du fabricant','kind':'text','required':True,'options':[]},{'name':'client_secret','label':'Secret de l’application du fabricant','kind':'secret','required':True,'options':[]}],'choices':[],'retry':False,'title':'Autoriser cette application','description':'Ce fabricant demande les identifiants de son application développeur, distincts de votre mot de passe personnel. Ils seront conservés uniquement par Home Assistant sur votre box, comme dans son parcours natif. Suivez les prérequis indiqués par ce fabricant avant de continuer.'}
        def observe(reply):
            flow=public_flow(reply,domain)
            # Native French instructions include physical pairing confirmations.
            # Never return provider errors or interpolate credentials/placeholders.
            try:
                translated=registry({'type':'frontend/get_translations','language':'fr','category':'config','integration':[domain]})
                resources=translated.get('resources',{})if isinstance(translated,dict)else{}
            except Exception:resources={}
            prefix='component.'+domain+'.config.'
            for key in('title','description'):
                value=resources.get(prefix+'step.'+flow['step']+'.'+key)
                if isinstance(value,str)and len(value)<=4000:flow[key]=re.sub(r'\{[^{}]+\}','votre appareil',value)
            for field in flow['fields']:
                label=resources.get(prefix+'step.'+flow['step']+'.data.'+field['name'])
                if isinstance(label,str)and len(label)<=500:field['label']=label
            errors=reply.get('errors',{})
            reason=reply.get('reason')if flow['kind']=='abort'else errors.get('base')if isinstance(errors,dict)else None
            if isinstance(reason,str)and FIELD.fullmatch(reason):
                message=resources.get(prefix+('abort.'if flow['kind']=='abort'else'error.')+reason)
                if isinstance(message,str)and len(message)<=1000:flow['message']=re.sub(r'\{[^{}]+\}','votre appareil',message)
            if flow['kind']=='create_entry':
                created=reply.get('result',{});eid=created.get('entry_id')if isinstance(created,dict)else None
                if not eid or not any(e['entryId']==eid and e['domain']==domain for e in active_entries(call)):raise RuntimeError('L’intégration créée n’est pas encore vérifiable. Actualisez sans recommencer.')
                journal.pop(domain,None);save()
            elif flow['kind']=='abort':
                supported=registry({'type':'application_credentials/config'})if flow.get('reason')=='missing_credentials'else{}
                if flow.get('reason')=='missing_credentials'and isinstance(supported,dict)and domain in supported.get('domains',[]):
                    state.update(phase='credentials',step='application_credentials',flowId='application_credentials');save();return view(credentials_form())
                journal.pop(domain,None);save()
            else:
                if not flow['flowId']:raise RuntimeError('La session de l’intégration n’est pas vérifiable.')
                state.update(flowId=flow['flowId'],step=flow['step'],phase='ready');save()
            return view(flow)
        def owned_flow():
            if not state or state.get('ownerScope')!=owner or state.get('session')!=session:raise RuntimeError('Reprenez la connexion dans la session qui l’a ouverte.')
            fid=state.get('flowId')
            if not isinstance(fid,str)or not ID.fullmatch(fid):raise RuntimeError('Le démarrage reste à vérifier. Aucune seconde connexion n’a été lancée.')
            flow=call('/config/config_entries/flow/'+fid)
            if not isinstance(flow,dict)or flow.get('handler')!=domain or flow.get('flow_id')!=fid:raise RuntimeError('La session de connexion a changé.')
            return flow
        if operation=='flow_start':
            if domain=='midea':
                config=call('/config');version=str(config.get('version',''))if isinstance(config,dict)else''
                match=re.match(r'^(\d{4})\.(\d{1,2})\.',version)
                if not match or tuple(map(int,match.groups()))<(2026,8):return view({'flowId':'','step':'','kind':'abort','fields':[],'choices':[],'retry':False,'reason':'requires_home_assistant_2026_8'})
            if state:
                if state.get('phase')=='credentials'and state.get('ownerScope')==owner and state.get('session')==session:
                    if clock()>=state['expiresAt']:raise RuntimeError('La connexion a expiré. Annulez avant de recommencer.')
                    return view(credentials_form())
                flow=owned_flow()
                if clock()>=state['expiresAt']:raise RuntimeError('La connexion a expiré. Annulez-la avant de recommencer.')
                if state.get('phase')=='submitted'and flow.get('step_id')==state.get('step'):raise RuntimeError('Un envoi reste à vérifier. Annulez avant de recommencer ; les identifiants ne seront pas renvoyés.')
                return observe(flow)
            state={'ownerScope':owner,'session':session,'expiresAt':clock()+TTL,'phase':'starting'};journal[domain]=state;save()
            try:reply=call('/config/config_entries/flow',method='POST',payload={'handler':domain,'show_advanced_options':False})
            except urllib.error.HTTPError as error:
                if error.code in(400,404):
                    journal.pop(domain,None);save();return view({'flowId':'','step':'','kind':'abort','fields':[],'choices':[],'retry':False,'reason':'integration_not_available'})
                raise RuntimeError('Le démarrage de cette intégration reste à vérifier.')from None
            except Exception:
                # Unknown outcome: retain the lease rather than replaying a login.
                raise RuntimeError('Le démarrage de cette intégration reste à vérifier. Aucun nouvel essai automatique n’a été lancé.')from None
            return observe(reply)
        if state and state.get('phase')=='credentials':
            if state.get('ownerScope')!=owner or state.get('session')!=session:raise RuntimeError('Reprenez la connexion dans la session qui l’a ouverte.')
            if operation=='flow_cancel':
                journal.pop(domain,None);save();return view({'flowId':'','step':'','kind':'cancelled','fields':[],'choices':[],'retry':False})
            if clock()>=state['expiresAt']:raise RuntimeError('La connexion a expiré. Annulez avant de recommencer.')
            if operation=='flow_resume':return view(credentials_form())
            if operation!='flow_advance'or payload['flowId']!='application_credentials'or payload['step']!='application_credentials'or payload['cloudConsent']is not True:raise ValueError('Autorisez uniquement les identifiants d’application demandés.')
            values=payload['values']
            if not isinstance(values,dict)or set(values)!={'client_id','client_secret'}or any(not isinstance(v,str)or not 1<=len(v.strip())<=4096 for v in values.values()):raise ValueError('Renseignez les deux identifiants fournis par le fabricant.')
            # HA is the sole persistent secret store. A lost create response must
            # never cause automatic resubmission or modification of another app.
            state.update(phase='starting',flowId=None);save()
            registry({'type':'application_credentials/create','domain':domain,'client_id':values['client_id'],'client_secret':values['client_secret'],'name':'La Box'})
            return observe(call('/config/config_entries/flow',method='POST',payload={'handler':domain,'show_advanced_options':False}))
        if operation=='flow_cancel'and state and state.get('ownerScope')==owner and state.get('session')==session and not state.get('flowId'):
            # A lost initial response contains no credential submission. Explicit
            # cancellation releases our lease; it never removes an HA entry.
            journal.pop(domain,None);save()
            return view({'flowId':'','step':'','kind':'cancelled','fields':[],'choices':[],'retry':False})
        flow=owned_flow()
        if operation=='flow_authorize':
            # Forward only the current native OAuth state to HA's own signature
            # verifier. Never decode/sign a provider state or accept a target URL.
            if clock()>=state['expiresAt']or state.get('phase')!='ready'or flow.get('type')!='external'or payload.get('flowId')!=state['flowId']:raise ValueError('Autorisation expirée ou déjà transmise.')
            expected=parse_qs(urlparse(flow.get('url','')).query).get('state',[])
            code=payload.get('code');received=payload.get('state')
            if len(expected)!=1 or not isinstance(received,str)or len(received)>4096 or not hmac.compare_digest(expected[0],received)or not isinstance(code,str)or not 1<=len(code)<=4096:raise ValueError('Cette autorisation ne correspond pas à votre connexion.')
            state['phase']='submitted';save()
            call('/auth/external/callback?'+urlencode({'state':received,'code':code}),_configuration_callback=True)
            return observe(call('/config/config_entries/flow/'+state['flowId']))
        if operation=='flow_cancel':
            call('/config/config_entries/flow/'+state['flowId'],method='DELETE');journal.pop(domain,None);save()
            return view({'flowId':'','step':'','kind':'cancelled','fields':[],'choices':[],'retry':False})
        if clock()>=state['expiresAt']:raise RuntimeError('La connexion a expiré. Annulez avant de recommencer.')
        if operation=='flow_resume':
            if state.get('phase')=='submitted'and flow.get('step_id')==state.get('step'):raise RuntimeError('Un envoi reste à vérifier. Les informations ne seront pas renvoyées automatiquement.')
            if flow.get('type')in('external_done','show_progress_done'):
                state['phase']='submitted';save();return observe(call('/config/config_entries/flow/'+state['flowId'],method='POST',payload={}))
            return observe(flow)
        if state.get('phase')!='ready'or payload['flowId']!=state['flowId']or payload['step']!=flow.get('step_id'):raise RuntimeError('Le formulaire a changé. Actualisez cette connexion.')
        values=validate_values(flow,payload['values']);state.update(phase='submitted',step=flow.get('step_id'));save()
        try:reply=call('/config/config_entries/flow/'+state['flowId'],method='POST',payload=values)
        except Exception:raise RuntimeError('L’envoi reste à vérifier. Actualisez sans renvoyer vos identifiants.')from None
        return observe(reply)
