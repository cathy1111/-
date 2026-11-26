"""Persistent queue and import worker for the local outline manager; no GUI dependency."""
from __future__ import annotations
import csv
import json
import os
import re
import subprocess
import sys
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from vehicle_outlines import vehicle_key
from outline_catalog import normalize_number

SUPPORTED={'.pdf','.csv','.tsv','.xlsx','.docx','.txt'}

@dataclass(frozen=True)
class ImportJob:
    row_id: str
    vehicle: str
    path: Path


def guess_vehicle(filename):
    stem=unicodedata.normalize('NFKC',Path(filename).stem).upper()
    exact=set(re.findall(r'(?<![A-Z0-9])([A-Z]{1,3}\d{1,6})(?![A-Z0-9])',stem))
    families=set(re.findall(r'(?<![A-Z0-9])([A-F])(?:车|[_ -]+(?:OUTLINE|大纲)|\s+试验大纲)',stem))
    families.update(re.findall(r'(?:车辆|车型|车号)[ _-]*([A-F])(?=[^A-Z0-9]|$)',stem))
    families.update(re.findall(r'(?:大纲|OUTLINE)[ _-]*([A-F])$',stem))
    if re.fullmatch(r'[A-F]',stem):families.add(stem)
    if len(exact)==1:
        value=next(iter(exact));prefix=re.match('[A-Z]+',value).group()
        if not families or families=={prefix}:return value
    if not exact and len(families)==1:return next(iter(families))
    return ''


def prepare_jobs(rows):
    jobs=[];seen=set()
    for row in rows:
        if not row.get('selected'):continue
        code=vehicle_key(row.get('vehicle',''))
        if code in seen:raise ValueError(f'车辆{code}选中了多份大纲，请保留一份，或分别绑定到完整车号。')
        path=Path(row.get('path','')).expanduser()
        if not str(row.get('path','')).strip() or not path.is_file():raise ValueError(f'{code}车的大纲文件不存在，请重新选择。')
        if path.suffix.lower() not in SUPPORTED:raise ValueError(f'{code}车文件格式不支持，请选择PDF、CSV、XLSX、DOCX或TXT。')
        jobs.append(ImportJob(str(row['id']),code,path.resolve()));seen.add(code)
    if not jobs:raise ValueError('请先选择大纲文件，并勾选需要导入的行。')
    return jobs


class StateStore:
    def __init__(self,path):self.path=Path(path)
    def load(self):
        if not self.path.is_file():return []
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('rows'),list):raise ValueError('队列状态格式不正确')
        rows=[]
        for item in data['rows']:
            if isinstance(item,dict):rows.append({'vehicle':str(item.get('vehicle','')),'path':str(item.get('path','')),
                                                 'selected':bool(item.get('selected',False))})
        return rows
    def save(self,rows):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        data={'rows':[{k:r.get(k,'' if k!='selected' else False) for k in ['vehicle','path','selected']} for r in rows]}
        temp=self.path.with_name(self.path.name+'.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(self.path)


def existing_catalog_status(root,vehicle):
    try:code=vehicle_key(vehicle)
    except ValueError:return '请选择车辆'
    path=Path(root)/'outlines'/f'vehicle_{code}.csv'
    if not path.is_file():return '尚未导入'
    try:
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            if not {'大纲序号','科目名称'}.issubset(set(reader.fieldnames or [])):return '目录格式不完整，请重新导入'
            rows=list(reader)
        if not rows:return '目录为空，请检查'
        for row in rows:
            if not row.get('科目名称'):return '目录不完整，请重新导入'
            normalize_number(row.get('大纲序号',''))
        example=any(r.get('示例标记')=='示例' for r in rows)
        return f'已导入 {len(rows)} 项'+('（示例）' if example else '')
    except (OSError,UnicodeError,csv.Error,ValueError):return '目录存在，需检查'


def worker_interpreter(executable=None):
    path=Path(executable or sys.executable)
    # GUI starts under pythonw, but the worker needs python.exe with real pipes
    # so stdout/progress/tracebacks do not disappear on Windows.
    return str(path.with_name('python.exe')) if path.name.lower()=='pythonw.exe' else str(path)


def run_imports(jobs,root,backend_script,stop_event,emit):
    """Only stop between files, so a user cancel does not kill a catalog write."""
    root=Path(root);backend_script=Path(backend_script)
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1')
    successes=failures=0
    for job in jobs:
        if stop_event.is_set():break
        emit({'kind':'started','id':job.row_id,'vehicle':job.vehicle})
        args=[worker_interpreter(),str(backend_script),'import-outline','--vehicle',job.vehicle,'--input',str(job.path),'--out',str(root)]
        try:
            flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
            with subprocess.Popen(args,cwd=str(backend_script.parent),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                  text=True,encoding='utf-8',errors='replace',bufsize=1,creationflags=flags) as process:
                tail=[]
                for line in process.stdout:
                    text=line.rstrip();tail.append(text);tail=tail[-8:]
                    emit({'kind':'log','id':job.row_id,'vehicle':job.vehicle,'text':text})
                code=process.wait()
            if code==0:
                successes+=1;emit({'kind':'success','id':job.row_id,'vehicle':job.vehicle})
            else:
                failures+=1;emit({'kind':'failure','id':job.row_id,'vehicle':job.vehicle,'text':'\n'.join(tail)})
        except Exception as exc:
            failures+=1;emit({'kind':'failure','id':job.row_id,'vehicle':job.vehicle,'text':str(exc)})
    emit({'kind':'finished','successes':successes,'failures':failures,'stopped':stop_event.is_set()})


class InstanceLock:
    def __init__(self,path):self.path=Path(path);self.stream=None
    def acquire(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b')
        if self.path.stat().st_size==0:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            return True
        except OSError:self.stream.close();self.stream=None;return False
    def release(self):
        if self.stream:
            self.stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_UN)
            self.stream.close();self.stream=None
