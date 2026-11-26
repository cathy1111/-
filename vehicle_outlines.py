"""Vehicle-scoped outline selection. No fallback to another vehicle's directory."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from pathlib import Path
import outline_catalog as oc


def vehicle_key(value):
    value=unicodedata.normalize('NFKC',str(value)).upper().strip()
    value=re.sub(r'\s+','',value)
    value=value[:-1] if value.endswith('车') else value
    value=value.replace('-','')
    if not re.fullmatch(r'[A-Z]{1,3}(?:\d{1,6})?',value):
        raise ValueError('大纲车辆请填A、B、C等类别，或A204等完整车号。不能使用纯数字或未知车号。')
    return value


class VehicleBank:
    def __init__(self,root,catalogs):
        self.path=Path(root)
        self.catalogs=catalogs
        self.entries=[entry for catalog in catalogs.values() for entry in catalog.entries]
        self.example=any(c.example for c in catalogs.values())
    @classmethod
    def load(cls,root):
        root=Path(root);catalogs={}
        if root.is_dir():
            for path in sorted(root.glob('vehicle_*.csv')):
                match=re.fullmatch(r'vehicle_([A-Z]{1,3}(?:\d{1,6})?)\.csv',path.name)
                if match:catalogs[match.group(1)]=oc.read_source(path)[0]
        return cls(root,catalogs) if catalogs else None
    def select(self,number):
        try:key=vehicle_key(number)
        except ValueError:return '',None
        if key in self.catalogs:return key,self.catalogs[key]
        prefix=re.match(r'[A-Z]+',key).group()
        if prefix in self.catalogs:return prefix,self.catalogs[prefix]
        return '',None
    def snapshot(self):
        return {key:{'path':str(cat.path.resolve()),'sha256':cat.sha256,'example':cat.example,
                     'numbers':sorted({e.number for e in cat.entries})} for key,cat in self.catalogs.items()}


def apply_bank(metas,bank):
    for meta in metas:
        key,catalog=bank.select(meta.vehicle)
        meta.outline_active=True
        meta.outline_vehicle=key
        meta.outline_source=catalog.path.name if catalog else ''
        meta.outline_example=catalog.example if catalog else False
        if catalog:
            match=catalog.match(meta.experiment)
            meta.outline_no=match.number;meta.outline_status=match.status;meta.outline_candidates=match.candidates
        else:
            meta.outline_no='';meta.outline_candidates=''
            meta.outline_status='车号不明确或该车大纲未导入'
    return metas


def verify_bank(data,metas):
    current=VehicleBank.load(Path(data['root']))
    if current is None or current.snapshot()!=data['catalogs']:
        raise ValueError('车辆大纲库已改变，请重新生成预览后核对，避免套用其他车辆或旧版编号。')
    changed=False
    for meta in metas:
        key,catalog=current.select(meta.vehicle)
        if not meta.outline_active:raise ValueError('清单车辆大纲模式不能改为停用，请重新预览。')
        if key!=meta.outline_vehicle:
            if key and catalog and not meta.outline_vehicle and not meta.outline_no:
                match=catalog.match(meta.experiment)
                meta.outline_vehicle=key;meta.outline_source=catalog.path.name
                meta.outline_example=catalog.example;meta.outline_no=match.number
                meta.outline_status='人工核对车号后：'+match.status
                meta.outline_candidates=match.candidates;changed=True
            else:
                raise ValueError(f'第{meta.page_index+1}页车号与“大纲车辆”不对应。核对车号后，可清空本页“大纲车辆”和“大纲序号”，再导出以重新匹配；不能保留旧车编号。')
        if catalog is None:
            if meta.outline_no or meta.outline_example:raise ValueError('没有对应车辆大纲，不能手填其他车的编号。请先导入该车大纲。')
            continue
        info=data['catalogs'][key]
        if meta.outline_example!=info['example']:raise ValueError('车辆目录的示例标记被改变，请重新预览。')
        if meta.outline_no and meta.outline_no not in info['numbers']:
            raise ValueError(f'第{meta.page_index+1}页编号不在{key}车大纲内，不能使用其他车辆的编号。')

    return changed


if __name__=='__main__':
    from outline_manager import main
    raise SystemExit(main())
