"""Per-page durable OCR checkpoint, bound to PDF bytes and recognizer/rule versions."""
import hashlib
import json
import os
from pathlib import Path
from outline_manager_backend import InstanceLock

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

def identity(pdf,ratio,root):
    root=Path(root);files=['split_experiments.py','legacy_ocr.py','field_rules.json','locations.csv','location_catalog.py','legacy_engine.json']
    config=root/'legacy_engine.json'
    if config.is_file():
        spec=json.loads(config.read_text(encoding='utf-8'));exe=root/spec['executable'];files.append(str(exe))
        files += [str(exe.parent/'models'/v) for v in spec['models'].values()]
    else:
        files += [str(p) for p in sorted((root/'soft/paddleocr_models').rglob('inference.*')) if p.is_file()]
    hashes={str(name):hash_file(root/name) for name in files if (root/name).is_file()}
    return {'schema':1,'pdf_sha256':hash_file(pdf),'top_ratio':ratio,'recognizer_rules':hashes}

class Checkpoint:
    def __init__(self,root,source):
        root=Path(root);root.mkdir(parents=True,exist_ok=True);self.key=hashlib.sha256(encode(source)).hexdigest();self.path=root/(self.key+'.jsonl');self.lock=InstanceLock(root/(self.key+'.lock'));self.stream=None;self.rows=[]
    def __enter__(self):
        if not self.lock.acquire():raise RuntimeError('同一PDF正在另一个识别任务中处理，请等待该任务结束')
        try:
            self.stream=self.path.open('a+b');self.stream.seek(0);valid=0
            while True:
                line=self.stream.readline()
                if not line:break
                try:
                    item=json.loads(line.decode('utf-8'));meta=item['meta']
                    if meta['page_index']!=len(self.rows) or item['sha256']!=hashlib.sha256(encode(meta)).hexdigest():break
                    self.rows.append(meta);valid=self.stream.tell()
                except (ValueError,KeyError,TypeError,UnicodeError):break
            self.stream.seek(valid);self.stream.truncate();self.stream.flush()
            return self
        except BaseException:self.__exit__(None,None,None);raise
    def append(self,meta):
        if meta['page_index']!=len(self.rows):raise ValueError('识别检查点页码顺序异常')
        item={'meta':meta,'sha256':hashlib.sha256(encode(meta)).hexdigest()}
        self.stream.write(encode(item)+b'\n');self.stream.flush();os.fsync(self.stream.fileno());self.rows.append(meta)
    def __exit__(self,*args):
        if self.stream:self.stream.close();self.stream=None
        self.lock.release()
