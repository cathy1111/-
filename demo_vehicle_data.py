"""Generate conspicuously marked, non-business full outlines and scanned records."""
from pathlib import Path
import fitz

FONT='china-s'

def _page(doc,title):
    page=doc.new_page(width=595,height=842)
    page.insert_text((45,35),'软件演示示例大纲 - 非真实试验大纲',fontname=FONT,fontsize=12,color=(.65,0,0))
    page.insert_text((45,85),title,fontname=FONT,fontsize=18)
    return page


def generate_demo(folder):
    folder=Path(folder);outlines=folder/'full_outlines';outlines.mkdir(parents=True,exist_ok=True)
    subjects=['外部尺寸与几何特性参数测定','装备质量质心测定','加速性能试验']
    numbers={'A':'A204','B':'B101','C':'C301','D':'D401','E':'E202','F':'F601'}
    for index,vehicle in enumerate('ABCDEF',1):
        with fitz.open() as doc:
            cover=_page(doc,vehicle+'车试验大纲（完整示例）')
            cover.insert_text((45,145),'包含封面、目录和正文，仅用于软件功能测试。',fontname=FONT,fontsize=13)
            cover.insert_text((45,180),'科目序号为自动生成的演示编号，不能作为正式编号。',fontname=FONT,fontsize=13)
            toc=_page(doc,'目 录')
            for j,name in enumerate(subjects,1):toc.insert_text((50,145+j*45),f'{index}.{j} {name} ...... {j+2}',fontname=FONT,fontsize=12)
            for j,name in enumerate(subjects,1):
                page=_page(doc,f'{index}.{j} {name}')
                page.insert_text((45,145),f'{index}.{j}.1 试验条件',fontname=FONT,fontsize=14)
                page.insert_text((45,180),'正文示例：准备记录表，检查车辆状态及试验设备。',fontname=FONT,fontsize=12)
                page.insert_text((45,225),f'{index}.{j}.2 试验方法',fontname=FONT,fontsize=14)
                page.insert_text((45,260),'该正文用于验证目录优先，不能把正文步骤当成试验科目。',fontname=FONT,fontsize=12)
            doc.set_metadata({'title':vehicle+'车完整试验大纲（示例）','subject':'EXAMPLE_OUTLINE','keywords':'DEMO_ONLY'})
            doc.save(outlines/(vehicle+'_outline.pdf'),deflate=True)
    scan_path=folder/'mixed_vehicle_records_scan.pdf'
    with fitz.open() as records:
        for index,vehicle in enumerate('ABCDEF',1):
            with fitz.open() as source:
                page=source.new_page(width=595,height=842)
                page.insert_text((40,32),'软件演示示例记录 - 非真实试验数据',fontname=FONT,fontsize=12,color=(.65,0,0))
                page.insert_text((140,85),'加速性能试验记录表',fontname=FONT,fontsize=19)
                page.draw_rect(fitz.Rect(35,110,560,215))
                page.draw_line(fitz.Point(35,145),fitz.Point(560,145))
                page.draw_line(fitz.Point(35,180),fitz.Point(560,180))
                page.insert_text((45,134),'试验时间：2026年7月23日',fontname=FONT,fontsize=13)
                page.insert_text((320,134),'试验地点：河北官厅',fontname=FONT,fontsize=13)
                page.insert_text((45,169),'车辆条件  车号：'+numbers[vehicle],fontname=FONT,fontsize=13)
                page.insert_text((320,169),'里程：100 km',fontname=FONT,fontsize=13)
                page.insert_text((45,204),'天气：晴  温度：25 C  湿度：60%',fontname=FONT,fontsize=12)
                page.insert_text((45,280),'试验科目：加速性能试验；仅为演示填写的打印文字。',fontname=FONT,fontsize=13)
                page.insert_text((45,325),f'本页应选择{vehicle}车大纲，演示序号应为{index}.3。',fontname=FONT,fontsize=13)
                png=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).tobytes('png')
                target=records.new_page(width=595,height=842)
                target.insert_image(target.rect,stream=png)
        records.set_metadata({'title':'A-F混合车辆扫描记录（示例）','subject':'EXAMPLE_RECORDS'})
        records.save(scan_path,deflate=True)
    (folder/'README.txt').write_text('全部为软件生成的示例，不是真实业务资料。\n先用import_vehicle_outline.bat逐个绑定A~F车的full_outlines目录PDF。\n再用run_preview.bat输入mixed_vehicle_records_scan.pdf，核对后run_export.bat导出。\n预期A204对应1.3，B101对应2.3，C301对应3.3，D401对应4.3，E202对应5.3，F601对应6.3。\n输出必须带示例标记。后续逐车导入真实大纲后，该车输出不再带示例。\n',encoding='utf-8-sig')
    print('已生成6份完整示例大纲及混合车辆扫描记录：'+str(folder),flush=True)
    print('全部使用示例标记，真实使用前请逐车替换成真实大纲。',flush=True)
