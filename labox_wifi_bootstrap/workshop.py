"""Run locally inside the prepared app. Explicit private QR label export only."""
import argparse
import html
import json
import re
import os
from pathlib import Path
import qrcode
import qrcode.image.svg
from io import BytesIO
from model import IP, PORT, read

def wifi_qr(data):
    def escape(s):
        for c in ('\\', ';', ',', ':', '"'): s = s.replace(c, '\\' + c)
        return s
    return 'WIFI:T:WPA;S:' + escape(data['ssid']) + ';P:' + escape(data['psk']) + ';;'

def label(data):
    if data.get('phase') not in ('ready', 'hotspot'):
        raise ValueError('Étiquette réservée à une box neuve préparée.')
    stream = BytesIO()
    qrcode.make(wifi_qr(data), image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=4).save(stream)
    return ('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Première connexion La Box</title>'
            '<style>body{font:16px system-ui;max-width:460px;margin:30px auto;padding:24px;border:1px solid #555}'
            'svg{width:230px;height:230px;display:block;margin:auto}h1{font-size:25px}code{font-size:18px}</style>'
            '<h1>Connecter votre box en Wi-Fi</h1><p>1. Branchez La Box et attendez son démarrage.</p>'
            '<p>2. Scannez ce code avec votre téléphone et rejoignez le Wi-Fi de configuration.</p>'
            + stream.getvalue().decode() + '<p>Réseau : <strong>' + html.escape(data['ssid']) + '</strong><br>'
            'Clé : <code>' + html.escape(data['psk']) + '</code></p><p>3. Ouvrez <strong>http://' + IP + ':' + str(PORT)
            + '</strong> et choisissez le Wi-Fi de votre maison.</p><p>Si le téléphone indique « Sans Internet », '
            'restez connecté le temps de la configuration. Le réseau de configuration s’arrêtera une fois la box connectée.</p></html>')

def identification(data, product='box'):
    """Allowlist for the offline workshop renderer. No factory/owner/technician secret."""
    if data.get('phase') not in ('ready', 'hotspot') or product not in ('box', 'console'):
        raise ValueError('Préparation atelier non valide.')
    if not re.fullmatch(r'[a-f0-9]{64}', data.get('context', '')):
        raise ValueError('Identité atelier absente.')
    if not re.fullmatch(r'[A-HJ-NP-Z2-9]{8}', data.get('psk', '')):
        raise ValueError('Cette identité conserve son ancien code : ne pas le modifier après étiquetage.')
    return {'schema':'labox.workshop-identification.v1','product':product,
            'factoryContext':data['context'],'ssid':data['ssid'],'wifiCode':data['psk']}

def main():
    parser = argparse.ArgumentParser(description='Exporter les supports privés de cette unité, sans modifier le réseau.')
    parser.add_argument('--state', default='/data/onboarding.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--format', choices=['html','identification'], default='identification')
    parser.add_argument('--product', choices=['box','console'], default='box')
    args = parser.parse_args()
    data = read(args.state)
    value = label(data) if args.format == 'html' else json.dumps(identification(data,args.product),indent=2)+'\n'
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(value)
    print('Export privé créé. Le code reste celui configuré sur cet appareil.')

if __name__ == '__main__': main()
