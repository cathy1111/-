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
        fingerprint=rules[0]['page_fingerprint']
        v,p,notes=app.apply_confirmed_rules('A车2.0阶段配重明细表','204','河眺宽万',rules,fingerprint)
        self.assertEqual((v,p),('A204','河北官厅'))
        self.assertEqual(len(notes),2)
        self.assertEqual(app.apply_confirmed_rules('B车配重明细表','204','河眺宽万',rules)[:2],('204','河眺宽万'))
        self.assertEqual(app.apply_confirmed_rules('A车配重明细表','B204','其他地点',rules)[:2],('B204','其他地点'))
        self.assertEqual(app.apply_confirmed_rules('A车配重明细表','','',rules)[:2],('',''))
        self.assertEqual(app.apply_confirmed_rules('A车配重明细表','','',rules,fingerprint)[:2],('A204','河北官厅'))
    def test_confirmed_correction_does_not_affect_other_acceleration_pages(self):
        rules=app.load_confirmed_rules(Path(__file__).parent/'field_rules.json')
        rule=next(r for r in rules if r['experiment_contains']=='加速性能试验记录表')
        self.assertEqual(app.apply_confirmed_rules('加速性能试验记录表','A04','河北官厅',rules,'another-page')[:2],('A04','河北官厅'))
        self.assertEqual(app.apply_confirmed_rules('加速性能试验记录表','A04','河北官厅',rules,rule['page_fingerprint'])[:2],('A204','河北官厅'))
    def test_units_are_not_places(self):
        for value in ["'C",'℃','C','KM','25.9℃','天气晴','湿度65%','1234']:
            self.assertEqual(app.parse_place_value(value),'')
        self.assertEqual(app.parse_place_value('河北官厅'),'河北官厅')
        self.assertEqual(app.parse_place_value('MIRA'),'MIRA')

    def test_temperature_fallback_is_removed_and_known_page_restored(self):
        rules=app.load_confirmed_rules(Path(__file__).parent/'field_rules.json')
        fp=next(r['page_fingerprint'] for r in rules if r['experiment_contains']=='加速性能试验记录表')
        B=app.OCRBox
        header=[B(10,20,300,40,'加速性能试验记录表',.99),B(10,60,160,80,'试验时间2026年7月23日',.99),B(200,60,300,80,'车号A04',.9)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'sample.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(src)
            with patch.object(app,'ocr_boxes',side_effect=[header,[]]),patch.object(app,'retry_labelled_field',return_value=''),patch.object(app,'page_fingerprint',return_value=fp),patch.object(app,'extract_fields',return_value=('加速性能试验记录表','A04','2026年7月23日','20260723',"'C",'')):
                result=app.scan_pdf(src)[0]
            self.assertEqual(result.vehicle,'A204')
            self.assertEqual(result.location_raw,'河北官厅')
            self.assertEqual(result.vehicle_raw,'A04')
            self.assertEqual(result.location_ocr_raw,"'C")
            self.assertEqual(result.filename_base,'加速性能试验记录表-A204-20260723-河北官厅')

    def test_location_cell_retry_rejects_units_and_conflicts(self):
        B=app.OCRBox
        with fitz.open() as doc:
            page=doc.new_page()
            anchors=[B(50,100,130,120,'试验地点',.99)]
            with patch.object(app,'ocr_boxes',return_value=[B(1,1,50,20,"'C",.9)]):
                self.assertEqual(app.retry_labelled_field(page,anchors,app.PLACE_LABEL,app.parse_place_value,None,0,'place'),'')
            with patch.object(app,'ocr_boxes',return_value=[B(1,1,90,20,'河北官厅',.9)]):
                self.assertEqual(app.retry_labelled_field(page,anchors,app.PLACE_LABEL,app.parse_place_value,None,0,'place'),'河北官厅')
            with patch.object(app,'ocr_boxes',side_effect=[[B(1,1,90,20,'河北官厅',.9)],[B(1,1,90,20,'另一地点',.9)]]):
                self.assertEqual(app.retry_labelled_field(page,anchors,app.PLACE_LABEL,app.parse_place_value,None,0,'place'),'')
    def test_instrument_expiry_is_not_used_as_test_date(self):
        B=app.OCRBox
        header=[B(10,20,300,40,'其他试验记录表',.99),B(10,100,170,120,'试验地点河北官厅',.99),B(200,100,300,120,'车号E202',.9)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'sample.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(src)
            with patch.object(app,'ocr_boxes',side_effect=[header,[]]),patch.object(app,'retry_labelled_field',return_value=''),patch.object(app,'extract_fields',return_value=('其他试验记录表','E202','2027年7月1日','20270701','河北官厅','')):
                result=app.scan_pdf(src)[0]
            self.assertEqual(result.time_code,'')
            self.assertEqual(result.location_raw,'河北官厅')

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
