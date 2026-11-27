"""Recover verified real outline catalogs from known old application locations."""
import csv
import hashlib
import json
import os
import re
from pathlib import Path
from outline_catalog import normalize_number

CATALOG=re.compile(r'(?:vehicle_[A-Z]{1,3}\d{0,6}|outline_catalog)\.csv$',re.I)

def known_locations(root):
    root=Path(root).resolve()
    folders=[root.parent/name for name in ['TrialRecords','pro','propro']]
    if os.name=='nt':
        folders += [Path('C:/')/name for name in ['TrialRecords','pro','propro']]
        desktop=Path.home()/'Desktop'
        folders += [desktop/name for name in ['TrialRecords','pro','propro']]
        for name in ['数据转换文件']:
            folders += [desktop/name/sub for sub in ['pro','propro']]
    unique=[]
    for folder in folders:
        folder=folder.resolve()
        if folder!=root and folder not in unique:unique.append(folder)
    return unique

def valid_real(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'大纲序号','科目名称'}.issubset(set(reader.fieldnames or [])):raise ValueError('目录列不完整')
        rows=list(reader)
    if not rows:raise ValueError('目录为空')
    for row in rows:
        if not normalize_number(row.get('大纲序号','')):raise ValueError('大纲序号为空')
        if not row.get('科目名称','').strip():raise ValueError('科目名称为空')
        if row.get('示例标记','').strip()=='示例':raise ValueError('示例目录不作为真实大纲迁移')

def migrate(root,sources=None):
    root=Path(root).resolve();report={'copied':[],'conflicts':[],'ignored':[],'errors':[]}
    candidates={}
    for source in known_locations(root) if sources is None else sources:
        source=Path(source).resolve()
        if source==root:continue
        try:
            paths=list((source/'outlines').glob('vehicle_*.csv'))
            paths += [source/'outline_catalog.csv'] if (source/'outline_catalog.csv').is_file() else []
            for path in paths:
                if not CATALOG.fullmatch(path.name):continue
                try:
                    valid_real(path);data=path.read_bytes();key=path.name.lower()
                    candidates.setdefault(key,[]).append((path,data,hashlib.sha256(data).hexdigest()))
                except (OSError,ValueError,UnicodeError,csv.Error) as exc:report['ignored'].append({'path':str(path),'reason':str(exc)})
        except OSError as exc:report['errors'].append(str(exc))
    for name,items in candidates.items():
        target=root/'outline_catalog.csv' if name=='outline_catalog.csv' else root/'outlines'/items[0][0].name
        if target.exists():continue
        if len({item[2] for item in items})!=1:
            report['conflicts'].append({'name':name,'sources':[str(item[0]) for item in items]});continue
        path,data,_=items[0]
        try:
            target.parent.mkdir(exist_ok=True,parents=True)
            # Exclusive creation never overwrites an existing catalog, even on a race.
            with target.open('xb') as stream:stream.write(data)
            report['copied'].append({'source':str(path),'destination':str(target)})
        except FileExistsError:pass
        except OSError as exc:report['errors'].append(str(exc))
    try:
        (root/'logs').mkdir(exist_ok=True,parents=True)
        (root/'logs/outline-migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    except OSError:pass
    count=len(report['copied'])
    if report['conflicts']:message='发现不同版本的旧大纲，未自动选择；请点击①管理车辆大纲，导入需要使用的版本。'
    elif report['errors']:message='旧大纲恢复未全部完成，请查看logs/outline-migration.json，或点击①导入真实大纲。'
    elif count:message=f'已自动找回{count}份真实大纲，无需复制文件夹。请选择PDF，识别核对后导出。'
    elif list((root/'outlines').glob('vehicle_*.csv')) or (root/'outline_catalog.csv').is_file():message='已有大纲可以继续使用。请选择PDF，识别核对后导出。'
    else:message='未找到旧大纲。请点击①管理车辆大纲，选择真实大纲文件；不需要复制任何程序文件夹。'
    return report,message
