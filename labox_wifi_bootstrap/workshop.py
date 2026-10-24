"""Run locally inside the prepared app. Explicit private QR label export only."""
import argparse
import html
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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Exporter l’étiquette privée de cette box, sans modifier le réseau.')
    parser.add_argument('--state', default='/data/onboarding.json')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    value = label(read(args.state))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(value)
    print('Étiquette privée créée. Ne pas la copier dans une image atelier ou un dépôt Git.')
