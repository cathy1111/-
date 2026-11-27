import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fitz
import split_experiments as app
from location_catalog import load,resolve
from scan_checkpoint import Checkpoint,identity

class LargeScanTests(unittest.TestCase):
    def test_confirmed_place_aliases_only(self):
        mapping=load()
        for raw in ['河水定厅','河北官后']:
            value,note=resolve(raw,mapping);self.assertEqual(value,'河北官厅');self.assertIn(raw,note)
        self.assertEqual(resolve('河北官厅',mapping),('河北官厅',''))
        self.assertEqual(resolve('北京试验场',mapping)[0],'北京试验场')
        self.assertEqual(resolve('河北官厂',mapping)[0],'河北官厂')
        self.assertEqual(resolve('',mapping),('',''))
    def test_checkpoint_recovers_partial_line_and_rejects_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Checkpoint(tmp,{'test':1}) as state:
                state.append({'page_index':0,'note':'ok'});path=state.path
                with self.assertRaises(RuntimeError):
                    with Checkpoint(tmp,{'test':1}):pass
            with path.open('ab') as stream:stream.write(b'{partial row')
            with Checkpoint(tmp,{'test':1}) as state:
                self.assertEqual(len(state.rows),1);state.append({'page_index':1,'note':'ok'})
            with Checkpoint(tmp,{'test':1}) as state:self.assertEqual(len(state.rows),2)
    def test_pdf_content_changes_invalidate_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.pdf';p.write_bytes(b'first');a=identity(p,.4,Path(tmp));p.write_bytes(b'second');self.assertNotEqual(a,identity(p,.4,Path(tmp)))
    def test_1000_page_resume_and_export_with_mocked_ocr(self):
        # Real 1000-page PDF, rasterization/checkpoint/CSV/PDF export; OCR is a test double.
        boxes=[app.OCRBox(20,10,450,30,'加速性能试验记录表',.99),
            app.OCRBox(20,60,110,80,'试验时间',.99),app.OCRBox(120,60,290,80,'2026年7月23日',.99),
            app.OCRBox(310,60,390,80,'试验地点',.99),app.OCRBox(400,60,530,80,'河水定厅',.99),
            app.OCRBox(20,110,100,130,'车号',.99),app.OCRBox(110,110,200,130,'A204',.99)]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'1000-pages.pdf'
            with fitz.open() as doc:
                for i in range(1000):doc.new_page(width=100,height=150).insert_text((10,25),str(i+1))
                doc.save(str(source))
            calls=[0]
            def failing_ocr(*args,**kwargs):
                calls[0]+=1
                if calls[0]==501:raise RuntimeError('simulated OCR interruption')
                return boxes
            with contextlib.redirect_stdout(io.StringIO()),patch.object(app,'load_confirmed_rules',return_value=[]),patch.object(app,'ocr_boxes',side_effect=failing_ocr):
                with self.assertRaisesRegex(RuntimeError,'simulated'):
                    app.scan_pdf(source,resume_dir=root/'progress')
            self.assertEqual(calls[0],501)
            with contextlib.redirect_stdout(io.StringIO()),patch.object(app,'load_confirmed_rules',return_value=[]),patch.object(app,'ocr_boxes',return_value=boxes) as mocked:
                metas=app.scan_pdf(source,resume_dir=root/'progress')
                self.assertEqual(mocked.call_count,500)
                self.assertEqual(len(metas),1000)
                self.assertTrue(all(m.location_raw=='河北官厅' and m.location_ocr_raw=='河水定厅' for m in metas))
                app.write_preview_csv(metas,root/'out/preview.csv','V011')
                written=app.split_pdf(source,metas,root/'out','V011')
            self.assertEqual(len(written),1000);self.assertEqual(len(set(written)),1000)
            with fitz.open(str(written[0])) as first:self.assertIn('1',first[0].get_text())
            with fitz.open(str(written[-1])) as last:self.assertIn('1000',last[0].get_text())
            with contextlib.redirect_stdout(io.StringIO()),patch.object(app,'load_confirmed_rules',return_value=[]),patch.object(app,'ocr_boxes',side_effect=AssertionError('must use checkpoint')):
                self.assertEqual(len(app.scan_pdf(source,resume_dir=root/'progress')),1000)
    def test_pause_request_stops_before_the_next_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'two.pdf'
            with fitz.open() as doc:
                doc.new_page();doc.new_page();doc.save(str(pdf))
            (root/'pause-request').write_text('pause')
            with contextlib.redirect_stdout(io.StringIO()),patch.object(app,'ocr_boxes',side_effect=AssertionError('paused before OCR')):
                with self.assertRaises(InterruptedError):app.scan_pdf(pdf,resume_dir=root/'progress')
            self.assertFalse((root/'pause-request').exists())

    def test_incomplete_preview_blocks_old_export(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'input.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(str(pdf))
            out=root/'out';out.mkdir();(out/'preview-in-progress.json').write_text('interrupted')
            args=Namespace(input=str(pdf),out=str(out),version='V011',rescan=False,outline=None,top_ratio=.4,max_pages=None)
            with self.assertRaisesRegex(ValueError,'尚未完整完成'):app.cmd_split(args)
if __name__=='__main__':unittest.main()
