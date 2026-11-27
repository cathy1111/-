"""Exact, human-confirmed place aliases. No fuzzy or default-place substitution."""
import csv
from pathlib import Path
import re
import unicodedata

def normalized(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value))).upper()

def load(path=None):
    path=Path(path) if path else Path(__file__).resolve().parent/'locations.csv'
    if not path.is_file():return {}
    mappings={}
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if not {'标准地点','已确认误读'}.issubset(set(reader.fieldnames or [])):raise ValueError('地点词典缺少标准地点/已确认误读列')
        for row in reader:
            name=normalized(row.get('标准地点',''))
            if not name:continue
            values=[name]+[normalized(v) for v in re.split(r'[;；]',row.get('已确认误读','')) if v.strip()]
            for value in values:
                if value in mappings and mappings[value]!=name:raise ValueError('地点别名对应多个标准地点：'+value)
                mappings[value]=name
    return mappings

def resolve(value,mappings):
    if not value:return value,''
    key=normalized(value)
    if key in mappings:
        corrected=mappings[key]
        return corrected,('已确认地点误读修正：'+value+'→'+corrected) if corrected!=value else ''
    return value,'地点未列入已确认词典，请核对原图' if mappings else ''
