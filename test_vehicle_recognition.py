import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
import split_experiments as app

B=app.OCRBox
class VehicleTests(unittest.TestCase):
    def test_labelled_formats(self):
        for raw, expected in [('车号：E202','E202'),('车 号：Ａ２０４','A204'),('车辆编号：00123','00123'),('试验车号：AB0123','AB0123'),('车号E202里程100km','E202')]:
            self.assertEqual(app.labelled_vehicle(raw),expected)
        for raw in ['车型A204','编号E202','车号E2O2','车号：2026年7月23日']:
            self.assertEqual(app.labelled_vehicle(raw),'')
    def test_split_tokens(self):
        self.assertEqual(app.vehicle_from_texts([('车号',.99),('E',.9),('202',.9),('里程',.99)]),'E202')
        self.assertEqual(app.vehicle_from_texts([('车号',.99),('里程',.99),('A204',.9)]),'')
    def test_geometry_and_field_boundary(self):
        boxes=[B(10,50,40,65,'车号',.99), B(120,45,150,60,'里程',.99), B(160,50,180,65,'200',.9),
               B(55,53,65,65,'E',.8),B(67,53,95,65,'202',.9)]
        self.assertEqual(app.vehicle_from_boxes(boxes),'E202')
        self.assertEqual(app.vehicle_from_boxes([b for b in boxes if b.text not in ['E','202']]),'')
    def test_separate_label_letters(self):
        boxes=[B(10,50,20,65,'车',.99), B(21,50,31,65,'号',.99), B(50,52,88,66,'00123',.9)]
        self.assertEqual(app.vehicle_from_boxes(boxes),'00123')
    def test_conflict_not_guessed(self):
        boxes=[B(10,50,40,65,'车号E202',.9),B(10,90,40,105,'车号A204',.9)]
        self.assertEqual(app.vehicle_from_boxes(boxes),'')
    def test_expanded_retry_and_missing_diagnostics(self):
        with fitz.open() as doc, tempfile.TemporaryDirectory() as tmp:
            page=doc.new_page();debug=Path(tmp)
            boxes=[B(10,50,40,65,'车号',.99),B(50,50,90,65,'E202',.9)]
            with patch.object(app,'ocr_boxes',return_value=boxes):
                value,note=app.retry_vehicle(page,[],debug,0)
            self.assertEqual(value,'E202')
            self.assertTrue((debug/'page-0001-expanded.png').exists())
            with patch.object(app,'ocr_boxes',return_value=[]):
                value,note=app.retry_vehicle(page,[],debug,1)
            self.assertEqual(value,'')
            self.assertTrue((debug/'page-0002-ocr.json').exists())
    def test_cell_retry_and_variant_conflict(self):
        with fitz.open() as doc, tempfile.TemporaryDirectory() as tmp:
            page=doc.new_page();debug=Path(tmp)
            anchor=[B(20,100,70,120,'车号',.99)]
            first=[B(5,5,80,25,'E202',.9)]
            second=[B(5,5,80,25,'A204',.9)]
            with patch.object(app,'ocr_boxes',side_effect=[anchor,[],first,first]):
                value,note=app.retry_vehicle(page,[],debug,0)
            self.assertEqual(value,'E202')
            self.assertTrue((debug/'page-0001-cell-0-contrast.png').exists())
            with patch.object(app,'ocr_boxes',side_effect=[anchor,[],first,second]):
                value,note=app.retry_vehicle(page,[],debug,1)
            self.assertEqual(value,'')
            self.assertIn('冲突',note)

    def test_footer_metadata_labels(self):
        boxes=[B(10,1900,70,1920,'检查时间',.99),B(80,1900,160,1920,'20260723',.9),
               B(200,1900,260,1920,'检查地点',.99),B(270,1900,350,1920,'河北官厅',.9),
               B(390,1900,450,1920,'检查车辆',.99),B(460,1900,540,1920,'A204',.9)]
        self.assertEqual(app.field_from_boxes(boxes,app.DATE_LABEL,app.normalized_date_value),'20260723')
        self.assertEqual(app.field_from_boxes(boxes,app.PLACE_LABEL,app.parse_place_value),'河北官厅')
        self.assertEqual(app.vehicle_from_boxes(boxes),'A204')
        self.assertEqual(app.normalized_date_value('20260230'),'')
    def test_footer_coordinates(self):
        with fitz.open() as doc:
            page=doc.new_page(width=600,height=800)
            with patch.object(app,'ocr_boxes',return_value=[B(10,20,50,40,'检查车辆',.9)]):
                boxes,png=app.ocr_footer(page,zoom=2.5)
            self.assertEqual(boxes[0].y0,1520)
            self.assertTrue(png.startswith(b'\x89PNG'))
    def test_annex_scan_metadata_from_footer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'annex.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(pdf)
            header=[B(10,30,300,50,'A车2.0阶段质量质心测量配重明细表',.99)]
            footer=[B(10,1900,70,1920,'检查时间20260723',.9),B(200,1900,350,1920,'检查地点河北官厅',.9),B(390,1900,540,1920,'检查车辆A204',.9)]
            with patch.object(app,'ocr_boxes',side_effect=[header,footer]):
                rows=app.scan_pdf(pdf,debug_dir=root/'debug')
            self.assertEqual((rows[0].vehicle,rows[0].time_code,rows[0].location_raw),('A204','20260723','河北官厅'))
            self.assertNotIn('时间未识别',rows[0].note)

    def test_recognition_only_handwriting(self):
        from unittest.mock import Mock
        from PIL import Image
        from io import BytesIO
        image=BytesIO();Image.new('RGB',(180,50),'white').save(image,format='PNG')
        engine=Mock();engine.ocr.return_value=[[('A204',.95)]]
        with patch.object(app,'get_ocr',return_value=engine):
            self.assertEqual(app.recognize_single_cell(image.getvalue()),'A204')
        self.assertFalse(engine.ocr.call_args.kwargs['det'])
        engine.ocr.return_value=[[('A2O4',.99)]]
        with patch.object(app,'get_ocr',return_value=engine):
            self.assertEqual(app.recognize_single_cell(image.getvalue()),'')

    def test_scan_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'sample.pdf'
            with fitz.open() as doc:
                doc.new_page();doc.save(pdf)
            initial=[B(10,50,40,65,'车号',.99)]
            with patch.object(app,'ocr_boxes',return_value=initial),patch.object(app,'retry_vehicle',return_value=('A204','车号经扩大区域复识别')):
                rows=app.scan_pdf(pdf,debug_dir=root/'debug')
            self.assertEqual(rows[0].vehicle,'A204')
            self.assertNotIn('车号未识别',rows[0].note)
            self.assertIn('A204',rows[0].filename_base)
if __name__=='__main__':unittest.main()
