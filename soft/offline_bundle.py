"""Prepare and verify a Windows CPython 3.9 x64 offline bundle (stdlib only)."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

SOFT = Path(__file__).resolve().parent
ROOT = SOFT.parent
WHEELS = SOFT / 'wheelhouse'
MANIFEST = SOFT / 'offline-manifest.json'
TOOLS = ['pip==25.3', 'setuptools==75.8.2', 'wheel==0.45.1']
MODEL_DIRS = [
    ('ch_PP-OCRv4_det_infer', 'det/ch'),
    ('ch_PP-OCRv4_rec_infer', 'rec/ch'),
    ('ch_ppocr_mobile_v2.0_cls_infer', 'cls'),
]

def run(args):
    print('Running: ' + ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=str(ROOT), check=True)

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def windows_python():
    if os.name != 'nt' or sys.version_info[:2] != (3, 9) or struct.calcsize('P') != 8:
        raise ValueError('Use Windows 64-bit with Python 3.9. This bundle targets cp39-win_amd64.')

def model_files():
    files = []
    for name, sub in MODEL_DIRS:
        candidates = [SOFT / 'paddleocr_models' / name, SOFT / 'paddleocr_models' / 'from_cache' / sub / name]
        folder = next((p for p in candidates if (p / 'inference.pdmodel').is_file() and (p / 'inference.pdiparams').is_file()), None)
        if folder is None:
            raise ValueError('Missing bundled model: ' + name + '. Keep the original paddleocr_models folder.')
        files.extend(p for p in folder.rglob('*') if p.is_file())
    return files

def manifest_files():
    required = [SOFT / 'python/python-3.9.13-amd64.exe', SOFT / 'vcredist/vc_redist.x64.exe', SOFT / 'requirements-lock.txt']
    for p in required:
        if not p.is_file():
            raise ValueError('Missing required file: ' + str(p))
    wheels = list(WHEELS.glob('*.whl'))
    if not wheels:
        raise ValueError('No wheels found. Run prepare_online.bat on an Internet-connected computer first.')
    return sorted(set(required + wheels + model_files()))

def verify():
    if not MANIFEST.is_file():
        raise ValueError('Offline package is not prepared. Run prepare_online.bat on a connected PC first.')
    data = json.loads(MANIFEST.read_text(encoding='utf-8'))
    files = data.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Invalid offline manifest')
    for name, expected in files.items():
        p = (ROOT / name).resolve()
        try:
            p.relative_to(ROOT.resolve())
        except ValueError:
            raise ValueError('Invalid manifest path')
        if not p.is_file() or digest(p) != expected:
            raise ValueError('Missing or changed bundle file: ' + name)
    required = {str(p.relative_to(ROOT)).replace('\\', '/') for p in manifest_files()}
    if required != set(files):
        raise ValueError('Bundle inventory changed. Prepare the package again.')
    print('Offline bundle integrity OK: ' + str(len(files)) + ' files.', flush=True)
    return data

def clean_environment(path):
    if path.exists():
        shutil.rmtree(path)
    run([sys.executable, '-m', 'venv', str(path)])
    return path / 'Scripts/python.exe'

def prepare():
    windows_python()
    # Never leave an old success marker after an interrupted or failed rebuild.
    MANIFEST.unlink(missing_ok=True)
    output = ROOT / 'offline-package.zip'
    output.unlink(missing_ok=True)
    model_files()
    for name in ['python/python-3.9.13-amd64.exe', 'vcredist/vc_redist.x64.exe']:
        if not (SOFT / name).is_file():
            raise ValueError('Missing installer: ' + name)
    WHEELS.mkdir(exist_ok=True)
    for p in WHEELS.glob('*.whl'):
        p.unlink()
    build = clean_environment(ROOT / '.bundle-build')
    run([build, '-m', 'pip', 'install', '--index-url', 'https://pypi.org/simple', *TOOLS])
    # wheel, rather than download, converts source-only dependencies such as fire
    # into installable wheels while Internet access and build tools are available.
    run([build, '-m', 'pip', 'wheel', '--index-url', 'https://pypi.org/simple',
         '--wheel-dir', WHEELS, '--find-links', SOFT / 'wheels', '--prefer-binary',
         '-r', SOFT / 'requirements-win.txt', 'paddlepaddle==2.6.1', *TOOLS])
    check = clean_environment(ROOT / '.bundle-check')
    offline_env = dict(os.environ, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1', PIP_NO_CACHE_DIR='1')
    commands = [
        [check, '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--find-links', WHEELS,
         '-r', SOFT / 'requirements-win.txt', 'paddlepaddle==2.6.1', *TOOLS],
        [check, '-m', 'pip', 'check'],
        [check, '-c', 'import fitz, paddle; from paddleocr import PaddleOCR; print("Imports OK")'],
        [check, '-c', 'from split_experiments import get_ocr; get_ocr(); print("Local OCR model initialization OK")'],
    ]
    for command in commands:
        print('Verifying fresh environment without package-index access...', flush=True)
        subprocess.run(list(map(str, command)), cwd=str(ROOT), env=offline_env, check=True)
    frozen = subprocess.check_output([str(check), '-m', 'pip', 'freeze', '--all'], text=True)
    (SOFT / 'requirements-lock.txt').write_text(frozen, encoding='utf-8')
    # Reinstall from the exact lock as well; this is what the offline installer uses.
    subprocess.run([str(check), '-m', 'pip', 'install', '--no-index', '--no-cache-dir', '--find-links', str(WHEELS),
                    '-r', str(SOFT / 'requirements-lock.txt')], env=offline_env, check=True)
    files = manifest_files()
    MANIFEST.write_text(json.dumps({'target': 'Windows x64 / CPython 3.9',
        'files': {p.relative_to(ROOT).as_posix(): digest(p) for p in files}}, indent=2), encoding='utf-8')
    data = verify()
    # Only ship application files and vetted dependencies, never input/output PDFs,
    # the host interpreter, API keys, or the temporary virtual environments.
    package_files = [ROOT / name for name in data['files']]
    package_files += [MANIFEST, ROOT / 'split_experiments.py', ROOT / 'run_preview.bat', ROOT / 'run_export.bat',
                      SOFT / 'install_offline.bat', SOFT / 'offline_bundle.py', SOFT / 'requirements-win.txt',
                      ROOT / 'OFFLINE_GUIDE.md']
    package_files += [ROOT / 'outline_catalog.py', ROOT / 'import_outline.bat', ROOT / 'OUTLINE_GUIDE.md', ROOT / 'examples/sample_outline.csv']
    package_files += [ROOT / 'vehicle_outlines.py', ROOT / 'full_outline_pdf.py', ROOT / 'demo_vehicle_data.py',
                      ROOT / 'import_vehicle_outline.bat', ROOT / 'make_demo_data.bat', ROOT / 'MULTI_VEHICLE_GUIDE.md']
    package_files += [ROOT / 'outline_manager.py', ROOT / 'outline_manager_backend.py', ROOT / 'open_outline_manager.bat',
                      ROOT / '打开大纲管理.bat', ROOT / 'import_vehicle_outline_cli.bat', ROOT / 'OUTLINE_MANAGER_GUIDE.md']
    if (ROOT / 'field_rules.json').is_file():
        package_files.append(ROOT / 'field_rules.json')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(package_files)):
            z.write(p, 'pro/' + p.relative_to(ROOT).as_posix())
    print('\nSUCCESS: ' + str(output), flush=True)
    print('Copy this ZIP to the offline PC and extract it to C:\\pro.')
    print('Then run C:\\pro\\soft\\install_offline.bat. No Internet required there.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'verify'])
    args = parser.parse_args()
    try:
        if args.action == 'prepare': prepare()
        else: verify()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('\nFAILED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
