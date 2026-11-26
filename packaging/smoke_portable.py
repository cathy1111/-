"""Run with the relocated bundled interpreter; its outbound firewall is blocked."""
import argparse
import csv
import ctypes
import json
import shutil
import sys
from pathlib import Path

def under(path,parent):
    try:Path(path).resolve().relative_to(Path(parent).resolve());return True
    except ValueError:return False

def main():
    app=Path(sys.argv[1]).resolve();runtime=app/'runtime'
    assert under(sys.executable,runtime),sys.executable
    assert Path(sys.prefix).resolve()==runtime
    import fitz,numpy,paddle,tkinter
    for module in [fitz,numpy,paddle]:assert under(module.__file__,runtime),module.__file__
    for name in ['msvcp140.dll','vcomp140.dll']:
        dll=ctypes.WinDLL(str(runtime/name));buffer=ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetModuleFileNameW(ctypes.c_void_p(dll._handle),buffer,len(buffer))
        assert under(buffer.value,runtime),buffer.value
    root=tkinter.Tk();root.withdraw();root.update_idletasks();root.destroy()
    from split_experiments import get_ocr,cmd_import_outline,cmd_preview,cmd_split
    from demo_vehicle_data import generate_demo
    from desktop_app import DesktopApp
    from outline_manager import OutlineManager
    root=tkinter.Tk();root.withdraw();DesktopApp(root);root.update_idletasks();root.destroy()
    root=tkinter.Tk();root.withdraw();OutlineManager(root);root.update_idletasks();root.destroy()
    get_ocr();folder=app/'examples/multi_vehicle';generate_demo(folder)
    for car in 'ABCDEF':cmd_import_outline(argparse.Namespace(input=str(folder/'full_outlines'/(car+'_outline.pdf')),out=str(app),vehicle=car))
    args=argparse.Namespace(input=str(folder/'mixed_vehicle_records_scan.pdf'),out=str(app/'out'),version='V011',top_ratio=.4,max_pages=None,outline=None,rescan=False)
    cmd_preview(args)
    with (app/'out/preview.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    assert [r['车号'] for r in rows]==['A204','B101','C301','D401','E202','F601'],[(r['车号'],r['备注']) for r in rows]
    assert [r['大纲序号'] for r in rows]==[f'{n}.3' for n in range(1,7)],rows
    assert all(r['时间码']=='20260723' and r['试验地点']=='河北官厅' for r in rows),rows
    cmd_split(args);assert len(list((app/'out').glob('*.pdf')))==6
    print('PORTABLE_SMOKE_REPORT='+json.dumps({'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,
        'pymupdf':fitz.VersionBind,'device':paddle.device.get_device(),'gui':'passed','real_printed_scan_ocr':'passed','pages':6,
        'network':'blocked_by_windows_firewall'},ensure_ascii=False),flush=True)
    for name in ['out','outlines','logs','examples/multi_vehicle']:
        if (app/name).exists():shutil.rmtree(app/name)
    for name in ['outline_manager_state.json','.outline_manager.lock','desktop_state.json','.desktop_app.lock']:(app/name).unlink(missing_ok=True)

if __name__=='__main__':main()
