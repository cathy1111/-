"""Local RapidOCR-json subprocess bridge for the Windows 7 compatibility build."""
import atexit
import base64
import io
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from PIL import Image, ImageOps

ROOT=Path(__file__).resolve().parent

class LegacyOCR:
    def __init__(self):
        spec=json.loads((ROOT/'legacy_engine.json').read_text(encoding='utf-8'))
        exe=ROOT/spec['executable'];self.lock=threading.Lock();self.lines=queue.Queue()
        args=[str(exe),'--ensureAscii=1','--numThread=2','--maxSideLen=2048','--models='+str(exe.parent/'models')]
        args += ['--'+k+'='+v for k,v in spec['models'].items()]
        self.process=subprocess.Popen(args,cwd=str(exe.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
        def reader():
            for line in self.process.stdout:self.lines.put(line.decode('utf-8',errors='replace').strip())
            self.lines.put(None)
        threading.Thread(target=reader,daemon=True).start();atexit.register(self.close)
        try:
            while True:
                line=self.lines.get(timeout=45)
                if line is None:raise RuntimeError('OCR engine exited during startup. Check Win7 SP1/runtime prerequisites.')
                if 'OCR init completed.' in line:break
        except BaseException:self.close();raise
    def close(self):
        proc=getattr(self,'process',None)
        if proc and proc.poll() is None:
            proc.kill()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
    def ocr(self,arr,cls=True,det=True):
        image=Image.fromarray(arr)
        if not det:image=ImageOps.expand(image,border=25,fill='white')
        stream=io.BytesIO();image.save(stream,format='PNG')
        request=json.dumps({'image_base64':base64.b64encode(stream.getvalue()).decode('ascii')})+'\n'
        with self.lock:
            if self.process.poll() is not None:raise RuntimeError('Local OCR engine has exited. Restart recognition.')
            self.process.stdin.write(request.encode('ascii'));self.process.stdin.flush()
            try:
                while True:
                    line=self.lines.get(timeout=180)
                    if line is None:raise RuntimeError('Local OCR engine terminated during recognition')
                    try:result=json.loads(line)
                    except ValueError:continue
                    if isinstance(result,dict) and 'code' in result:break
            except queue.Empty:
                self.close();raise RuntimeError('Local OCR recognition timed out')
        if result['code']==101:return [[]]
        if result['code']!=100:raise RuntimeError('Local OCR error '+str(result['code'])+': '+str(result.get('data')))
        if not det:return [[(item['text'],float(item['score'])) for item in result['data']]]
        return [[(item['box'],(item['text'],float(item['score']))) for item in result['data']]]
