"""Functional checks on a modern Windows runner; explicitly NOT a Win7 OS certification."""
import argparse
import csv
import json
import shutil
import sys
from pathlib import Path
app=Path(sys.argv[1]).resolve()
assert Path(sys.prefix).resolve()==app/'runtime'
assert sys.version_info[:2]==(3,8)
import fitz,numpy,PIL,tkinter
for module in [fitz,numpy,PIL]:assert str(Path(module.__file__).resolve()).startswith(str(app/'runtime'))
from desktop_app import DesktopApp
from outline_manager import OutlineManager
for factory in [DesktopApp,OutlineManager]:
    root=tkinter.Tk();root.withdraw();factory(root);root.update_idletasks();root.destroy()
from split_experiments import get_ocr,cmd_import_outline,cmd_preview,cmd_split
from demo_vehicle_data import generate_demo
folder=app/'examples/multi_vehicle';generate_demo(folder)
for car in 'ABCDEF':cmd_import_outline(argparse.Namespace(input=str(folder/'full_outlines'/(car+'_outline.pdf')),out=str(app),vehicle=car))
args=argparse.Namespace(input=str(folder/'mixed_vehicle_records_scan.pdf'),out=str(app/'out'),version='V011',top_ratio=.4,max_pages=None,outline=None,rescan=False)
try:
    cmd_preview(args)
    with (app/'out/preview.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert [r['车号'] for r in rows]==['A204','B101','C301','D401','E202','F601'],rows
    assert [r['大纲序号'] for r in rows]==[f'{n}.3' for n in range(1,7)],rows
    assert all(r['时间码']=='20260723' and r['试验地点']=='河北官厅' for r in rows),rows
    cmd_split(args);assert len(list((app/'out').glob('*.pdf')))==6
finally:get_ocr().close()
report={'result':'PASS','python':sys.version,'pdf':fitz.VersionBind,'ocr':'RapidOCR-json v0.2.0','gui':'PASS','scanned_pages':6,
    'outbound':'Python and OCR executables blocked by Windows Firewall','windows7_real_machine_test':'NOT PERFORMED','status':'compatibility trial'}
(app/'BUILD_TEST_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('WIN7_BUILD_SMOKE_REPORT='+json.dumps(report,ensure_ascii=False),flush=True)
for name in ['out','outlines','logs','examples','__pycache__']:
    if (app/name).exists():shutil.rmtree(app/name)
for name in ['outline_manager_state.json','.outline_manager.lock','desktop_state.json','.desktop_app.lock']:
    p=app/name
    if p.exists():p.unlink()
