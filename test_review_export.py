import argparse
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
import split_experiments as app

class ReviewTests(unittest.TestCase):
    def test_confirmed_rules_are_scoped_and_exact(self):
        rules=app.load_confirmed_rules(Path(__file__).parent/'field_rules.json')
        v,p,notes=app.apply_confirmed_rules('A车2.0阶段配重明细表','204','河眺宽万',rules)
        self.assertEqual((v,p),('A204','河北官厅'))
        self.assertEqual(len(notes),2)
        self.assertEqual(app.apply_confirmed_rules('B车配重明细表','204','河眺宽万',rules)[:2],('204','河眺宽万'))
        self.assertEqual(app.apply_confirmed_rules('A车配重明细表','B204','其他地点',rules)[:2],('B204','其他地点'))
        self.assertEqual(app.apply_confirmed_rules('A车配重明细表','','',rules)[:2],('',''))
    def test_reviewer_edits_are_exported_without_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'input.pdf';out=root/'out'
            with fitz.open() as doc:doc.new_page();doc.save(src)
            meta=app.PageMeta(0,'A车配重明细表','204','2026年7月23日','20260723','河眺宽万','key','old',vehicle_raw='204',location_ocr_raw='河眺宽万')
            app.write_preview_csv([meta],out/'preview.csv','V011')
            app.write_preview_identity(src,out)
            with (out/'preview.csv').open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            rows[0]['车号']='A204';rows[0]['试验地点']='河北官厅'
            with (out/'preview.csv').open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
            args=argparse.Namespace(input=str(src),out=str(out),version='V011',rescan=False,top_ratio=.4,max_pages=None)
            with patch.object(app,'scan_pdf',side_effect=AssertionError('OCR must not run during reviewed export')):
                self.assertEqual(app.cmd_split(args),0)
            files=list(out.glob('*.pdf'));self.assertEqual(len(files),1)
            self.assertEqual(files[0].name,'A车配重明细表-A204-20260723-河北官厅-V011.pdf')
            loaded=app.load_preview_csv(out/'preview.csv')[0]
            self.assertEqual(loaded.vehicle_raw,'204')
            self.assertEqual(loaded.location_ocr_raw,'河眺宽万')
    def test_wrong_source_and_missing_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';src=root/'a.pdf';other=root/'b.pdf'
            for path,words in [(src,'A'),(other,'B')]:
                with fitz.open() as doc:
                    page=doc.new_page();page.insert_text((30,30),words);doc.save(path)
            with self.assertRaises(ValueError):app.verify_preview_identity(src,out)
            app.write_preview_identity(src,out)
            self.assertEqual(app.verify_preview_identity(src,out),1)
            with self.assertRaises(ValueError):app.verify_preview_identity(other,out)

if __name__=='__main__':unittest.main()
