import tempfile
import unittest
from pathlib import Path
from outline_migration import migrate

class MigrationTests(unittest.TestCase):
    def catalog(self,root,name='vehicle_A.csv',title='加速性能试验',example=False):
        folder=root/'outlines';folder.mkdir(parents=True,exist_ok=True)
        p=folder/name;p.write_text('大纲序号,科目名称,示例标记\n1.3,'+title+','+('示例' if example else '')+'\n',encoding='utf-8-sig');return p
    def test_recover_keep_source_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new';old=Path(tmp)/'old';src=self.catalog(old);before=src.read_bytes()
            report,_=migrate(root,[old]);self.assertEqual(len(report['copied']),1);self.assertEqual(src.read_bytes(),before)
            destination=root/'outlines/vehicle_A.csv';self.assertEqual(destination.read_bytes(),before)
            src.write_text('changed',encoding='utf-8');migrate(root,[old]);self.assertEqual(destination.read_bytes(),before)
    def test_ambiguous_versions_are_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new';a=Path(tmp)/'a';b=Path(tmp)/'b';self.catalog(a);self.catalog(b,title='质量质心测定')
            report,_=migrate(root,[a,b]);self.assertEqual(len(report['conflicts']),1);self.assertFalse((root/'outlines/vehicle_A.csv').exists())
    def test_identical_duplicates_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new';a=Path(tmp)/'a';b=Path(tmp)/'b';self.catalog(a);self.catalog(b)
            report,_=migrate(root,[a,b]);self.assertEqual(len(report['copied']),1)
    def test_samples_and_backup_files_are_not_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new';old=Path(tmp)/'old';self.catalog(old,example=True);self.catalog(old,name='vehicle_B.previous.csv')
            report,_=migrate(root,[old]);self.assertFalse(report['copied']);self.assertEqual(len(report['ignored']),1)
    def test_missing_old_data_is_explicit_not_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            report,message=migrate(Path(tmp)/'new',[Path(tmp)/'missing']);self.assertFalse(report['copied']);self.assertIn('未找到旧大纲',message)
if __name__=='__main__':unittest.main()
