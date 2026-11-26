import argparse
import csv
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import fitz
import outline_catalog as oc
import split_experiments as app

class OutlineTests(unittest.TestCase):
    def catalog(self,root,example=False):
        path=root/'catalog.csv'
        cat=oc.Catalog([oc.OutlineEntry('3.2.1','加速性能试验',(),example),oc.OutlineEntry('3.10','装备质量质心测定',('A车配重明细表',),example)],path,example)
        oc.write_catalog(cat,path)
        return oc.read_source(path)[0]
    def test_matching_and_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            cat=self.catalog(Path(tmp))
            self.assertEqual(cat.match('加速性能试验记录表').number,'3.2.1')
            self.assertEqual(cat.match('A车配重明细表').number,'3.10')
            self.assertEqual(cat.match('加速性能试验').status,'完整名称匹配')
            self.assertEqual(cat.match('加速试验').number,'')
            self.assertIn('3.2.1',cat.match('加速试验').candidates)
            self.assertEqual(oc.prefix_filename('test','3.2.1',True),'3.2.1-test')
            self.assertEqual(oc.prefix_filename('test','',True),'待匹配-test')
            self.assertEqual(oc.prefix_filename('test','3.2.1',True,True),'示例-3.2.1-test')
            self.assertEqual(oc.prefix_filename('test'),'test')
    def test_collisions_and_invalid_numbers(self):
        entries=[oc.OutlineEntry('1.1','科目一',('加速性能试验',)),oc.OutlineEntry('1.2','科目二',('加速性能试验',))]
        cat=oc.Catalog(entries,Path('unused'))
        self.assertEqual(cat.match('加速性能试验记录表').status,'多项匹配')
        self.assertEqual(cat.match('加速性能试验记录表').number,'')
        with self.assertRaises(ValueError):oc.validate_entries([oc.OutlineEntry('1','甲试验'),oc.OutlineEntry('1','乙试验')])
        for invalid in ['../1','1/2','1-2','1:2','']:
            with self.assertRaises(ValueError):oc.normalize_number(invalid)
        self.assertEqual(oc.normalize_number('A.1.2'),'A.1.2')
        self.assertEqual(oc.normalize_number('3.10'),'3.10')
    def test_plain_text_and_docx_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            text=root/'outline.txt';text.write_text('3.2.1 加速性能试验……12\n3.10 装备质量质心测定\n一旦发生变化不应识别成编号\n',encoding='utf-8')
            cat,_=oc.read_source(text)
            self.assertEqual([(e.number,e.name) for e in cat.entries],[('3.2.1','加速性能试验'),('3.10','装备质量质心测定')])
            word=root/'outline.docx'
            xml='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>大纲序号</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>科目名称</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>3.2.1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>加速性能试验</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
            with zipfile.ZipFile(word,'w') as z:z.writestr('word/document.xml',xml)
            cat,notes=oc.read_source(word)
            self.assertEqual(cat.entries[0].number,'3.2.1')
            self.assertTrue(notes)
    def test_text_pdf_and_scanned_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'text.pdf';scan=root/'scan.pdf'
            with fitz.open() as doc:
                page=doc.new_page();page.insert_text((40,50),'3.2.1 加速性能试验……12',fontname='china-s');doc.save(pdf)
            cat,_=oc.read_source(pdf)
            self.assertEqual(cat.entries[0].name,'加速性能试验')
            with fitz.open() as doc:doc.new_page();doc.save(scan)
            seen=[]
            def fake_ocr(png):
                seen.append(png)
                return [('3.2.1',.99),('加速性能试验',.99)]
            cat,notes=oc.read_source(scan,fake_ocr)
            self.assertEqual(cat.entries[0].number,'3.2.1')
            self.assertTrue(seen[0].startswith(b'\x89PNG'))
            self.assertTrue(any('OCR' in n for n in notes))
    @unittest.skipUnless(importlib.util.find_spec('openpyxl'),'openpyxl not installed')
    def test_xlsx_text_number(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'outline.xlsx';wb=openpyxl.Workbook();sheet=wb.active
            sheet.append(['大纲序号','科目名称']);sheet.append(['3.10','加速性能试验']);wb.save(path);wb.close()
            cat,_=oc.read_source(path)
            self.assertEqual(cat.entries[0].number,'3.10')
    def test_example_is_not_silently_formal(self):
        path=Path(__file__).parent/'examples/sample_outline.csv'
        cat,_=oc.read_source(path)
        self.assertTrue(cat.example)
        self.assertEqual(cat.match('加速性能试验记录表').number,'1.3')
        self.assertEqual(cat.match('A车20阶段战斗全重状态质量质心测量配重明细表').number,'1.2')
    def test_import_preview_review_and_export_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'out';cat=self.catalog(root);source=root/'record.pdf'
            with fitz.open() as doc:doc.new_page();doc.save(source)
            meta=app.PageMeta(0,'加速性能试验记录表','A204','2026年7月23日','20260723','河北官厅','group','unused')
            args=argparse.Namespace(input=str(source),out=str(out),version='V011',top_ratio=.4,max_pages=None,outline=str(cat.path))
            with patch.object(app,'scan_pdf',return_value=[meta]):app.cmd_preview(args)
            with (out/'preview.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            self.assertEqual(rows[0]['大纲序号'],'3.2.1')
            self.assertTrue(rows[0]['预计文件名'].startswith('3.2.1-'))
            args.rescan=False
            with patch.object(app,'scan_pdf',side_effect=AssertionError('Do not rerun OCR during reviewed export')):
                app.cmd_split(args)
            expected=out/'3.2.1-加速性能试验记录表-A204-20260723-河北官厅-V011.pdf'
            self.assertTrue(expected.exists())
            with fitz.open(expected) as doc:self.assertEqual(len(doc),1)
            cat.path.write_text('changed',encoding='utf-8')
            with self.assertRaises(ValueError):app.cmd_split(args)
    def test_manual_number_and_demo_marker_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cat=self.catalog(root,True)
            meta=app.PageMeta(0,'不匹配的科目','A204','','20260723','河北官厅','group','unused')
            app.attach_outline([meta],cat);app.write_preview_csv([meta],root/'preview.csv','V011');app.write_outline_identity(root,cat)
            self.assertTrue(meta.filename_base.startswith('示例-待匹配-'))
            meta.outline_no='3.2.1';app.verify_outline_identity(root,[meta])
            self.assertTrue(app.refresh_filename(meta).startswith('示例-3.2.1-'))
            meta.outline_example=False
            with self.assertRaises(ValueError):app.verify_outline_identity(root,[meta])
            meta.outline_example=True;meta.outline_no='99'
            with self.assertRaises(ValueError):app.verify_outline_identity(root,[meta])
    def test_import_command_backups_and_windows_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cat=self.catalog(root);target=root/'active';target.mkdir()
            (target/'outline_catalog.csv').write_bytes(b'old')
            args=argparse.Namespace(input=str(cat.path),out=str(target))
            app.cmd_import_outline(args)
            self.assertEqual((target/'outline_catalog.previous.csv').read_bytes(),b'old')
            self.assertTrue((target/'outline_import_report.txt').exists())
        raw=(Path(__file__).parent/'import_outline.bat').read_bytes();raw.decode('ascii')
        self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
        self.assertEqual(raw.count(b'\r\n:find_python\r\n'),1)

if __name__=='__main__':unittest.main()
