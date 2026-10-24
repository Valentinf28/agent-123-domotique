"""Offline label and engraving export. Never creates or changes a device credential."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
PRODUCTS = {'box': ('LA BOX', 'LB', 'LB-B01'), 'console': ('CONSOLE', 'LC', 'LB-C01')}
DEFAULT_MAKER = {
    'name': 'SAS 123 PANNEAUX SOLAIRES',
    'street': '14 rue du Vieux Pont',
    'city': '28380 Saint-Rémy-sur-Avre · France',
    'website': '123panneaux-solaires.fr',
    'boxInput': 'Entrée : à confirmer sur le produit assemblé',
    'consoleInput': 'Entrée : à confirmer sur le produit assemblé',
    'markingReviewed': False,
}


def validated_identity(data):
    if data.get('schema') != 'labox.workshop-identification.v1' or data.get('product') not in PRODUCTS:
        raise ValueError('Export atelier non reconnu.')
    if not re.fullmatch('[a-f0-9]{64}', str(data.get('factoryContext', ''))):
        raise ValueError('Identité atelier manquante.')
    code = data.get('wifiCode', '')
    if not isinstance(code, str) or not re.fullmatch('[A-HJ-NP-Z2-9]{8}', code) or not any(c.isdigit() for c in code) or not any(c.isalpha() for c in code):
        raise ValueError('Le code réellement configuré doit comporter huit chiffres et lettres majuscules.')
    ssid = data.get('ssid')
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 for c in ssid):
        raise ValueError('Nom Wi-Fi invalide.')
    # Do not carry arbitrary source fields (including technician or activation secrets).
    return {k: data[k] for k in ('schema', 'product', 'factoryContext', 'ssid', 'wifiCode')}


def reference(data):
    prefix = 'LaBox-' if data['product']=='box' else 'LaConsole-'
    if not re.fullmatch(re.escape(prefix)+r'[A-F0-9]{8}',data['ssid']):
        raise ValueError('Le nom réseau doit correspondre à la référence de cette unité.')
    return PRODUCTS[data['product']][1] + '-' + data['ssid'].split('-',1)[1]


def default_font(bold=False):
    candidates = ([Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
                   Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')] if bold else
                  [Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
                   Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')])
    return next((p for p in candidates if p.is_file()), None)


class Drawing:
    def __init__(self, width, height, regular, bold, dpi=600):
        if not 35 <= width <= 150 or not 18 <= height <= 100 or not 150 <= dpi <= 1200:
            raise ValueError('Dimensions ou résolution hors plage.')
        self.width, self.height, self.ppm = width, height, dpi / 25.4
        self.fonts = {False: TTFont(regular), True: TTFont(bold)}
        self.font_paths = {False: str(regular), True: str(bold)}
        self.parts, self.texts = [], []
        self.image = Image.new('RGB', (round(width*self.ppm), round(height*self.ppm)), 'white')
        self.raster = ImageDraw.Draw(self.image)
        self.dpi = dpi

    def text(self, value, x, baseline, size, bold=False, max_width=None):
        font = self.fonts[bold]
        glyphs, cmap, units = font.getGlyphSet(), font.getBestCmap(), font['head'].unitsPerEm
        if any(ord(c) not in cmap for c in value):
            raise ValueError('Caractère absent de la police.')
        names = [cmap[ord(c)] for c in value]
        advance = sum(glyphs[n].width for n in names)
        scale = size/units
        if max_width and advance*scale > max_width:
            scale = max_width/advance
        if size*scale/(size/units) < 1.35:
            raise ValueError('Texte trop petit pour ce format. Agrandir le support.')
        cursor = x
        for name in names:
            pen = SVGPathPen(glyphs)
            transform = (scale, 0, 0, -scale, cursor, baseline)
            glyphs[name].draw(TransformPen(pen, transform))
            bounds = BoundsPen(glyphs)
            glyphs[name].draw(TransformPen(bounds, transform))
            if bounds.bounds:
                a,b,c,d = bounds.bounds
                if a < .4 or b < .4 or c > self.width-.4 or d > self.height-.4:
                    raise ValueError('Texte hors de la zone utile.')
            path = pen.getCommands()
            if path:
                self.parts.append(f'<path fill="#000000" d="{path}"/>')
            cursor += glyphs[name].width*scale
        pixel_size = max(1, round(scale*units*self.ppm))
        raster_font = ImageFont.truetype(self.font_paths[bold], pixel_size)
        self.raster.text((x*self.ppm, baseline*self.ppm), value, font=raster_font, fill='black', anchor='ls')
        self.texts.append(value)

    def line(self, x1,y1,x2,y2,width=.15):
        length=math.hypot(x2-x1,y2-y1)
        if not length:return
        nx,ny=-(y2-y1)*width/(2*length),(x2-x1)*width/(2*length)
        self.parts.append(f'<path fill="#000000" d="M{x1+nx} {y1+ny}L{x2+nx} {y2+ny}L{x2-nx} {y2-ny}L{x1-nx} {y1-ny}Z"/>')
        self.raster.line(tuple(v*self.ppm for v in (x1,y1,x2,y2)), fill='black', width=max(1,round(width*self.ppm)))

    def brand(self, x, y, size):
        path = 'M14 12H86V16H90V84H86V88H14V84H10V16H14Z M26 26V74H74V26Z'
        self.parts.append(f'<g transform="translate({x} {y}) scale({size/100})"><path transform="rotate(-12 50 50)" fill="#000000" fill-rule="evenodd" d="{path}"/></g>')
        outer = [(14,12),(86,12),(90,16),(90,84),(86,88),(14,88),(10,84),(10,16)]
        inner = [(26,26),(26,74),(74,74),(74,26)]
        for pts,color in [(outer,'black'),(inner,'white')]:
            angle=-12*math.pi/180
            rotated=[((x+size*(50+(a-50)*math.cos(angle)-(b-50)*math.sin(angle))/100)*self.ppm,
                      (y+size*(50+(a-50)*math.sin(angle)+(b-50)*math.cos(angle))/100)*self.ppm) for a,b in pts]
            self.raster.polygon(rotated, fill=color)

    def marks(self, x, y):
        # CE geometry taken unchanged from the Commission's official EPS, 6 mm high.
        ce = ET.parse(ROOT/'assets/ce-official.svg').getroot()
        self.parts.append(f'<g fill="#000000" transform="translate({x} {y}) scale(.01)">')
        for p in ce:
            self.parts.append(f'<path d="{p.attrib["d"]}"/>')
        self.parts.append('</g>')
        # Draw the same CE curves on the raster, without substituting a font.
        from fontTools.pens.recordingPen import RecordingPen
        from fontTools.svgLib.path import parse_path
        for p in ce:
            pen=RecordingPen(); parse_path(p.attrib['d'], pen)
            points=[]; current=None
            for op,args in pen.value:
                if op=='moveTo': current=args[0]; points.append(current)
                elif op=='lineTo': current=args[0]; points.append(current)
                elif op=='curveTo':
                    a=current; b,c,d=args
                    for i in range(1,33):
                        t=i/32; points.append(((1-t)**3*a[0]+3*(1-t)**2*t*b[0]+3*(1-t)*t*t*c[0]+t**3*d[0],
                                                   (1-t)**3*a[1]+3*(1-t)**2*t*b[1]+3*(1-t)*t*t*c[1]+t**3*d[1]))
                    current=d
            self.raster.polygon([((x+a*.01)*self.ppm,(y+b*.01)*self.ppm) for a,b in points], fill='black')
        # Crossed-out wheeled bin with the post-2005 bar, provisional reproduction.
        bx,by=x+11,y-1
        primitives=[('M2 2H7L6.5 7H2.5Z M2.4 2.4L2.85 6.6H6.15L6.6 2.4Z',True),
                    ('M1.6 1.5H7.5V2H1.6Z',False),('M3.3 .7H5.6V1.5H5.2V1.1H3.7V1.5H3.3Z',False),
                    ('M.6 .5L8.4 7.8L8.1 8.1L.3 .8Z',False),('M8.1 .3L.3 7.8L.6 8.1L8.4 .6Z',False),
                    ('M1 9H7.7V10H1Z',False)]
        self.parts.append(f'<g transform="translate({bx} {by})" fill="#000000" fill-rule="evenodd">'+''.join(f'<path d="{p}"/>' for p,_ in primitives)+'<circle cx="6.7" cy="7.4" r=".65"/></g>')
        # Raster of the same simple bin geometry.
        def line(a,b,c,d,w=.35):self.raster.line(tuple(v*self.ppm for v in (bx+a,by+b,bx+c,by+d)), fill='black',width=max(1,round(w*self.ppm)))
        for a,b,c,d in [(2,2,7,2),(7,2,6.5,7),(6.5,7,2.5,7),(2.5,7,2,2),(1.6,1.7,7.5,1.7),(3.3,1.5,3.3,.7),(3.3,.7,5.6,.7),(5.6,.7,5.6,1.5),(.5,.5,8.3,8),(8.3,.5,.5,8),(1,9.5,7.7,9.5)]:line(a,b,c,d,.4 if b!=9.5 else 1)
        self.raster.ellipse(tuple(v*self.ppm for v in (bx+6.05,by+6.75,bx+7.35,by+8.05)),fill='black')

    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}mm" height="{self.height}mm" viewBox="0 0 {self.width} {self.height}">'
                '<title>Support privé de repérage et de configuration La Box</title>'+''.join(self.parts)+'</svg>')

    def save(self, folder, name):
        (folder/(name+'.svg')).write_text(self.svg())
        self.image.save(folder/(name+'.png'), dpi=(self.dpi,self.dpi))


def render_engraving(data, maker, font, bold, demo=False):
    d=Drawing(80,45,font,bold)
    d.brand(3,2.4,6)
    d.text('La Box',11,7,3.8,True)
    product,_,model=PRODUCTS[data['product']]
    d.text('BOX DOMOTIQUE' if data['product']=='box' else 'CONSOLE',54,6.8,2.5,True,max_width=23)
    d.text('Modèle '+model,3,11.3,2,max_width=74)
    d.line(3,13,77,13)
    d.text('N° DE SÉRIE',3,17,1.8,True)
    d.text(reference(data),3,23.5,3.6,True,max_width=38)
    d.text('MOT DE PASSE WI-FI',45,17,1.8,True)
    d.text(data['wifiCode'],45,24,5.5,True,max_width=32)
    d.text(maker[data['product']+'Input'],3,31,1.7,max_width=74)
    d.text(maker['name'],3,34.6,1.9,True,max_width=52)
    d.text(maker['street'],3,37.4,1.8,max_width=52)
    d.text(maker['city'],3,40.2,1.8,max_width=52)
    d.marks(57,33.2)
    caption='SPÉCIMEN · CODE FICTIF · MARQUAGES À VALIDER' if demo else 'MAQUETTE · MARQUAGES À VALIDER'
    if demo or not maker.get('markingReviewed'):
        d.text(caption,3,43.5,1.45,True,max_width=74)
    return d


def render_label(data, role, width, height, font, bold, demo=False):
    d=Drawing(width,height,font,bold,300)
    title=('LA BOX' if data['product']=='box' else 'LA BOX · CONSOLE')+' · '+('BOÎTIER CHÊNE' if role=='boitier-chene' else 'CARTE ODROID')
    d.text(title,2,4.4,2.2,True,max_width=width-4)
    d.text(reference(data),2,9.5,3.1,True,max_width=width-4)
    d.line(2,11,width-2,11)
    d.text('Même référence sur la gravure finale',2,14.5,1.6,max_width=width-4)
    d.text('Assemblage : associer les deux références',2,17.4,1.45,max_width=width-4)
    d.text('SPÉCIMEN' if demo else 'REPÉRAGE ATELIER',2,21.5,1.6,True,max_width=width-4)
    return d


def export_kit(raw, output, maker=None, label_size=(54,25), font=None, bold=None, demo=False):
    data=validated_identity(raw); maker={**DEFAULT_MAKER,**(maker or {})}
    for key in ('name','street','city','website','boxInput','consoleInput'):
        if not isinstance(maker[key],str) or not maker[key] or len(maker[key])>120 or any(ord(c)<32 for c in maker[key]):
            raise ValueError('Coordonnées ou caractéristiques invalides.')
    font,bold=font or default_font(),bold or default_font(True)
    if not font or not bold:raise ValueError('Fournir les polices locales --font et --bold-font.')
    if label_size[0]<45 or label_size[1]<24:raise ValueError('Utiliser au moins 45 × 24 mm pour ce gabarit.')
    output=Path(output)
    if output.exists():raise FileExistsError('Le dossier existe déjà. Réimprimer le même kit sans régénérer le code.')
    output.parent.mkdir(parents=True,exist_ok=True)
    # A short reference collision or changed engraved code must stop production.
    for previous in output.parent.glob('*/controle-atelier.json'):
        saved=json.loads(previous.read_text())
        if not demo and not saved.get('demo') and saved.get('reference')==reference(data):
            current=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
            if saved.get('sourceIdentityFingerprint')!=current:
                raise ValueError('Référence déjà utilisée pour une autre identité ou un autre code.')
    temp=Path(tempfile.mkdtemp(prefix='.identification-',dir=output.parent));temp.chmod(0o700)
    try:
        engraving=render_engraving(data,maker,font,bold,demo);engraving.save(temp,'maquette-gravure' if demo or not maker['markingReviewed'] else 'gravure-lightburn')
        labels=[]
        for role in ('boitier-chene','carte-odroid'):
            drawing=render_label(data,role,*label_size,font,bold,demo);drawing.save(temp,role);labels.append(drawing.svg())
        style=f'@page{{size:{label_size[0]}mm {label_size[1]}mm;margin:0}}html,body{{margin:0;padding:0}}section{{width:{label_size[0]}mm;height:{label_size[1]}mm;break-after:page;overflow:hidden}}svg{{display:block}}'
        (temp/'imprimer-etiquettes.html').write_text('<!doctype html><html lang="fr"><meta charset="utf-8"><title>Repérage atelier</title><style>'+style+'</style>'+''.join('<section>'+svg+'</section>'for svg in labels)+'</html>')
        # The source credential stays in this private per-device folder for exact reprints.
        (temp/'identification-private.json').write_text(json.dumps(data,indent=2)+'\n')
        (temp/'fabricant.json').write_text(json.dumps(maker,indent=2,ensure_ascii=False)+'\n')
        facts={'reference':reference(data),'product':data['product'],'demo':demo,'engravingMm':[80,45],
               'dymoMm':list(label_size),'dymoFormatConfirmed':False,'markingReviewed':bool(maker['markingReviewed']),
               'wifiCodeFingerprint':hashlib.sha256(data['wifiCode'].encode()).hexdigest(),
               'sourceIdentityFingerprint':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}
        (temp/'controle-atelier.json').write_text(json.dumps(facts,indent=2)+'\n')
        (temp/'LIRE-AVANT-FABRICATION.txt').write_text('Gravure : SVG en millimètres, textes vectorisés. Importer dans LightBurn, vérifier 80 × 45 mm ; les bords du document ne sont pas un contour de découpe. Réglages laser à qualifier sur une chute du même chêne. Aucun réglage laser/G-code n’est fourni.\nÉtiquettes : deux pages au format choisi, même référence pour le boîtier et la carte. Imprimer à 100 %, sans ajustement automatique. Taille et marges à adapter au modèle Dymo.\nLe code vient de l’appareil ; ne pas fabriquer un autre code pour la même carte. Aucun code SAV, token usine, code d’activation ou mot de passe Wi-Fi maison n’est inclus.\nLa maquette CE/DEEE ne vaut pas déclaration de conformité. Fabricant, modèle, alimentation et marquages doivent correspondre au produit assemblé. La console doit disposer de son propre export d’identité ; le gabarit ne lui installe pas un point d’accès Wi-Fi.\n')
        for p in temp.iterdir():p.chmod(0o600)
        # Rename on the same filesystem, refusing an existing unit kit.
        if output.exists():raise FileExistsError('Dossier déjà créé.')
        temp.rename(output)
        return facts
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--identity',type=Path);source.add_argument('--demo',action='store_true')
    parser.add_argument('--product',choices=PRODUCTS,default='box',help='uniquement pour la démonstration')
    parser.add_argument('--maker',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--label-width',type=float,default=54);parser.add_argument('--label-height',type=float,default=25)
    parser.add_argument('--font',type=Path);parser.add_argument('--bold-font',type=Path)
    args=parser.parse_args()
    data=(json.loads(args.identity.read_text()) if args.identity else
          {'schema':'labox.workshop-identification.v1','product':args.product,'factoryContext':('a' if args.product=='box' else 'b')*64,'ssid':'LaBox-A4C7E2F9' if args.product=='box' else 'LaConsole-B6D3F8A2','wifiCode':'A7K3P9M2'})
    maker=json.loads(args.maker.read_text()) if args.maker else None
    export_kit(data,args.output,maker,(args.label_width,args.label_height),args.font,args.bold_font,args.demo)
    print('Kit créé : deux étiquettes et un visuel de gravure. Aucun appareil ni imprimante modifié.')


if __name__=='__main__':main()
