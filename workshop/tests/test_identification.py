import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from identification import validated_identity, reference, export_kit, render_label, render_engraving, DEFAULT_MAKER, default_font


def identity(**changes):
    return {'schema':'labox.workshop-identification.v1','product':'box',
            'factoryContext':'a'*64,'ssid':'LaBox-A4C7E2F9','wifiCode':'A7K3P9M2',**changes}


class WorkshopTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def test_only_real_eight_character_mixed_uppercase_codes(self):
        self.assertEqual(validated_identity(identity())['wifiCode'],'A7K3P9M2')
        for code in ['abcdefgh','12345678','ABCDEFGH','A7K3P9M','A7K3P9M20','A7K3P9O2',None]:
            with self.subTest(code=code),self.assertRaises(ValueError):validated_identity(identity(wifiCode=code))

    def test_serial_and_ssid_share_suffix_but_not_wifi_secret(self):
        self.assertEqual(reference(identity()),'LB-A4C7E2F9')
        self.assertEqual(reference(identity(product='console',ssid='LaConsole-B6D3F8A2')),'LC-B6D3F8A2')
        with self.assertRaises(ValueError):reference(identity(product='console'))

    def test_foreign_secret_fields_are_excluded(self):
        raw=identity(factory_token='DO-NOT-EXPORT',technician_code='DO-NOT-EXPORT',home_wifi_password='DO-NOT-EXPORT')
        self.assertNotIn('DO-NOT-EXPORT',json.dumps(validated_identity(raw)))

    def test_pair_of_labels_matches_without_exposing_wifi_password(self):
        for role in ['boitier-chene','carte-odroid']:
            drawing=render_label(identity(),role,54,25,default_font(),default_font(True))
            self.assertIn('LB-A4C7E2F9',drawing.texts)
            self.assertNotIn('A7K3P9M2',' '.join(drawing.texts))

    def test_engraving_has_serial_and_password_without_network_name(self):
        drawing=render_engraving(identity(),DEFAULT_MAKER,default_font(),default_font(True),True)
        self.assertIn(reference(identity()),drawing.texts)
        self.assertIn(identity()['wifiCode'],drawing.texts)
        self.assertNotIn(identity()['ssid'],' '.join(drawing.texts))

    def test_complete_private_kit_dimensions_and_outlined_svg(self):
        target=self.root/'unit';facts=export_kit(identity(),target)
        self.assertEqual(facts['reference'],'LB-A4C7E2F9');self.assertFalse(facts['markingReviewed'])
        self.assertFalse(facts['dymoFormatConfirmed'])
        self.assertEqual(stat.S_IMODE(target.stat().st_mode),0o700)
        for p in target.iterdir():self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
        root=ET.parse(target/'maquette-gravure.svg').getroot()
        self.assertEqual((root.attrib['width'],root.attrib['height']),('80mm','45mm'))
        for tag in ['text','image','script','foreignObject']:
            self.assertEqual(root.findall('.//{http://www.w3.org/2000/svg}'+tag),[])
        with Image.open(target/'maquette-gravure.png')as im:
            self.assertEqual(im.size,(1890,1063));self.assertAlmostEqual(im.info['dpi'][0],600,delta=.1)
        self.assertEqual((target/'imprimer-etiquettes.html').read_text().count('<section>'),2)
        self.assertEqual(json.loads((target/'identification-private.json').read_text()),identity())
        with self.assertRaises(FileExistsError):export_kit(identity(),target)
        with self.assertRaises(ValueError):export_kit(identity(factoryContext='b'*64),self.root/'collision')
        self.assertFalse((self.root/'collision').exists())

    def test_bad_dimensions_and_unreadable_text_leave_no_partial_kit(self):
        with self.assertRaises(ValueError):export_kit(identity(),self.root/'small',label_size=(40,20))
        with self.assertRaises(ValueError):export_kit(identity(),self.root/'overflow',maker={'name':'W'*120})
        self.assertEqual(list(self.root.iterdir()),[])


if __name__=='__main__':unittest.main()
