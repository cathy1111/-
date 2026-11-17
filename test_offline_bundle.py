import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('offline_bundle',Path(__file__).parent/'soft/offline_bundle.py')
bundle=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

class OfflineTests(unittest.TestCase):
    def test_missing_package_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);soft=root/'soft';soft.mkdir();wheels=soft/'wheelhouse';wheels.mkdir()
            with patch.multiple(bundle,ROOT=root,SOFT=soft,WHEELS=wheels,MANIFEST=soft/'offline-manifest.json'):
                with self.assertRaises(ValueError):bundle.verify()
                names=['python/python-3.9.13-amd64.exe','vcredist/vc_redist.x64.exe','requirements-lock.txt','wheelhouse/httpx-1-test.whl']
                for name,_ in bundle.MODEL_DIRS:
                    names.extend(['paddleocr_models/'+name+'/inference.pdmodel','paddleocr_models/'+name+'/inference.pdiparams'])
                for name in names:
                    p=soft/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
                files=bundle.manifest_files()
                bundle.MANIFEST.write_text(json.dumps({'files':{p.relative_to(root).as_posix():bundle.digest(p) for p in files}}))
                bundle.verify()
                (wheels/'httpx-1-test.whl').write_bytes(b'changed')
                with self.assertRaises(ValueError):bundle.verify()
    def test_offline_command_and_line_endings(self):
        root=Path(__file__).parent
        raw=(root/'soft/install_offline.bat').read_bytes()
        text=raw.decode('ascii')
        self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
        self.assertIn('--no-index --no-cache-dir --find-links=',text)
        self.assertNotIn('https://',text)
        self.assertIn('PIP_NO_INDEX=1',text)
        self.assertIn('requirements-lock.txt',text)
        for name in ['run_preview.bat','run_export.bat']:
            self.assertIn('.venv\\Scripts\\python.exe',(root/name).read_text())
        self.assertIn("'wheel'",Path(bundle.__file__).read_text())
        self.assertIn("'--no-index'",Path(bundle.__file__).read_text())
if __name__=='__main__':unittest.main()
