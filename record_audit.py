"""Offline, evidence-based record screening; never certifies signatures or metrology."""
import argparse
import csv
from datetime import datetime
from decimal import Decimal,InvalidOperation
import hashlib
import html
import json
import math
from pathlib import Path
import re
import unicodedata
import uuid
import fitz
import numpy as np
from PIL import Image

KINDS={'numeric','signature','required'}

def positive_decimal(value):
    number=Decimal(str(value))
    if not number.is_finite() or number<=0:raise ValueError('记录步长/分辨力必须是正数')
    return number

def validate(profile):
    if profile.get('schema')!=1 or not profile.get('name','').strip():raise ValueError('检查模板格式或名称无效')
    if not profile.get('fields'):raise ValueError('请先在原始记录样张上框选至少一个检查区域')
    if not profile.get('basis','').strip():raise ValueError('请填写检查依据（如记录填写规范及条款），示例不能作为正式依据')
    if not math.isfinite(float(profile['page_ratio'])) or profile['page_ratio']<=0:raise ValueError('页面比例无效')
    names=set()
    for field in profile['fields']:
        name=field.get('name','').strip()
        if not name or name in names:raise ValueError('检查项名称不能为空或重复')
        names.add(name)
        if field.get('kind') not in KINDS:raise ValueError('检查项类型无效')
        b=field.get('bbox',[])
        if len(b)!=4 or not all(math.isfinite(float(v)) and 0<=float(v)<=1 for v in b) or b[2]-b[0]<.005 or b[3]-b[1]<.005:raise ValueError('框选区域无效')
        if field['kind']=='numeric':
            positive_decimal(field.get('increment',''))
            if field.get('resolution'):positive_decimal(field['resolution'])
    return profile

def numeric_result(text,confidence,field):
    text=unicodedata.normalize('NFKC',text).strip().replace('−','-').replace('，',',')
    matches=re.findall(r'(?<![\d.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])',text)
    if len(matches)!=1 or not math.isfinite(confidence) or not 0<=confidence<=1:return '待人工复核','数值未唯一识别或OCR置信度不足；不能据此判定填写精度'
    raw=matches[0];value=Decimal(raw);step=positive_decimal(field['increment'])
    decimals=max(0,-step.normalize().as_tuple().exponent)
    written=len(raw.split('.')[1]) if '.' in raw else 0
    mismatch=written!=decimals or value%step!=0
    if confidence<.90:
        detail='OCR置信度不足，须先核对识别值'
        if mismatch:detail+=f'；候选{raw}与要求步长{step}、小数位{decimals}不符，但不能据此认定填写错误'
        return '待人工复核',detail
    if mismatch:
        return '疑似填写格式不符',f'识别为{raw}，要求步长{step}、小数位{decimals}；请核对原图及填写规范'
    return '未发现格式问题',f'识别值满足配置的步长{step}、小数位{decimals}；仍需确认OCR和规则适用性'

def ink_metrics(image):
    gray=np.asarray(image.convert('L'));height,width=gray.shape
    if height<6 or width<6:return {'ink':False,'pixels':0,'ratio':0.0}
    mask=gray<180
    # Suppress form borders/grid lines, not handwriting identity analysis.
    rows=np.where(mask.mean(axis=1)>.70)[0];cols=np.where(mask.mean(axis=0)>.70)[0]
    for y in rows:mask[max(0,y-1):min(height,y+2),:]=False
    for x in cols:mask[:,max(0,x-1):min(width,x+2)]=False
    border=max(2,int(min(height,width)*.03));mask=mask[border:-border,border:-border]
    if not mask.size:return {'ink':False,'pixels':0,'ratio':0.0}
    # Discard isolated scan speckles (pixels without any black neighbor).
    neighbors=np.zeros(mask.shape,dtype=np.uint8)
    neighbors[1:]+=mask[:-1];neighbors[:-1]+=mask[1:];neighbors[:,1:]+=mask[:,:-1];neighbors[:,:-1]+=mask[:,1:]
    count=int(np.count_nonzero(mask & (neighbors>0)));ratio=count/mask.size
    return {'ink':count>=max(18,mask.size*.003),'pixels':count,'ratio':round(ratio,6)}

def read_crop(image,ocr):
    result=ocr.ocr(np.array(image.convert('RGB')),cls=True,det=False)
    found=[]
    def visit(item):
        if isinstance(item,(tuple,list)):
            if len(item)==2 and isinstance(item[0],str) and isinstance(item[1],(int,float)):found.append((item[0],float(item[1])))
            else:
                for child in item:visit(child)
    visit(result)
    return ' '.join(t for t,_ in found),min((s for _,s in found),default=0.0)

def device_notes(field):
    notes=[]
    if field.get('kind')=='numeric':
        if not field.get('device_id') or not field.get('resolution'):notes.append('设备编号/分辨力未配置，不能验证设备与填写要求的对应关系')
        elif positive_decimal(field['increment'])<positive_decimal(field['resolution']):notes.append('规则待核对：记录步长细于设备分辨力，不能据此增加测量信息')
        if not field.get('accuracy'):notes.append('设备准确度资料未配置；小数位检查不等于准确度合格判定')
    return notes

