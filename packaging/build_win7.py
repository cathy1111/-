"""Build a Win7 SP1 x64 compatibility *trial*, never claim Win7 real-machine validation."""
import hashlib
import json
import shutil
import subprocess
import sys
import sysconfig
import urllib.request
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
ENGINE_URL='https://github.com/hiroi-sora/RapidOCR-json/releases/download/v0.2.0/RapidOCR-json_v0.2.0.7z'
ENGINE_SHA='7ad9b283d03436c6cd0296723188699299cb4e5cf9140b410c59543aa5793c40'
FILES=['desktop_app.py','outline_manager.py','outline_manager_backend.py','split_experiments.py','outline_catalog.py','vehicle_outlines.py','full_outline_pdf.py','demo_vehicle_data.py','field_rules.json','location_catalog.py','locations.csv','scan_checkpoint.py','legacy_ocr.py','win7_diagnostics.py']

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def build():
    assert sys.platform=='win32' and sys.version_info[:2]==(3,8),'Build using CPython 3.8 x64 on Windows'
    payload=ROOT/'dist/TrialRecords-Win7';payload.mkdir(parents=True,exist_ok=True)
    for name in FILES:shutil.copy2(ROOT/name,payload/name)
    for name in ['desktop_app.py','outline_manager.py']:
        p=payload/name;s=p.read_text(encoding='utf-8')
        if name=='desktop_app.py':
            s=s.replace("VERSION='1.6.0'","VERSION='1.6.2-Win7 Trial'")
            s=s.replace("logging.basicConfig(filename=str(ROOT/'logs/desktop_app.log'),encoding='utf-8',level=logging.INFO)","logging.basicConfig(handlers=[logging.FileHandler(str(ROOT/'logs/desktop_app.log'),encoding='utf-8')],level=logging.INFO)")
        else:
            s=s.replace("logging.basicConfig(filename=str(ROOT/'logs'/'outline_manager.log'),level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')","logging.basicConfig(handlers=[logging.FileHandler(str(ROOT/'logs'/'outline_manager.log'),encoding='utf-8')],level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')")
        p.write_text(s,encoding='utf-8')
    p=payload/'split_experiments.py';s=p.read_text(encoding='utf-8');anchor='    global _OCR\n'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+"    if (Path(__file__).resolve().parent/'legacy_engine.json').is_file():\n        if _OCR is None:\n            from legacy_ocr import LegacyOCR\n            _OCR=LegacyOCR()\n        return _OCR\n",1)
    s=s.replace('PROGRAM_VERSION = "1.6.0"','PROGRAM_VERSION = "1.6.2-Win7 Trial"');p.write_text(s,encoding='utf-8')
    runtime=payload/'runtime';base=Path(sys.base_prefix);runtime.mkdir(exist_ok=True)
    for name in ['python.exe','pythonw.exe','python3.dll','python38.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        if (base/name).is_file():shutil.copy2(base/name,runtime/name)
    for name in ['DLLs','tcl']:shutil.copytree(base/name,runtime/name,dirs_exist_ok=True)
    shutil.copytree(base/'Lib',runtime/'Lib',ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests'),dirs_exist_ok=True)
    shutil.copytree(Path(sysconfig.get_paths()['purelib']),runtime/'Lib/site-packages',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    (runtime/'python38._pth').write_text('Lib\nDLLs\nLib/site-packages\n..\nimport site\n',encoding='ascii')
    archive=ROOT/'.build-cache/rapidocr-win7.7z';archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(ENGINE_URL,timeout=120) as r,archive.open('wb') as f:shutil.copyfileobj(r,f)
    assert digest(archive)==ENGINE_SHA,'Upstream engine SHA256 mismatch'
    extract=ROOT/'.build-cache/rapidocr-extracted';extract.mkdir(exist_ok=True)
    subprocess.run(['7z','x',str(archive),'-o'+str(extract),'-y'],check=True)
    exes=list(extract.rglob('RapidOCR_json.exe'))+list(extract.rglob('RapidOCR-json.exe'))
    assert len(exes)==1,exes
    engine=payload/'soft/rapidocr';shutil.copytree(exes[0].parent,engine,dirs_exist_ok=True)
    models=engine/'models';names={p.name for p in models.iterdir()}
    def choose(*options):
        for n in options:
            if n in names:return n
        raise RuntimeError('No suitable model: '+str(options)+' Available: '+str(sorted(names)))
    spec={'executable':(engine/exes[0].name).relative_to(payload).as_posix(),'models':{
        'det':choose('ch_PP-OCRv4_det_infer.onnx','ch_PP-OCRv3_det_infer.onnx'),
        'cls':choose('ch_ppocr_mobile_v2.0_cls_infer.onnx'),
        'rec':choose('ch_PP-OCRv4_rec_infer.onnx','ch_PP-OCRv3_rec_infer.onnx'),
        'keys':choose('ppocr_keys_v1.txt')}}
    (payload/'legacy_engine.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    # Use the engine's own legacy VC DLLs when included, never builder VS2022 DLLs.
    for dll in engine.rglob('*.dll'):
        if dll.name.lower().startswith(('msvcp140','vcruntime140','vcomp140')) and not (runtime/dll.name).exists():shutil.copy2(dll,runtime/dll.name)
    script='@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\nif not exist logs mkdir logs\r\n"%~dp0runtime\\python.exe" "%~dp0win7_diagnostics.py" > "%~dp0logs\\startup-check.txt" 2>&1\r\nif not "%errorlevel%"=="0" goto failed\r\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0desktop_app.py"\r\nexit /b\r\n:failed\r\necho Compatibility check failed. See logs\\startup-check.txt.\r\necho Windows 7 SP1 x64 and approved Universal CRT prerequisites are required.\r\npause\r\n'
    (payload/'Start.bat').write_bytes(script.encode('ascii'));(payload/'启动软件.bat').write_bytes(script.encode('ascii'))
    check='@echo off\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" "%~dp0win7_diagnostics.py"\r\npause\r\n';(payload/'检查运行环境.bat').write_bytes(check.encode('ascii'))
    for src in ['WIN7_GUIDE.md','WIN7_TEST_SCOPE.md','SCALE_LOCATION_FIX.md']:shutil.copy2(ROOT/'packaging'/src,payload/src)
    # Preserve complete upstream binary distribution (including its licenses/models).
    upstream=ROOT/'packaging/RAPIDOCR_LICENSE.txt';shutil.copy2(upstream,payload/'RAPIDOCR_LICENSE.txt')
    (payload/'THIRD_PARTY_NOTICES.txt').write_text('Python: PSF License, runtime/LICENSE.txt.\nRapidOCR-json v0.2.0: MIT, RAPIDOCR_LICENSE.txt; '+ENGINE_URL+'\nRapidOcrOnnx/ONNX Runtime/PaddleOCR model licenses: see bundled upstream files and upstream source.\nOther package metadata and licenses remain in runtime/Lib/site-packages.\nNo proprietary trial records or real outlines are included.\n',encoding='utf-8')
    return payload

def package():
    payload=ROOT/'dist/TrialRecords-Win7';target=ROOT/'dist/TrialRecords-Win7-SP1-x64-Portable-Trial.zip'
    import runpy
    generate_demo=runpy.run_path(str(ROOT/'demo_vehicle_data.py'))['generate_demo']
    generate_demo(payload/'examples/multi_vehicle')
    for car in 'ABCDEF':
        subprocess.run([str(payload/'runtime/python.exe'),str(payload/'split_experiments.py'),'import-outline','--vehicle',car,
            '--input',str(payload/'examples/multi_vehicle/full_outlines'/(car+'_outline.pdf')),'--out',str(payload)],check=True)
    verification = """
from pathlib import Path
from argparse import Namespace
import tempfile,shutil
import vehicle_outlines as vo
import outline_catalog as oc
from split_experiments import cmd_import_outline
root=Path.cwd()
bank=vo.VehicleBank.load(root/'outlines')
assert set(bank.catalogs)==set('ABCDEF')
assert all(c.example and len(c.entries)==3 for c in bank.catalogs.values())
with tempfile.TemporaryDirectory() as temp:
    folder=Path(temp)
    shutil.copytree(root/'outlines',folder/'outlines')
    real=folder/'real_A.csv'
    real.write_text('大纲序号,科目名称'+chr(10)+'9.1,加速性能试验记录表'+chr(10),encoding='utf-8-sig')
    cmd_import_outline(Namespace(input=str(real),out=str(folder),vehicle='A'))
    replaced=vo.VehicleBank.load(folder/'outlines')
    a=replaced.select('A204')[1];b=replaced.select('B101')[1]
    assert not a.example and b.example
    assert a.match('加速性能试验记录表').number=='9.1'
    assert not oc.prefix_filename('记录','9.1',True,a.example).startswith('示例')
    assert oc.prefix_filename('记录','2.3',True,b.example).startswith('示例')
print('PRELOADED_OUTLINES_AND_REAL_REPLACEMENT: PASS')
"""
    subprocess.run([str(payload/'runtime/python.exe'),'-c',verification],cwd=str(payload),check=True)

    (payload/'examples/multi_vehicle/README.txt').write_text('全部为示例，不是真实业务资料。\nA至F示例大纲已预先导入，无需手动导入示例。\n返回主窗口选择mixed_vehicle_records_scan.pdf，识别生成预览，核对保存关闭后点击导出PDF。\n正式使用时在界面导入真实大纲，示例编号不能用于正式归档。\n',encoding='utf-8-sig')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in payload.rglob('*'):
            if p.is_file():z.write(p,'TrialRecords-Win7/'+p.relative_to(payload).as_posix())
    (target.parent/'SHA256SUMS-Win7.txt').write_text(digest(target)+'  '+target.name+'\n',encoding='ascii')
    print(str(target)+' '+str(target.stat().st_size),flush=True)
if __name__=='__main__':
    if '--package-only' in sys.argv:package()
    else:build()
