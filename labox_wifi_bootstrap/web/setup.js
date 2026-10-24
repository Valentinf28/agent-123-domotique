'use strict';
const form=document.querySelector('#wifi'),button=document.querySelector('#connect'),result=document.querySelector('#result');
let token='',pending=false;
const messages={connexion_wifi_refusee:'La connexion Wi-Fi a échoué. Vérifiez le nom du réseau, le mot de passe et la proximité du routeur.',adresse_ip_non_obtenue:'Le routeur n’a pas attribué d’adresse à la box. Vérifiez son fonctionnement puis réessayez.',connexion_wifi_non_confirmee:'La connexion n’a pas pu être confirmée. Vérifiez le réseau et réessayez.',internet_non_confirme:'Le Wi-Fi a été rejoint, mais l’accès au portail n’a pas pu être confirmé. Vérifiez la connexion Internet du routeur puis réessayez.',tentative_interrompue:'La tentative précédente a été interrompue. Vous pouvez réessayer.',mot_de_passe_invalide:'Le mot de passe doit contenir 8 à 63 caractères ASCII, ou une clé hexadécimale de 64 caractères.',nom_wifi_invalide:'Vérifiez le nom du réseau.',trop_de_demandes:'Patientez une minute avant de réessayer.'};
document.querySelector('#show').addEventListener('change',e=>{document.querySelector('#password').type=e.target.checked?'text':'password';});
async function refresh(){
 try{
  const [session,status]=await Promise.all([fetch('/api/session',{cache:'no-store'}).then(r=>r.json()),fetch('/api/status',{cache:'no-store'}).then(r=>r.json())]);
  token=session.token;
  const list=document.querySelector('#networks');list.replaceChildren();
  for(const network of status.networks){if(!network.supported)continue;const option=document.createElement('option');option.value=network.ssid;list.append(option);}
  if(status.error)result.textContent=messages[status.error]||'La connexion n’a pas pu être confirmée. Réessayez ou contactez votre installateur.';
  button.disabled=status.phase!=='hotspot';pending=false;
 }catch(_){result.textContent='Reconnectez votre téléphone au réseau LaBox-… puis rouvrez cette page.';}
}
form.addEventListener('submit',async event=>{
 event.preventDefault();if(pending)return;pending=true;button.disabled=true;
 result.textContent='La connexion va être testée. Le réseau LaBox-… va disparaître. Patientez jusqu’à 2 min 30. S’il réapparaît, reconnectez-vous à celui-ci puis rouvrez cette page. Sinon, rejoignez le Wi-Fi de votre maison et ouvrez votre espace client.';
 try{
  const response=await fetch('/api/connect',{method:'POST',headers:{'Content-Type':'application/json','X-Setup-Token':token},body:JSON.stringify({ssid:document.querySelector('#ssid').value,password:document.querySelector('#password').value})});
  document.querySelector('#password').value='';const data=await response.json();
  if(response.status!==202){result.textContent=messages[data.error]||'La demande n’a pas été acceptée. Rouvrez cette page et réessayez.';pending=false;button.disabled=false;}
 }catch(_){document.querySelector('#password').value='';}
});
refresh();