def audit(input_pdf,profile,out_root,ocr,emit=print):
    validate(profile);input_pdf=Path(input_pdf).resolve();out_root=Path(out_root).resolve()
    run=out_root/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]);run.mkdir(parents=True)
    (run/'evidence').mkdir();rows=[]
    profile_json=json.dumps(profile,ensure_ascii=False,sort_keys=True)
    (run/'used_rules.json').write_text(profile_json,encoding='utf-8')
    with fitz.open(str(input_pdf)) as doc:
        if doc.needs_pass:raise ValueError('PDF已加密，请使用有权读取且已解密的副本')
        for index,page in enumerate(doc):
            emit(f'规范检查：第{index+1}/{len(doc)}页',flush=True)
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            reason=''
            if abs(image.width/image.height-profile['page_ratio'])/profile['page_ratio']>.04 or page.rotation!=profile.get('rotation',0):reason='页面比例或方向与模板不一致，请重新框选；本页未检查'
            title=profile.get('title_contains','').strip()
            if not reason and title:
                from split_experiments import ocr_boxes
                from io import BytesIO
                stream=BytesIO();image.crop((0,0,image.width,int(image.height*.22))).save(stream,format='PNG')
                try:header=''.join(b.text for b in ocr_boxes(stream.getvalue()))
                except Exception:header=''
                compact=lambda v:re.sub(r'\s+','',unicodedata.normalize('NFKC',v))
                if compact(title) not in compact(header):reason='未确认模板标题，不能自动套用此检查规则；本页未检查'
            if reason:
                rows.append({'页码':index+1,'检查项':'模板适用性','类型':'template','状态':'未检查','识别内容':'','置信度':'','说明':reason,'设备编号':'','分辨力':'','准确度':'','单位':'','证据图片':''});continue
            for number,field in enumerate(profile['fields'],1):
                box=field['bbox'];crop=image.crop((int(box[0]*image.width),int(box[1]*image.height),int(box[2]*image.width),int(box[3]*image.height)))
                evidence=f'evidence/page-{index+1:04d}-field-{number:02d}.png';crop.save(run/evidence)
                metrics=ink_metrics(crop);text='';confidence=0.0;kind=field['kind']
                if kind=='numeric':
                    try:text,confidence=read_crop(crop,ocr);status,detail=numeric_result(text,confidence,field)
                    except Exception as exc:status,detail='待人工复核','OCR/数值解析未完成：'+str(exc)
                elif kind=='signature':
                    status='检测到笔迹，待复核' if metrics['ink'] else '疑似漏签，待复核'
                    detail='仅分析填写区墨迹，不能判断是否为签名、签名人身份、真伪或授权有效性'
                else:
                    status='检测到填写痕迹，待复核' if metrics['ink'] else '疑似漏填，待复核'
                    detail='仅判断区域是否有可见填写痕迹；不代表内容正确'
                notes=device_notes(field)
                rows.append({'页码':index+1,'检查项':field['name'],'类型':kind,'状态':status,'识别内容':text,'置信度':round(confidence,4),
                    '说明':detail+('；'+'；'.join(notes) if notes else ''),'设备编号':field.get('device_id',''),'分辨力':field.get('resolution',''),
                    '准确度':field.get('accuracy',''),'单位':field.get('unit',''),'证据图片':evidence})
    if not rows:raise ValueError('PDF没有可检查页面')
    with (run/'检查清单.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader()
        for row in rows:
            writer.writerow({key:("'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value) for key,value in row.items()})
    metadata={'input':str(input_pdf),'input_sha256':file_hash(input_pdf),'rules_sha256':hashlib.sha256(profile_json.encode('utf-8')).hexdigest(),
        'example_rules':bool(profile.get('example')),'basis':profile['basis'],'notice':'辅助筛查，不作规范符合性或计量有效性的最终结论'}
    (run/'检查信息.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    e=lambda v:html.escape(str(v),quote=True)
    body=['<!doctype html><meta charset="utf-8"><title>原始记录规范检查</title><style>body{font:16px sans-serif;max-width:1200px;margin:30px auto}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px;vertical-align:top}img{max-width:260px;max-height:130px}.notice{background:#fff1cd;padding:15px}</style>',
        '<h1>原始记录规范辅助检查</h1><p class="notice">本报告仅提供疑点和证据，不作最终合格判定。签字墨迹不代表有效签名；填写位数符合不等于设备准确度符合。'+('当前使用示例规则，不能作为正式检查依据。' if profile.get('example') else '')+'</p>',
        '<p>文件：'+e(input_pdf.name)+'<br>模板：'+e(profile['name'])+'<br>依据：'+e(profile['basis'])+'</p><table><tr><th>页码/项目</th><th>结果</th><th>说明及设备信息</th><th>原图证据</th></tr>']
    for row in rows:
        img='<a href="'+e(row['证据图片'])+'"><img src="'+e(row['证据图片'])+'"></a>' if row['证据图片'] else '本页未检查'
        info=row['说明']+'；设备：'+row['设备编号']+'；分辨力：'+row['分辨力']+'；准确度：'+row['准确度']+'；单位：'+row['单位']
        body.append('<tr><td>'+e(str(row['页码'])+' / '+row['检查项'])+'</td><td>'+e(row['状态'])+'<br>'+e(row['识别内容'])+'</td><td>'+e(info)+'</td><td>'+img+'</td></tr>')
    body.append('</table>');(run/'检查报告.html').write_text('\n'.join(body),encoding='utf-8')
    emit('检查完成：'+str(run/'检查报告.html'),flush=True)
    return run,rows

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',required=True);parser.add_argument('--rules',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    profile=json.loads(Path(args.rules).read_text(encoding='utf-8-sig'))
    from split_experiments import get_ocr
    run,_=audit(args.input,profile,args.out,get_ocr())
    return 0
if __name__=='__main__':raise SystemExit(main())
