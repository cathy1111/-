import argparse
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
import outline_catalog as oc
import vehicle_outlines as vc
import split_experiments as app
from demo_vehicle_data import generate_demo

class MultiVehicleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.demo=Path(cls.tmp.name)/'demo';generate_demo(cls.demo)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def import_six(self,root):
        for vehicle in 'ABCDEF':
            args=argparse.Namespace(input=str(self.demo/'full_outlines'/(vehicle+'_outline.pdf')),out=str(root),vehicle=vehicle)
            app.cmd_import_outline(args)
        return vc.VehicleBank.load(root/'outlines')
    def test_full_demo_prefers_toc_over_body(self):
        for index,vehicle in enumerate('ABCDEF',1):
            catalog,notes=oc.read_source(self.demo/'full_outlines'/(vehicle+'_outline.pdf'))
            self.assertEqual(len(catalog.entries),3)
            self.assertEqual(catalog.source_mode,'PDF目录')
            self.assertEqual(catalog.match('加速性能试验记录表').number,f'{index}.3')
            self.assertTrue(catalog.example)
            self.assertTrue(all(e.source_page==2 for e in catalog.entries))
            self.assertTrue(catalog.review_rows)
        with fitz.open(self.demo/'mixed_vehicle_records_scan.pdf') as doc:
            self.assertEqual(len(doc),6)
            self.assertTrue(all(not p.get_text().strip() for p in doc))
    def test_bookmarks_and_body_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);book=root/'book.pdf';body=root/'body.pdf'
            with fitz.open() as doc:
                doc.new_page().insert_text((30,50),'1.1 正文杂项',fontname='china-s')
                doc.new_page().insert_text((30,50),'8.3 加速性能试验',fontname='china-s')
                doc.set_toc([[1,'8.3 加速性能试验',2]]);doc.save(book)
            cat,_=oc.read_source(book)
            self.assertEqual(cat.source_mode,'PDF书签');self.assertEqual(cat.entries[0].number,'8.3')
            with fitz.open() as doc:
                page=doc.new_page();page.insert_text((30,50),'5.2 加速性能试验',fontname='china-s')
                page.insert_text((30,80),'5.2.1 车辆应在平坦道路进行试验',fontname='china-s');doc.save(body)
            cat,_=oc.read_source(body)
            self.assertEqual(cat.source_mode,'正文标题候选')
            self.assertEqual([e.number for e in cat.entries],['5.2'])
    def test_conflicts_are_reported_not_silently_assigned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pdf=root/'conflict.pdf'
            with fitz.open() as doc:
                page=doc.new_page()
                for y,t in [(40,'目录'),(80,'1.1 加速性能试验 ...... 3'),(110,'1.1 制动性能试验 ...... 4'),(140,'1.2 转向性能试验 ...... 5')]:
                    page.insert_text((30,y),t,fontname='china-s')
                doc.save(pdf)
            cat,notes=oc.read_source(pdf)
            self.assertEqual([e.number for e in cat.entries],['1.2'])
            self.assertEqual(sum('同号异名' in r['状态'] for r in cat.review_rows),2)
            app.cmd_import_outline(argparse.Namespace(input=str(pdf),out=str(root),vehicle='A'))
            self.assertTrue((root/'outlines/vehicle_A_extraction_review.csv').exists())
    def test_vehicle_family_exact_override_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bank=self.import_six(root)
            cat=oc.Catalog([oc.OutlineEntry('9.3','加速性能试验')],root/'outlines/vehicle_A204.csv')
            oc.write_catalog(cat,cat.path);bank=vc.VehicleBank.load(root/'outlines')
            self.assertEqual(bank.select('A204')[0],'A204')
            self.assertEqual(bank.select('A205')[0],'A')
            self.assertEqual(bank.select('B101')[0],'B')
            for number in ['204','未知','G901','AB204']:
                self.assertIsNone(bank.select(number)[1])
            self.assertEqual(vc.vehicle_key('A车'),'A')
    def test_mixed_records_preview_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bank=self.import_six(root);out=root/'out'
            cars=['A204','B101','C301','D401','E202','F601']
            metas=[app.PageMeta(i,'加速性能试验记录表',car,'2026年7月23日','20260723','河北官厅',str(i),'unused') for i,car in enumerate(cars)]
            args=argparse.Namespace(input=str(self.demo/'mixed_vehicle_records_scan.pdf'),out=str(out),version='V011',top_ratio=.4,max_pages=None,outline=None,rescan=False)
            with patch.object(app,'active_outline',return_value=bank),patch.object(app,'scan_pdf',return_value=metas):app.cmd_preview(args)
            with (out/'preview.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertEqual([r['大纲车辆'] for r in rows],list('ABCDEF'))
            self.assertEqual([r['大纲序号'] for r in rows],[f'{i}.3' for i in range(1,7)])
            with patch.object(app,'scan_pdf',side_effect=AssertionError('Do not OCR on reviewed export')):app.cmd_split(args)
            pdfs=list(out.glob('*.pdf'));self.assertEqual(len(pdfs),6)
            for i,car in enumerate(cars,1):
                self.assertTrue(any(p.name.startswith(f'示例-{i}.3-') and car in p.name for p in pdfs))
            loaded=app.load_preview_csv(out/'preview.csv')
            loaded[0].vehicle='B101'
            with self.assertRaises(ValueError):app.verify_outline_identity(out,loaded)
            loaded[0].vehicle='A204';loaded[0].outline_no='2.3'
            with self.assertRaises(ValueError):app.verify_outline_identity(out,loaded)
    def test_real_vehicle_replaces_only_its_own_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bank=self.import_six(root)
            real=root/'real_C.csv';oc.write_catalog(oc.Catalog([oc.OutlineEntry('7.2.1','加速性能试验')],real),real)
            app.cmd_import_outline(argparse.Namespace(input=str(real),out=str(root),vehicle='C'))
            bank=vc.VehicleBank.load(root/'outlines')
            metas=[app.PageMeta(0,'加速性能试验记录表','C301','','20260723','河北官厅','',''),app.PageMeta(1,'加速性能试验记录表','A204','','20260723','河北官厅','','')]
            app.attach_outline(metas,bank)
            self.assertFalse(metas[0].outline_example);self.assertEqual(metas[0].outline_no,'7.2.1')
            self.assertTrue(metas[0].filename_base.startswith('7.2.1-'))
            self.assertTrue(metas[1].filename_base.startswith('示例-'))
            self.assertTrue((root/'outlines/vehicle_C.previous.csv').exists())
    def test_no_cross_vehicle_fuzzy_fallback_and_reviewed_vehicle_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'outlines';folder.mkdir()
            for key,title,no in [('A','加速性能试验','1.3'),('B','其他专用试验','2.9')]:
                path=folder/f'vehicle_{key}.csv';oc.write_catalog(oc.Catalog([oc.OutlineEntry(no,title)],path),path)
            bank=vc.VehicleBank.load(folder)
            meta=app.PageMeta(0,'其他专用试验记录表','A204','','20260723','河北官厅','','')
            app.attach_outline([meta],bank)
            self.assertEqual(meta.outline_vehicle,'A')
            self.assertEqual(meta.outline_no,'')
            unknown=app.PageMeta(1,'加速性能试验记录表','204','','20260723','河北官厅','','')
            app.attach_outline([unknown],bank)
            self.assertEqual(unknown.outline_vehicle,'')
            unknown.vehicle='A204'
            data={'root':str(folder),'catalogs':bank.snapshot()}
            self.assertTrue(vc.verify_bank(data,[unknown]))
            self.assertEqual(unknown.outline_vehicle,'A');self.assertEqual(unknown.outline_no,'1.3')

    def test_windows_entrypoints(self):
        root=Path(__file__).parent
        for name in ['import_vehicle_outline.bat','make_demo_data.bat']:
            raw=(root/name).read_bytes();raw.decode('ascii')
            self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
            self.assertEqual(raw.count(b'\r\n:find_python\r\n'),1)

if __name__=='__main__':unittest.main()
