"""Generate obvious examples, never real compliance requirements or signatures."""
import json
from pathlib import Path
import fitz

def generate(root):
    root=Path(root);folder=root/'examples/record_audit';folder.mkdir(exist_ok=True,parents=True);rules=root/'audit_rules';rules.mkdir(exist_ok=True)
    fields=[{'name':'示例长度值','kind':'numeric','bbox':[.30,.24,.60,.29],'increment':'0.1','unit':'mm','device_id':'演示量具DEMO-01','resolution':'0.1','accuracy':'±0.5 mm（仅演示，非真实设备资料）'},
        {'name':'试验员签字','kind':'signature','bbox':[.30,.40,.75,.46]},
        {'name':'记录车号必填','kind':'required','bbox':[.30,.56,.65,.62]}]
    profile={'schema':1,'name':'规范检查示例（非正式规则）','example':True,'title_contains':'规范检查演示记录表','basis':'软件演示规则；不能作为正式记录检查依据','page_ratio':595/842,'rotation':0,'fields':fields}
    (rules/'规范检查示例.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    with fitz.open() as output:
        for index in range(2):
            with fitz.open() as source:
                page=source.new_page(width=595,height=842)
                page.insert_text((100,70),'规范检查演示记录表',fontname='china-s',fontsize=20)
                page.insert_text((40,105),'演示资料：非真实试验数据、签名及设备信息',fontname='china-s',fontsize=12)
                page.insert_text((40,145),'页1：填写格式符合示例规则；页2：故意填错小数位并留空。',fontname='china-s',fontsize=11)
                for label,field in zip(['长度值（mm）','试验员签字','记录车号'],fields):
                    b=field['bbox'];rect=fitz.Rect(b[0]*595,b[1]*842,b[2]*595,b[3]*842)
                    page.draw_rect(rect,color=(0,0,0),width=.7);page.insert_text((40,rect.y0+25),label,fontname='china-s',fontsize=13)
                page.insert_text((200,232),'12.3' if index==0 else '12.34',fontsize=22)
                if index==0:
                    points=[fitz.Point(210,365),fitz.Point(230,351),fitz.Point(222,375),fitz.Point(245,354),fitz.Point(264,370),fitz.Point(281,352),fitz.Point(270,380)]
                    shape=page.new_shape();shape.draw_polyline(points);shape.finish(color=(0,0,0),width=2);shape.commit()
                    page.insert_text((200,505),'A204',fontsize=20)
                page.insert_text((40,720),'签字区域笔画为程序生成，仅用于测试有无墨迹；不代表有效签名。',fontname='china-s',fontsize=11)
                png=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).tobytes('png')
                p=output.new_page(width=595,height=842);p.insert_image(p.rect,stream=png)
        output.set_metadata({'title':'规范检查扫描示例（非真实资料）','subject':'EXAMPLE_RECORD_AUDIT'})
        output.save(str(folder/'规范检查扫描示例.pdf'),deflate=True)
    return folder/'规范检查扫描示例.pdf',rules/'规范检查示例.json'
if __name__=='__main__':generate(Path(__file__).resolve().parent)
