import io, tempfile, unittest, zipfile
from pathlib import Path
import fitz
import split_experiments as app

class RepairTests(unittest.TestCase):
    def test_date(self):
        self.assertEqual(app.format_time_code('2026','7','23'),'20260723')
        self.assertEqual(app.format_time_code('2026','2','30'),'')
    def test_version(self):
        self.assertEqual(app.normalize_version('v011'),'V011')
        with self.assertRaises(ValueError): app.normalize_version('../../bad')
    def test_distinct_pages_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'source.pdf'
            doc=fitz.open()
            for i in range(2):doc.new_page().insert_text((50,50),f'Page {i+1}')
            doc.save(src);doc.close()
            base=app.build_filename_base('实验记录表','E202','20260723','地点')
            metas=[app.PageMeta(i,'实验记录表','E202','2026年7月23日','20260723','地点','same',base) for i in range(2)]
            outputs=app.split_pdf(src,metas,root/'out','V011')
            self.assertEqual(len(outputs),2)
            for p in outputs:
                with fitz.open(p) as pdf:self.assertEqual(len(pdf),1)
            content=outputs[0].read_bytes()
            again=app.split_pdf(src,metas,root/'out','V011')
            self.assertTrue(set(outputs).isdisjoint(again))
            self.assertEqual(content,outputs[0].read_bytes())
    def test_windows_scripts(self):
        root=Path(__file__).parent
        for p in [root/'soft/install_offline.bat',root/'run_preview.bat',root/'run_export.bat']:
            raw=p.read_bytes();raw.decode('ascii')
            self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
            for label in [b':find_python\r\n',b':try_python\r\n']:
                self.assertEqual(raw.count(b'\r\n'+label),1)
if __name__=='__main__':unittest.main()
