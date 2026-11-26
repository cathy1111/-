"""Build self-contained Windows payload, portable ZIP and Inno online/offline EXEs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
VERSION='1.6.0'
MODELS={
 'ch_PP-OCRv4_det_infer':'https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar',
 'ch_PP-OCRv4_rec_infer':'https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar',
 'ch_ppocr_mobile_v2.0_cls_infer':'https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/ch_ppocr_mobile_v2.0_cls_infer.tar'}
APP_FILES=['desktop_app.py','outline_manager.py','outline_manager_backend.py','split_experiments.py',
 'outline_catalog.py','vehicle_outlines.py','full_outline_pdf.py','demo_vehicle_data.py','field_rules.json',
 'README.md','MULTI_VEHICLE_GUIDE.md','OUTLINE_MANAGER_GUIDE.md','OUTLINE_GUIDE.md']

def run(args,**kwargs):
    print('RUN: '+' '.join(map(str,args)),flush=True)
    subprocess.run(list(map(str,args)),cwd=str(ROOT),check=True,**kwargs)

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def download(url,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        print('Downloading '+url,flush=True)
        with urllib.request.urlopen(url,timeout=90) as response,path.open('wb') as out:shutil.copyfileobj(response,out)
    return path

def prepare_models():
    dest=ROOT/'soft/paddleocr_models';dest.mkdir(parents=True,exist_ok=True)
    for name,url in MODELS.items():
        target=dest/name
        if (target/'inference.pdmodel').is_file() and (target/'inference.pdiparams').is_file():continue
        archive=download(url,ROOT/'.build-cache'/(name+'.tar'))
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                resolved=(dest/member.name).resolve()
                if dest.resolve() not in resolved.parents or member.issym() or member.islnk():raise ValueError('Unsafe model archive member')
            tar.extractall(dest)
        if not (target/'inference.pdmodel').is_file() or not (target/'inference.pdiparams').is_file():raise ValueError('Incomplete model: '+name)
    return dest

def copy_runtime(target):
    base=Path(sys.base_prefix)
    target.mkdir(parents=True,exist_ok=True)
    # Copy standard Python binaries and libraries, not the builder's global packages.
    for name in ['python.exe','pythonw.exe','python3.dll','python39.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        p=base/name
        if p.is_file():shutil.copy2(p,target/name)
    for name in ['DLLs','tcl']:
        if (base/name).is_dir():shutil.copytree(base/name,target/name,dirs_exist_ok=True)
    shutil.copytree(base/'Lib',target/'Lib',ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests'),dirs_exist_ok=True)
    # The active environment is created clean by the Windows workflow.
    import sysconfig
    site=Path(sysconfig.get_paths()['purelib'])
    shutil.copytree(site,target/'Lib/site-packages',ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    (target/'python39._pth').write_text('Lib\nDLLs\nLib/site-packages\n..\nimport site\n',encoding='ascii')
    if not (target/'python.exe').is_file() or not (target/'tcl').is_dir():raise ValueError('Full Python 3.9 runtime with tcl/tk is required')
    # Ship app-local, redistributable VC runtime DLLs so no global runtime install
    # is needed by the portable package on supported Windows 10/11 x64 systems.
    candidates=[];omp=[]
    for vsroot in ['C:/Program Files/Microsoft Visual Studio/2022','C:/Program Files (x86)/Microsoft Visual Studio/2022']:
        candidates+=list(Path(vsroot).glob('*/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT'))
        omp+=list(Path(vsroot).glob('*/VC/Redist/MSVC/*/x64/Microsoft.VC*.OpenMP'))
    for folder in sorted(candidates+omp):
        for dll in folder.glob('*.dll'):shutil.copy2(dll,target/dll.name)
    if not (target/'msvcp140.dll').is_file() or not (target/'vcomp140.dll').is_file():raise ValueError('VC CRT/OpenMP redistributable DLLs not found on build machine')

def write_startup(payload):
    script='@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0runtime\\pythonw.exe" "%~dp0desktop_app.py"\r\n'
    (payload/'Start.bat').write_bytes(script.encode('ascii'))
    (payload/'启动软件.bat').write_bytes(script.encode('ascii'))
    for name in ['run_preview.bat','run_export.bat','open_outline_manager.bat','import_outline.bat','import_vehicle_outline_cli.bat','make_demo_data.bat','import_vehicle_outline.bat','打开大纲管理.bat']:
        source=ROOT/name
        if source.is_file():
            text=source.read_bytes().decode('ascii').replace('set \"TASK_PY=\"\r\n','set \"TASK_PY=\"\r\ncall :try_python \"%~dp0runtime\\python.exe\"\r\nif defined TASK_PY exit /b\r\n')
            (payload/name).write_bytes(text.encode('ascii'))
    (payload/'使用说明.txt').write_text('完整离线免安装版。解压到纯英文目录（例如C:\\TrialRecords），双击启动软件.bat。\n不需要安装Python，也不需要联网识别。不要单独复制一个exe，必须保留整个文件夹。\n先管理车辆大纲，再选择记录PDF生成清单，核对保存关闭后导出。\n当前软件含本地运行环境，不是服务器模型；手写结果仍需人工核对。\n',encoding='utf-8-sig')
    (payload/'THIRD_PARTY_NOTICES.txt').write_text('Python is distributed under the PSF License (runtime/LICENSE.txt).\nPaddlePaddle and PaddleOCR are open-source software under their respective licenses.\nPackage metadata/licenses are preserved under runtime/Lib/site-packages.\nOCR models obtained from official PaddleOCR model distribution URLs:\n'+'\n'.join(MODELS.values())+'\nVC runtime DLLs are Microsoft redistributable components.\n',encoding='utf-8')

def build_payload():
    if os.name!='nt' or sys.version_info[:2]!=(3,9) or struct.calcsize('P')!=8:raise ValueError('Build on Windows with clean CPython 3.9 x64 environment')
    models=prepare_models();dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    payload=dist/'TrialRecords'
    if payload.exists():shutil.rmtree(payload)
    payload.mkdir()
    for name in APP_FILES:shutil.copy2(ROOT/name,payload/name)
    shutil.copytree(models,payload/'soft/paddleocr_models')
    copy_runtime(payload/'runtime');write_startup(payload)
    return payload

def package(payload,repo,tag):
    dist=ROOT/'dist';portable=dist/'TrialRecords-Portable-Windows-x64.zip'
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED) as z:
        for p in payload.rglob('*'):
            if p.is_file():z.write(p,'TrialRecords/'+p.relative_to(payload).as_posix())
    digest=sha256(portable)
    (dist/'portable-manifest.json').write_text(json.dumps({'version':VERSION,'sha256':digest,'file':portable.name},indent=2))
    compiler=Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe')
    if not compiler.is_file():raise ValueError('Install Inno Setup 6 on the Windows build machine')
    run([compiler,'/DAppVersion='+VERSION,'/DPayloadDir='+str(payload),'/DOutputDir='+str(dist),str(ROOT/'packaging/offline.iss')])
    url='https://github.com/'+repo+'/releases/download/'+tag+'/'+portable.name
    run([compiler,'/DAppVersion='+VERSION,'/DPortableURL='+url,'/DPortableSHA256='+digest,'/DOutputDir='+str(dist),str(ROOT/'packaging/online.iss')])
    files=[portable,dist/f'TrialRecords-Offline-Setup-{VERSION}.exe',dist/f'TrialRecords-Online-Setup-{VERSION}.exe']
    (dist/'SHA256SUMS.txt').write_text('\n'.join(sha256(p)+'  '+p.name for p in files)+'\n',encoding='ascii')
    print('Built all three delivery packages:',*[str(p) for p in files],sep='\n',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo',default='cathy1111/-');parser.add_argument('--tag',default='v1.6.0');parser.add_argument('--payload-only',action='store_true');parser.add_argument('--package-only',action='store_true')
    args=parser.parse_args();payload=ROOT/'dist/TrialRecords' if args.package_only else build_payload()
    if not args.payload_only:package(payload,args.repo,args.tag)
