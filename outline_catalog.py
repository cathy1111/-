"""Local outline import and conservative subject-to-number matching."""
from __future__ import annotations
import csv
import difflib
import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

NUMBER = r'(?:[A-Z]\.)?\d+(?:\.\d+)*|[一二三四五六七八九十百]+'
NUMBER_RE = re.compile(r'^(?:' + NUMBER + r')$')
LINE_RE = re.compile(r'^\s*((?:[A-Z]\.)?\d+(?:\.\d+)*|[一二三四五六七八九十百]+)(?:[\s、:：)）.．]+|(?=[\u4e00-\u9fff]))(.+?)\s*$')
HEADERS_NO = ['大纲序号','序号','科目编号','项目编号','编号']
HEADERS_NAME = ['科目名称','试验科目','试验项目','实验名称','项目名称','名称']
CATALOG_HEADERS = ['大纲序号','科目名称','别名','示例标记','来源页码','提取方式','核对提示']

@dataclass(frozen=True)
class OutlineEntry:
    number: str
    name: str
    aliases: tuple = ()
    example: bool = False
    source_page: int = 0
    source_kind: str = ""
    review_note: str = ""

@dataclass
class Match:
    number: str = ''
    status: str = '待匹配'
    candidates: str = ''

@dataclass
class Catalog:
    entries: List[OutlineEntry]
    path: Path
    example: bool = False

    @property
    def sha256(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def match(self, title: str) -> Match:
        title = title.strip()
        if not title or title == '未知':return Match()
        direct = {e.number for e in self.entries if title in (e.name,*e.aliases)}
        if len(direct)==1:return Match(next(iter(direct)),'完整名称匹配')
        if len(direct)>1:return Match('','多项匹配',self.describe(direct))
        key = normalized_name(title)
        normalized = {e.number for e in self.entries if key and any(key==normalized_name(n) for n in (e.name,*e.aliases))}
        if len(normalized)==1:return Match(next(iter(normalized)),'规范名称匹配')
        if len(normalized)>1:return Match('','多项匹配',self.describe(normalized))
        ranked=[]
        for e in self.entries:
            score=max(difflib.SequenceMatcher(None,key,normalized_name(n)).ratio() for n in (e.name,*e.aliases))
            if score>=.5:ranked.append((score,e.number,e.name))
        ranked.sort(key=lambda x:(-x[0],x[1],x[2]))
        # Similar names are suggestions only: never infer a formal outline number.
        return Match('','待匹配','；'.join(f'{no} {name}' for _,no,name in ranked[:3]))

    def describe(self,numbers):
        return '；'.join(f'{e.number} {e.name}' for e in self.entries if e.number in numbers)


def normalize_number(value):
    value=unicodedata.normalize('NFKC',str(value)).strip().upper().rstrip('、.．')
    if not NUMBER_RE.fullmatch(value):raise ValueError('无效大纲序号：'+value+'。请使用3.2.1、A.1等格式。')
    return value


def normalized_name(value):
    value=unicodedata.normalize('NFKC',str(value)).strip().upper()
    # Strip only record-document suffixes, not performance terms such as test,
    # measurement, load state or speed that can distinguish outline subjects.
    value=re.sub(r'(?:原始数据记录表|原始记录表|记录表)$','',value)
    value=re.sub(r'试验$','',value)
    return re.sub(r'[^A-Z0-9\u4e00-\u9fff]','',value)


def clean_title(value):
    value=str(value).strip()
    # Dotted TOC leaders and their page numbers are layout, not subject names.
    value=re.sub(r'[.．…⋯·_]{2,}\s*\d+\s*$','',value).strip()
    return value


def make_entry(number,name,aliases='',example=False):
    name=clean_title(name)
    if not name or name in HEADERS_NAME:raise ValueError('大纲科目名称为空或仍为表头')
    aliases=tuple(a.strip() for a in re.split(r'[;；|\n]',str(aliases)) if a.strip())
    return OutlineEntry(normalize_number(number),name,aliases,example)


def decode_text(blob):
    for encoding in ['utf-8-sig','gb18030']:
        try:return blob.decode(encoding)
        except UnicodeDecodeError:pass
    raise ValueError('目录文本编码无法读取，请另存为UTF-8 CSV或TXT。')


def entries_from_table(rows):
    rows=[list(row) for row in rows if any(str(v or '').strip() for v in row)]
    if not rows:return []
    headers=[str(c or '').strip() for c in rows[0]]
    no=next((headers.index(h) for h in HEADERS_NO if h in headers),None)
    name=next((headers.index(h) for h in HEADERS_NAME if h in headers),None)
    alias=headers.index('别名') if '别名' in headers else None
    example=headers.index('示例标记') if '示例标记' in headers else None
    source_page=headers.index('来源页码') if '来源页码' in headers else None
    source_kind=headers.index('提取方式') if '提取方式' in headers else None
    review_note=headers.index('核对提示') if '核对提示' in headers else None
    start=1 if no is not None and name is not None else 0
    if not start:no,name=0,1
    result=[]
    for row in rows[start:]:
        get=lambda i:'' if i is None or i>=len(row) or row[i] is None else str(row[i]).strip()
        if not get(no) or not get(name):continue
        try:
            e=make_entry(get(no),get(name),get(alias),get(example) in ['示例','是','1','true','TRUE'])
            page=int(get(source_page)) if get(source_page).isdigit() else 0
            result.append(OutlineEntry(e.number,e.name,e.aliases,e.example,page,get(source_kind),get(review_note)))
        except ValueError:
            if start:raise
    return result


def entries_from_lines(lines):
    result=[]
    for line in lines:
        match=LINE_RE.match(unicodedata.normalize('NFKC',str(line)))
        if match:
            number,name=match.groups()
            if re.fullmatch(r'[一二三四五六七八九十百]+',number) and not re.match(r'^[一二三四五六七八九十百]+[\s、:：)）.．]+',str(line)):continue
            try:result.append(make_entry(number,name))
            except ValueError:pass
    return result


def validate_entries(entries):
    unique=[]; seen=set(); by_number={}
    for e in entries:
        old=by_number.get(e.number)
        if old and normalized_name(old.name)!=normalized_name(e.name):
            raise ValueError(f'同一大纲序号{e.number}对应多个不同科目：{old.name} / {e.name}。请先整理目录。')
        by_number[e.number]=e
        key=(e.number,e.name,e.aliases,e.example)
        if key not in seen:unique.append(e);seen.add(key)
    if not unique:raise ValueError('未提取到带序号的科目。请使用含“大纲序号、科目名称”的Excel/CSV，或检查PDF/Word中的编号是否为可见文字。')
    return unique


def read_source(path: Path, ocr_texts=None):
    path=Path(path)
    if not path.is_file():raise ValueError('找不到试验大纲文件：'+str(path))
    ext=path.suffix.lower();notes=[]
    if ext in ['.csv','.tsv']:
        text=decode_text(path.read_bytes())
        rows=list(csv.reader(io.StringIO(text),delimiter='\t' if ext=='.tsv' else ','))
        entries=entries_from_table(rows)
    elif ext=='.txt':entries=entries_from_lines(decode_text(path.read_bytes()).splitlines())
    elif ext=='.xlsx':
        try:import openpyxl
        except ImportError:raise ValueError('缺少openpyxl；已安装原依赖的电脑通常已包含它，也可把目录另存为CSV。') from None
        wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
        try:
            entries=[]
            for sheet in wb:entries+=entries_from_table(sheet.iter_rows(values_only=True))
        finally:wb.close()
        notes.append('Excel序号列建议设为文本，避免3.10被保存成3.1。')
    elif ext=='.docx':
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        with zipfile.ZipFile(path) as z:root=ET.fromstring(z.read('word/document.xml'))
        entries=[]
        for table in root.findall('.//w:tbl',ns):
            rows=[]
            for tr in table.findall('w:tr',ns):
                rows.append([''.join(t.text or '' for t in tc.findall('.//w:t',ns)) for tc in tr.findall('w:tc',ns)])
            entries+=entries_from_table(rows)
        lines=[''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns)]
        entries+=entries_from_lines(lines)
        notes.append('Word自动列表编号可能未包含在文字中；请核对导入清单，缺号时另存为带可见编号的PDF或Excel。')
    elif ext=='.pdf':
        from full_outline_pdf import extract_full_pdf
        return extract_full_pdf(path,ocr_texts)
    else:raise ValueError('支持CSV、XLSX、DOCX、PDF、TXT；旧版DOC/XLS请先另存为新格式。')
    entries=validate_entries(entries)
    return Catalog(entries,path,any(e.example for e in entries)),notes


def write_catalog(catalog,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(CATALOG_HEADERS)
        for e in catalog.entries:writer.writerow([e.number,e.name,'；'.join(e.aliases),'示例' if e.example or catalog.example else '',e.source_page or '',e.source_kind,e.review_note])


def add_outline(metas,catalog):
    for meta in metas:
        meta.outline_active=catalog is not None
        meta.outline_example=catalog.example if catalog else False
        if catalog:
            match=catalog.match(meta.experiment)
            meta.outline_no=match.number;meta.outline_status=match.status;meta.outline_candidates=match.candidates
        else:
            meta.outline_no='';meta.outline_status='未启用';meta.outline_candidates=''
    return metas


def prefix_filename(base,number='',active=False,example=False):
    if not active:return base
    prefix=normalize_number(number) if number else '待匹配'
    return ('示例-' if example else '')+prefix+'-'+base
