"""Explicit system checks; does not install software, patches or change security settings."""
import json
import platform
import struct
import sys
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    report={'platform':platform.platform(),'python':sys.version,'bits':struct.calcsize('P')*8,'win7_machine_test':False}
    try:
        if sys.platform=='win32':
            win=sys.getwindowsversion();report['windows_version']=list(win[:5]);report['service_pack']=win.service_pack
            if (win.major,win.minor)==(6,1):
                report['win7_machine_test']=True
                if win.service_pack_major<1:raise RuntimeError('Windows 7 SP1 is required. Ask IT to verify approved system prerequisites.')
        assert report['bits']==64,'64-bit Windows is required'
        import fitz,numpy,PIL,tkinter
        root=tkinter.Tk();root.withdraw();root.update_idletasks();root.destroy()
        from legacy_ocr import LegacyOCR
        engine=LegacyOCR()
        try:
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(600,120),'white');ImageDraw.Draw(image).text((20,30),'A204 20260723',fill='black')
            engine.ocr(numpy.array(image))
        finally:engine.close()
        report.update(status='PASS',pdf_version=fitz.VersionBind,ocr='local RapidOCR-json subprocess started and answered',gui='Tk initialized')
        returncode=0
    except Exception:
        report.update(status='FAIL',error=traceback.format_exc());returncode=1
    (ROOT/'logs').mkdir(exist_ok=True)
    (ROOT/'logs/compatibility-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2));return returncode
if __name__=='__main__':raise SystemExit(main())
