import csv
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import outline_catalog as oc
import outline_manager_backend as backend

class ManagerTests(unittest.TestCase):
    def make_csv(self,root,name='A车 真实大纲 & test.csv'):
        path=root/name;catalog=oc.Catalog([oc.OutlineEntry('3.2.1','加速性能试验')],path)
        oc.write_catalog(catalog,path);return path
    def test_filename_guess_requires_unambiguous_vehicle(self):
        for name,code in [('A车试验大纲.pdf','A'),('C_outline.pdf','C'),('A204_试验大纲.pdf','A204'),('A车_A204专用大纲.pdf','A204'),('车型A总试验大纲.pdf','A'),('试验大纲-F.pdf','F')]:
            self.assertEqual(backend.guess_vehicle(name),code)
        for name in ['普通大纲.pdf','A车_B车大纲.pdf','A204_B101对照.pdf']:
            self.assertEqual(backend.guess_vehicle(name),'')
    def test_queue_preflight_and_resume_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.make_csv(root)
            rows=[{'id':'1','vehicle':'a车','path':str(path),'selected':True},{'id':'2','vehicle':'B','path':'','selected':False}]
            jobs=backend.prepare_jobs(rows)
            self.assertEqual(jobs[0].vehicle,'A')
            self.assertEqual(len(jobs),1)
            store=backend.StateStore(root/'state.json');store.save(rows)
            self.assertTrue(store.load()[0]['selected'])
            rows[0]['selected']=False;store.save(rows)
            self.assertFalse(store.load()[0]['selected'])
            self.assertEqual(store.load()[1]['vehicle'],'B')
    def test_duplicates_and_missing_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.make_csv(root)
            row={'id':'1','vehicle':'A','path':str(path),'selected':True}
            with self.assertRaises(ValueError):backend.prepare_jobs([row,{**row,'id':'2','vehicle':'a'}])
            with self.assertRaises(ValueError):backend.prepare_jobs([{**row,'vehicle':''}])
            with self.assertRaises(ValueError):backend.prepare_jobs([{**row,'path':str(root/'missing.pdf')}])
            with self.assertRaises(ValueError):backend.prepare_jobs([])
    def test_real_subprocess_import_and_stop_keeps_completed_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.make_csv(root);stop=threading.Event();events=[]
            jobs=[backend.ImportJob('1','A',path),backend.ImportJob('2','B',path)]
            def emit(event):
                events.append(event)
                if event['kind']=='success':stop.set()
            backend.run_imports(jobs,root,Path(__file__).parent/'split_experiments.py',stop,emit)
            self.assertTrue((root/'outlines/vehicle_A.csv').exists())
            self.assertFalse((root/'outlines/vehicle_B.csv').exists())
            self.assertEqual(events[-1]['successes'],1)
            self.assertTrue(events[-1]['stopped'])
            self.assertIn('已导入',backend.existing_catalog_status(root,'A'))
            self.assertEqual(backend.existing_catalog_status(root,'B'),'尚未导入')
    def test_failure_does_not_prevent_other_vehicle_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);good=self.make_csv(root);bad=root/'bad.csv';bad.write_text('not a catalog',encoding='utf-8')
            jobs=[backend.ImportJob('1','A',bad),backend.ImportJob('2','B',good)];events=[]
            backend.run_imports(jobs,root,Path(__file__).parent/'split_experiments.py',threading.Event(),events.append)
            self.assertFalse((root/'outlines/vehicle_A.csv').exists())
            self.assertTrue((root/'outlines/vehicle_B.csv').exists())
            self.assertEqual((events[-1]['successes'],events[-1]['failures']),(1,1))
    def test_incomplete_catalog_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'outlines';folder.mkdir();path=folder/'vehicle_C.csv'
            path.write_text('broken header\nvalue',encoding='utf-8')
            self.assertNotIn('已导入',backend.existing_catalog_status(root,'C'))
            path.write_text('大纲序号,科目名称\n1.3,',encoding='utf-8')
            self.assertNotIn('已导入',backend.existing_catalog_status(root,'C'))

    def test_single_instance_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=backend.InstanceLock(Path(tmp)/'lock');second=backend.InstanceLock(Path(tmp)/'lock')
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release();self.assertTrue(second.acquire());second.release()
    def test_atomic_catalog_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=self.make_csv(root);original=path.read_bytes()
            updated=oc.Catalog([oc.OutlineEntry('9.1','制动性能试验')],path)
            with patch.object(Path,'replace',side_effect=PermissionError('File is open in Excel')):
                with self.assertRaises(PermissionError):oc.write_catalog(updated,path)
            self.assertEqual(path.read_bytes(),original)
    def test_worker_uses_console_interpreter_for_captured_output(self):
        self.assertEqual(Path(backend.worker_interpreter('/tmp/pythonw.exe')).name,'python.exe')
        self.assertEqual(backend.worker_interpreter('/tmp/python.exe'),'/tmp/python.exe')

    def test_windows_launchers_keep_ascii_crlf(self):
        root=Path(__file__).parent
        for name in ['打开大纲管理.bat','open_outline_manager.bat','import_vehicle_outline.bat','import_vehicle_outline_cli.bat']:
            raw=(root/name).read_bytes();raw.decode('ascii')
            self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
        self.assertIn('pythonw.exe',(root/'open_outline_manager.bat').read_text())
        self.assertIn('open_outline_manager.bat',(root/'import_vehicle_outline.bat').read_text())

if __name__=='__main__':unittest.main()
