#!/usr/bin/env python3
"""
用法：
  python3 split_experiments.py preview --input input/test.pdf --out out
  python3 split_experiments.py split --input input/test.pdf --out out --version V01
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
import outline_catalog as outlines
import vehicle_outlines as vehicle_catalogs

_OCR = None
PROGRAM_VERSION = "1.6.0"

TIME_RE = re.compile(
    r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*\D{0,4}日"
)
BAD_FIELD_RE = re.compile(r'[\\/:*?"<>|\s\-·.、，,]+')
TITLE_HINT_RE = re.compile(r".+(记录表|测定表|明细表|试验表)$")
VEHICLE_RE = re.compile(r"([A-Za-z])\s*(\d{2,4})(?!\d)")


@dataclass
class PageMeta:
    page_index: int
    experiment: str
    vehicle: str
    time_raw: str  
    time_code: str 
    location_raw: str
    group_key: str
    filename_base: str
    note: str = ""
    vehicle_raw: str = ""
    location_ocr_raw: str = ""
    outline_no: str = ""
    outline_status: str = "未启用"
    outline_candidates: str = ""
    outline_active: bool = False
    outline_example: bool = False
    outline_vehicle: str = ""
    outline_source: str = ""


def get_ocr():
    global _OCR
    if _OCR is None:
        from paddleocr import PaddleOCR

        root = Path(__file__).resolve().parent / "soft" / "paddleocr_models"
        cache = Path.home() / ".paddleocr" / "whl"
        models = {}
        for key, name, sub in [
            ("det_model_dir", "ch_PP-OCRv4_det_infer", "det/ch"),
            ("rec_model_dir", "ch_PP-OCRv4_rec_infer", "rec/ch"),
            ("cls_model_dir", "ch_ppocr_mobile_v2.0_cls_infer", "cls"),
        ]:
            candidates = [root / name, root / "from_cache" / sub / name, cache / sub / name]
            found = next((d for d in candidates if (d / "inference.pdmodel").is_file() and (d / "inference.pdiparams").is_file()), None)
            if found is None:
                raise FileNotFoundError(f"OCR model missing: {name}. Keep the original soft/paddleocr_models folder.")
            models[key] = str(found)
        _OCR = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False, use_gpu=False, **models)
    return _OCR


def sanitize_field(s: str) -> str:
    s = (s or "").strip()
    s = BAD_FIELD_RE.sub("", s)
    return s or "未知"


def format_time_code(y: str, m: str, d: str) -> str:
    try:
        return date(int(y), int(m), int(d)).strftime("%Y%m%d")
    except ValueError:
        return ""


def display_time(y: str, m: str, d: str) -> str:
    return f"{int(y)}年{int(m)}月{int(d)}日"


def build_filename_base(experiment: str, vehicle: str, time_code: str, location: str) -> str:
    return "-".join(
        [
            sanitize_field(experiment),
            sanitize_field(vehicle),
            sanitize_field(time_code) if time_code else "未知时间",
            sanitize_field(location),
        ]
    )


def render_top_crop(page: fitz.Page, top_ratio: float = 0.4, zoom: float = 2.5) -> bytes:
    r = page.rect
    clip = fitz.Rect(0, 0, r.width, r.height * top_ratio)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    return pix.tobytes("png")


# OCR coordinates are kept so a vehicle identifier is associated with its label,
# rather than with unrelated mileage or instrument numbers later in the page.
@dataclass
class OCRBox:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    confidence: float


VEHICLE_LABEL = re.compile(r"试验车号|车辆编号|试验车编号|车号|检查车辆|检查车号")
OTHER_FIELD = re.compile(r"里程|燃油|油量|摩托|负载|气象|天气|温度|湿度|风力|海拔|序号|仪器|有效期|试验时间|试验地点|检查时间|检查日期|检查地点|检查车辆|检查车号|车型|产品型号")


def compact_text(text: str) -> str:
    import unicodedata
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).upper()


def parse_vehicle_value(text: str) -> str:
    value = compact_text(text).strip(":：,，;；.。|[]()（）")
    value = value.replace("—", "-").replace("–", "-")
    # Preserve every recognized letter and digit; do not guess O/0, B/8 or E/F.
    if re.fullmatch(r"[A-F]车",value):value=value[:-1]
    if re.fullmatch(r"(?:[A-Z]{1,3}-?)?\d{2,6}|[A-F]", value):
        return value
    return ""


def labelled_vehicle(text: str) -> str:
    text = compact_text(text)
    match = VEHICLE_LABEL.search(text)
    if not match:
        return ""
    tail = OTHER_FIELD.split(text[match.end():], maxsplit=1)[0]
    return parse_vehicle_value(tail)


def vehicle_from_texts(texts: List[Tuple[str, float]]) -> str:
    """Conservative fallback for OCR engines with no box coordinates."""
    for i, (text, confidence) in enumerate(texts):
        if not VEHICLE_LABEL.search(compact_text(text)):
            continue
        direct = labelled_vehicle(text)
        if direct:
            return direct
        pieces = []
        for following, _ in texts[i + 1:i + 5]:
            normalized = compact_text(following)
            if OTHER_FIELD.search(normalized) or VEHICLE_LABEL.search(normalized):
                break
            if not re.fullmatch(r"[A-Z0-9-]{1,9}", normalized):
                break
            pieces.append(normalized)
        # Prefer a combined letter + digits value over an isolated number block.
        if len(pieces) >= 2 and re.fullmatch(r"[A-Z]{1,3}-?", pieces[0]):
            value = parse_vehicle_value("".join(pieces))
            if value:
                return value
        if len(pieces) == 1:
            value = parse_vehicle_value(pieces[0])
            if value:
                return value
    return ""


def vehicle_anchors(boxes: List[OCRBox]) -> List[OCRBox]:
    anchors = [b for b in boxes if VEHICLE_LABEL.search(compact_text(b.text))]
    # The printed label itself is sometimes detected as separate '车' and '号'.
    for first in boxes:
        if compact_text(first.text) != "车":
            continue
        for second in boxes:
            height = max(first.y1-first.y0, second.y1-second.y0, 1)
            if compact_text(second.text) == "号" and 0 <= second.x0-first.x1 <= height*2 and abs(second.y0-first.y0) <= height*.7:
                anchors.append(OCRBox(first.x0, min(first.y0,second.y0), second.x1, max(first.y1,second.y1), "车号", min(first.confidence,second.confidence)))
    return anchors


def vehicle_from_boxes(boxes: List[OCRBox]) -> str:
    candidates = set()
    for anchor in vehicle_anchors(boxes):
        direct = labelled_vehicle(anchor.text)
        if direct:
            candidates.add(direct)
            continue
        height = max(anchor.y1-anchor.y0, 1)
        cy = (anchor.y0+anchor.y1)/2
        nearby = [b for b in boxes if b is not anchor and b.x0 >= anchor.x1-height*.2 and
                  b.x0-anchor.x1 <= height*16 and abs((b.y0+b.y1)/2-cy) <= max(height,b.y1-b.y0)*1.3]
        nearby.sort(key=lambda b:b.x0)
        pieces = []
        for box in nearby:
            t = compact_text(box.text)
            if OTHER_FIELD.search(t):
                break
            if not re.fullmatch(r"[A-Z0-9-]{1,9}",t):
                break
            if pieces and box.x0-pieces[-1].x1 > height*2:
                break
            pieces.append(box)
        # Join adjacent OCR fragments, including separated digits and letters.
        value = parse_vehicle_value("".join(b.text for b in pieces))
        if value:
            candidates.add(value)
    # Different plausible identifiers in the same field require review, not guessing.
    return next(iter(candidates)) if len(candidates)==1 else ""


def ocr_boxes(png_bytes: bytes) -> List[OCRBox]:
    import numpy as np
    from io import BytesIO
    from PIL import Image
    arr = np.array(Image.open(BytesIO(png_bytes)).convert("RGB"))
    result = get_ocr().ocr(arr, cls=True)
    boxes = []
    if result and result[0]:
        for coords, (text, score) in result[0]:
            xs=[p[0] for p in coords]; ys=[p[1] for p in coords]
            boxes.append(OCRBox(min(xs),min(ys),max(xs),max(ys),text.strip(),float(score)))
    boxes.sort(key=lambda b:(round(b.y0/12),b.x0))
    return boxes


def recognize_single_cell(png_bytes: bytes) -> str:
    """Recognition-only retry when handwriting was missed by text detection."""
    import numpy as np
    from io import BytesIO
    from PIL import Image
    result = get_ocr().ocr(np.array(Image.open(BytesIO(png_bytes)).convert("RGB")),det=False,cls=True)
    candidates=set()
    def collect(item):
        if isinstance(item,(list,tuple)):
            if len(item)==2 and isinstance(item[0],str) and isinstance(item[1],(int,float)):
                value=parse_vehicle_value(item[0])
                if value and item[1]>=.6:candidates.add(value)
            else:
                for child in item:collect(child)
    collect(result)
    return next(iter(candidates)) if len(candidates)==1 else ""


def retry_vehicle(page: fitz.Page, initial: List[OCRBox], debug_dir: Optional[Path], page_index: int) -> Tuple[str, str]:
    import json
    from io import BytesIO
    from PIL import Image, ImageOps
    trace = []
    def remember(tag, png, boxes):
        trace.append({"pass":tag,"texts":[{"text":b.text,"confidence":b.confidence,"box":[b.x0,b.y0,b.x1,b.y1]} for b in boxes]})
        if debug_dir is not None:
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir/f"page-{page_index+1:04d}-{tag}.png").write_bytes(png)
    # A second, expanded crop can locate the printed label missed by the first pass.
    zoom = 3.0
    png = render_top_crop(page, top_ratio=0.60, zoom=zoom)
    boxes = ocr_boxes(png)
    remember("expanded",png,boxes)
    footer,footer_png=ocr_footer(page,zoom=zoom)
    remember("footer",footer_png,footer)
    boxes += footer
    value = vehicle_from_boxes(boxes)
    if value:
        return value, "车号经扩大区域复识别"
    anchors = vehicle_anchors(boxes)
    if not anchors:
        # Initial boxes were produced at zoom 2.5; scale their coordinates.
        anchors = [OCRBox(b.x0*zoom/2.5,b.y0*zoom/2.5,b.x1*zoom/2.5,b.y1*zoom/2.5,b.text,b.confidence) for b in vehicle_anchors(initial)]
    candidates = set()
    for index, anchor in enumerate(anchors[:2]):
        h=max(anchor.y1-anchor.y0,1)
        right=anchor.x1+16*h
        # Respect the next printed field boundary (e.g. mileage), even when its
        # text would sort before the vehicle value in the flattened OCR output.
        for b in boxes:
            if OTHER_FIELD.search(compact_text(b.text)) and b.x0>anchor.x1 and abs(b.y0-anchor.y0)<h*2:
                right=min(right,b.x0)
        rect=fitz.Rect((anchor.x1+h*.1)/zoom,(anchor.y0-h*.6)/zoom,right/zoom,(anchor.y1+h*1.1)/zoom) & page.rect
        if rect.is_empty or rect.width < h/zoom:
            continue
        raw=page.get_pixmap(matrix=fitz.Matrix(5,5),clip=rect,alpha=False).tobytes("png")
        for variant in ("original","contrast"):
            image=Image.open(BytesIO(raw)).convert("RGB")
            if variant=="contrast":
                image=ImageOps.autocontrast(ImageOps.grayscale(image)).convert("RGB")
            buf=BytesIO();image.save(buf,format="PNG");crop=buf.getvalue()
            local=ocr_boxes(crop)
            remember(f"cell-{index}-{variant}",crop,local)
            # Only accept one physical text row inside this bounded cell.
            value=""
            if local:
                heights=[max(b.y1-b.y0,1) for b in local]
                if max(b.y0 for b in local)-min(b.y0 for b in local) <= max(heights)*.9:
                    value=parse_vehicle_value("".join(b.text for b in sorted(local,key=lambda b:b.x0)))
                    if value:
                        candidates.add(value)
            if not value:
                value=recognize_single_cell(crop)
                trace.append({"pass":f"cell-{index}-{variant}-recognition-only","vehicle":value})
                if value:candidates.add(value)
    if debug_dir is not None:
        (debug_dir/f"page-{page_index+1:04d}-ocr.json").write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding="utf-8")
    if len(candidates)==1:
        return next(iter(candidates)), "车号经单元格放大复识别"
    return "", "车号复识别未确定" + ("（候选冲突）" if len(candidates)>1 else "")


DATE_LABEL = re.compile(r"试验时间|试验日期|测试日期|检查时间|检查日期")
PLACE_LABEL = re.compile(r"试验地点|测试地点|检查地点")
ALL_FIELD_LABELS = re.compile(r"试验车号|车辆编号|试验车编号|车号|检查车辆|检查车号|试验时间|试验日期|测试日期|检查时间|检查日期|试验地点|测试地点|检查地点|里程|燃油|油量|摩托|负载|气象|天气|温度|湿度|风力|海拔|序号|仪器|有效期|车型|产品型号")


def normalized_date_value(text: str) -> str:
    text = compact_text(text).strip(":：,，;；.。|[]()（）")
    match = re.fullmatch(r"(20\d{2})(\d{2})(\d{2})", text)
    if not match:
        match = re.fullmatch(r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})日?", text)
    return format_time_code(*match.groups()) if match else ""


def field_from_boxes(boxes, label_pattern, parse):
    values = set()
    for anchor in boxes:
        match = label_pattern.search(compact_text(anchor.text))
        if not match:
            continue
        tail = compact_text(anchor.text)[match.end():]
        tail = ALL_FIELD_LABELS.split(tail,maxsplit=1)[0]
        direct = parse(tail)
        if direct:
            values.add(direct)
            continue
        height = max(anchor.y1-anchor.y0,1)
        center = (anchor.y0+anchor.y1)/2
        nearby = [b for b in boxes if b is not anchor and b.x0>=anchor.x1-height*.2 and b.x0-anchor.x1<=height*22
                  and abs((b.y0+b.y1)/2-center)<=max(height,b.y1-b.y0)*1.1]
        nearby.sort(key=lambda b:b.x0)
        parts=[]
        for box in nearby:
            text=compact_text(box.text)
            if ALL_FIELD_LABELS.search(text):break
            if parts and box.x0-parts[-1].x1>height*2.5:break
            parts.append(box)
        value=parse("".join(b.text for b in parts))
        if value:values.add(value)
    return next(iter(values)) if len(values)==1 else ""


def parse_place_value(text):
    text=compact_text(text).strip(":：,，;；.。|[]()（）")
    # A unit or a weather measurement must never become a trial location.
    if re.search(r"℃|°|天气|温度|湿度|风力|海拔|气象条件|M/S|KM/H|%",text):return ""
    chinese=re.findall(r"[\u4e00-\u9fff]",text)
    if len(chinese)>=2 and re.fullmatch(r"[\u4e00-\u9fffA-Z0-9·.、-]{2,30}",text):return text
    # Preserve longer Latin place names, but reject isolated C, KM, H, etc.
    if re.fullmatch(r"[A-Z][A-Z .-]{3,29}",text) and text not in {"CELSIUS","TEMPERATURE","HUMIDITY"}:return text
    return ""


def retry_labelled_field(page, boxes, label_pattern, parse, debug_dir, page_index, tag):
    """Retry only the value cell to the right of the relevant printed label."""
    from io import BytesIO
    from PIL import Image, ImageOps
    candidates=set()
    anchors=[b for b in boxes if label_pattern.search(compact_text(b.text))]
    for index,anchor in enumerate(anchors[:2]):
        h=max(anchor.y1-anchor.y0,1)
        # Boxes from the primary header/footer pass use full-page coordinates at 2.5x.
        right=min(page.rect.width*2.5,anchor.x1+22*h)
        center=(anchor.y0+anchor.y1)/2
        for other in boxes:
            if other.x0>anchor.x1 and ALL_FIELD_LABELS.search(compact_text(other.text)) and abs((other.y0+other.y1)/2-center)<=h*1.3:
                right=min(right,other.x0)
        rect=fitz.Rect((anchor.x1+h*.1)/2.5,(anchor.y0-h*.5)/2.5,right/2.5,(anchor.y1+h*.9)/2.5)&page.rect
        if rect.is_empty:continue
        image=Image.open(BytesIO(page.get_pixmap(matrix=fitz.Matrix(5,5),clip=rect,alpha=False).tobytes('png')))
        for variant in ['original','contrast']:
            processed=image if variant=='original' else ImageOps.autocontrast(ImageOps.grayscale(image))
            data=BytesIO();processed.save(data,format='PNG');png=data.getvalue()
            if debug_dir is not None:
                debug_dir.mkdir(parents=True,exist_ok=True)
                (debug_dir/f'page-{page_index+1:04d}-{tag}-{index}-{variant}.png').write_bytes(png)
            local=ocr_boxes(png)
            # Ignore mixed lines and take only a single row from the bounded cell.
            if local and max(b.y0 for b in local)-min(b.y0 for b in local)<=max(max(b.y1-b.y0,1) for b in local):
                text=''.join(b.text for b in sorted(local,key=lambda b:b.x0))
                value=parse(text)
                if value:candidates.add(value)
    return next(iter(candidates)) if len(candidates)==1 else ''


def ocr_footer(page, zoom=2.5):
    # These forms put check date/place/vehicle in a row close to the bottom edge.
    r=page.rect
    rect=fitz.Rect(r.x0,r.y0+r.height*.75,r.x1,r.y1)
    png=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),clip=rect,alpha=False).tobytes("png")
    boxes=ocr_boxes(png)
    # Normalize crop coordinates back into full-page coordinates at the same zoom.
    return [OCRBox(b.x0+rect.x0*zoom,b.y0+rect.y0*zoom,b.x1+rect.x0*zoom,b.y1+rect.y0*zoom,b.text,b.confidence) for b in boxes],png


def ocr_texts(png_bytes: bytes) -> List[Tuple[str, float]]:
    return [(b.text,b.confidence) for b in ocr_boxes(png_bytes)]


def extract_fields(texts: List[Tuple[str, float]]) -> Tuple[str, str, str, str, str, str]:

    joined = " ".join(t for t, _ in texts)
    note_parts: List[str] = []

    experiment = ""
    for t, _ in texts[:8]:
        t2 = t.replace(" ", "")
        if TITLE_HINT_RE.search(t2) and "试验时间" not in t2 and "试验地点" not in t2:
            experiment = t2
            break
    if not experiment:
        for t, _ in texts[:5]:
            t2 = t.replace(" ", "")
            if len(t2) >= 6 and "条件" not in t2 and "时间" not in t2:
                experiment = t2
                break

    # ---- 时间 ----
    time_disp, time_code = "", ""
    m = TIME_RE.search(joined)
    if m:
        time_disp = display_time(m.group(1), m.group(2), m.group(3))
        time_code = format_time_code(m.group(1), m.group(2), m.group(3))
    else:
        for i, (t, _) in enumerate(texts):
            if "试验时间" in t or ("时间" in t and "摩托" not in t):
                window = " ".join(x for x, _ in texts[i : i + 4])
                m2 = TIME_RE.search(window)
                if m2:
                    time_disp = display_time(m2.group(1), m2.group(2), m2.group(3))
                    time_code = format_time_code(m2.group(1), m2.group(2), m2.group(3))
                    break

    # ---- 地点 ----
    loc_s = ""
    for i, (t, _) in enumerate(texts):
        if "试验地点" in t or t.endswith("地点"):
            after = re.split(r"试验地点|地点", t, maxsplit=1)
            if len(after) == 2 and after[1].strip():
                cand = after[1].strip(" :：.-·、")
                if cand and "气象" not in cand:
                    loc_s = cand
                    break
            for j in range(i + 1, min(i + 5, len(texts))):
                cand = texts[j][0]
                if any(
                    k in cand
                    for k in (
                        "试验",
                        "气象",
                        "天气",
                        "温度",
                        "湿度",
                        "风力",
                        "海拔",
                        "场地",
                        "车辆",
                        "时间",
                        "车号",
                    )
                ):
                    continue
                if TIME_RE.search(cand):
                    continue
                cand2 = re.sub(r"^[\s:：.\-—_/·、]+|[\s:：.\-—_/·、]+$", "", cand)
                if cand2 and not re.fullmatch(r"[\d.]+", cand2):
                    loc_s = cand2
                    break
            break
    if not loc_s:
        mloc = re.search(
            r"试验地点\s*[:：]?\s*([^\s试验气象温湿风力海拔场地车辆车号]{2,20})",
            joined,
        )
        if mloc:
            loc_s = mloc.group(1).strip(" :：.-·、")
    loc_s = re.sub(r"(气象条件|天气|温度).*$", "", loc_s).strip()

    # Read only the explicit vehicle-number label, never instrument serial numbers.
    vehicle = vehicle_from_texts(texts)

    if not experiment:
        note_parts.append("实验名称未识别")
    if not vehicle:
        note_parts.append("车号未识别")
    if not time_code:
        note_parts.append("时间未识别")
    if not loc_s:
        note_parts.append("地点未识别")

    return experiment, vehicle, time_disp, time_code, loc_s, ";".join(note_parts)


def load_confirmed_rules(path: Optional[Path] = None):
    import json
    path = path or Path(__file__).resolve().parent / "field_rules.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data,dict) or not isinstance(data.get("rules",[]),list):
        raise ValueError("field_rules.json 格式错误")
    for rule in data.get("rules",[]):
        if not isinstance(rule,dict) or not isinstance(rule.get("experiment_contains"),str) or not rule["experiment_contains"]:
            raise ValueError("纠正规则必须指定非空的 experiment_contains")
        if rule.get("confirmed_fields"):
            if not re.fullmatch(r"[a-f0-9]{64}",str(rule.get("page_fingerprint",""))):raise ValueError("已确认页面字段必须绑定有效页面指纹")
            if not isinstance(rule["confirmed_fields"],dict) or any(k not in {"vehicle","place"} or not isinstance(v,str) or not v for k,v in rule["confirmed_fields"].items()):raise ValueError("已确认页面字段格式错误")
        for key in ("vehicle_aliases","place_aliases"):
            aliases=rule.get(key,{})
            if not isinstance(aliases,dict) or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v for k,v in aliases.items()):
                raise ValueError("纠正规则的别名必须是非空文本")
    return data.get("rules",[])


def apply_confirmed_rules(experiment, vehicle, place, rules, page_fingerprint=None):
    changes=[]
    # Only a full observed error value in a matching form can trigger correction.
    # Never fuzzy-match all locations or apply one vehicle number to all forms.
    vehicle_targets=set();place_targets=set()
    for rule in rules:
        if rule.get("page_fingerprint") and rule["page_fingerprint"] != page_fingerprint:continue
        if compact_text(rule["experiment_contains"]) not in compact_text(experiment):continue
        # Exact image identity allows reuse of this page's human-confirmed fields,
        # including fields the OCR still cannot read. Never use this for another page.
        confirmed=rule.get("confirmed_fields",{}) if rule.get("page_fingerprint") else {}
        if confirmed.get("vehicle"):vehicle_targets.add(confirmed["vehicle"])
        if confirmed.get("place"):place_targets.add(confirmed["place"])
        if vehicle in rule.get("vehicle_aliases",{}):vehicle_targets.add(rule["vehicle_aliases"][vehicle])
        if place in rule.get("place_aliases",{}):place_targets.add(rule["place_aliases"][place])
    if len(vehicle_targets)==1:
        corrected=next(iter(vehicle_targets))
        if corrected!=vehicle:changes.append(f"已确认规则修正车号：{vehicle or '未识别'}→{corrected}")
        vehicle=corrected
    elif len(vehicle_targets)>1:changes.append("车号纠正规则冲突，未自动修改")
    if len(place_targets)==1:
        corrected=next(iter(place_targets))
        if corrected!=place:changes.append(f"已确认规则修正地点：{place or '未识别'}→{corrected}")
        place=corrected
    elif len(place_targets)>1:changes.append("地点纠正规则冲突，未自动修改")
    return vehicle,place,changes


def page_fingerprint(page):
    import hashlib
    pix=page.get_pixmap(matrix=fitz.Matrix(1,1),alpha=False)
    return hashlib.sha256(str((pix.width,pix.height)).encode()+pix.samples).hexdigest()


def pdf_identity(path: Path):
    import hashlib
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    with fitz.open(path) as doc:count=doc.page_count
    return {"sha256":h.hexdigest(),"pages":count}


def write_preview_identity(pdf_path: Path, out_dir: Path):
    import json
    out_dir.mkdir(parents=True,exist_ok=True)
    path=out_dir/"preview-source.json"
    path.write_text(json.dumps(pdf_identity(pdf_path),ensure_ascii=False,indent=2),encoding='utf-8')


def verify_preview_identity(pdf_path: Path, out_dir: Path):
    import json
    path=out_dir/"preview-source.json"
    if not path.is_file():
        raise ValueError("预览清单缺少原PDF校验信息。请先用新版 run_preview.bat 生成一次清单，再修改并导出。")
    expected=json.loads(path.read_text(encoding='utf-8'))
    actual=pdf_identity(pdf_path)
    if expected!=actual:
        raise ValueError("选择的PDF与当前preview.csv不对应。请拖入生成该清单时的同一份原PDF，或重新生成预览。")
    return actual['pages']


def scan_pdf(
    pdf_path: Path,
    top_ratio: float = 0.4,
    max_pages: Optional[int] = None,
    debug_dir: Optional[Path] = None,
) -> List[PageMeta]:
    doc = fitz.open(pdf_path)
    n = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
    metas: List[PageMeta] = []
    prev: Optional[PageMeta] = None
    confirmed_rules = load_confirmed_rules()

    print(f"共 {doc.page_count} 页，将处理前 {n} 页 …", flush=True)
    for i in range(n):
        page = doc[i]
        png = render_top_crop(page, top_ratio=top_ratio)
        boxes = ocr_boxes(png)
        texts = [(b.text,b.confidence) for b in boxes]
        experiment, _, time_disp, time_code, loc_s, note = extract_fields(texts)
        # Use labelled metadata from both regions. An annex may carry all of its
        # date/place/vehicle fields at the bottom instead of in the header.
        parsed_date = field_from_boxes(boxes, DATE_LABEL, normalized_date_value)
        parsed_place = field_from_boxes(boxes, PLACE_LABEL, parse_place_value)
        vehicle = vehicle_from_boxes(boxes)
        if not all([vehicle, parsed_date, parsed_place]):
            footer, footer_png = ocr_footer(page)
            boxes += footer
            if debug_dir is not None:
                debug_dir.mkdir(parents=True,exist_ok=True)
                (debug_dir/f"page-{i+1:04d}-footer.png").write_bytes(footer_png)
            parsed_date = field_from_boxes(boxes, DATE_LABEL, normalized_date_value)
            parsed_place = field_from_boxes(boxes, PLACE_LABEL, parse_place_value)
            vehicle = vehicle_from_boxes(boxes)
        # Discard flattened-text fallbacks: they can select a temperature unit
        # or an instrument expiry date from the next row.
        legacy_place=loc_s
        if not parsed_date:
            parsed_date=retry_labelled_field(page,boxes,DATE_LABEL,normalized_date_value,debug_dir,i,'date')
        if not parsed_place:
            parsed_place=retry_labelled_field(page,boxes,PLACE_LABEL,parse_place_value,debug_dir,i,'place')
        time_code=parsed_date
        time_disp=display_time(parsed_date[:4],parsed_date[4:6],parsed_date[6:8]) if parsed_date else ''
        loc_s=parsed_place
        vehicle_note = ""
        if not vehicle:
            print(f"  第{i+1}页车号未确定，正在放大复识别…",flush=True)
            vehicle, vehicle_note = retry_vehicle(page, boxes, debug_dir, i)
        vehicle_raw, location_ocr_raw = vehicle, loc_s or legacy_place
        vehicle, loc_s, corrections = apply_confirmed_rules(experiment, vehicle, loc_s, confirmed_rules, page_fingerprint(page) if any(r.get("page_fingerprint") for r in confirmed_rules) else None)
        notes = [part for part in note.split(";") if part and part not in {"车号未识别", "时间未识别", "地点未识别"}]
        if not time_code:
            notes.append("时间未识别")
        if not loc_s:
            notes.append("地点待核对：未从地点单元格读到有效地点")
        if not vehicle:
            notes.append("车号未识别")
        if vehicle_note:
            notes.append(vehicle_note)
        notes.extend(corrections)
        note = ";".join(notes)

        # Missing values remain unknown; never borrow fields from a different experiment.
        group_key = "|".join([experiment, vehicle, time_code, loc_s]) if all([experiment, vehicle, time_code, loc_s]) else f"未识别_p{i+1}"

        fname = build_filename_base(experiment, vehicle, time_code, loc_s)
        meta = PageMeta(
            page_index=i,
            experiment=experiment,
            vehicle=vehicle,
            time_raw=time_disp,
            time_code=time_code,
            location_raw=loc_s,
            group_key=group_key,
            filename_base=fname,
            note=note,
            vehicle_raw=vehicle_raw,
            location_ocr_raw=location_ocr_raw,
        )
        metas.append(meta)
        if not group_key.startswith("未识别_"):
            prev = meta
        print(
            f"  [{i+1}/{n}] {fname}  ({note})" if note else f"  [{i+1}/{n}] {fname}",
            flush=True,
        )

    doc.close()
    return metas


def refresh_filename(meta):
    base=build_filename_base(meta.experiment,meta.vehicle,meta.time_code,meta.location_raw)
    meta.filename_base=outlines.prefix_filename(base,meta.outline_no,meta.outline_active,meta.outline_example)
    return meta.filename_base


def active_outline(explicit=None):
    if not explicit:
        bank=vehicle_catalogs.VehicleBank.load(Path(__file__).resolve().parent/'outlines')
        if bank:return bank
    path=Path(explicit).expanduser().resolve() if explicit else Path(__file__).resolve().parent/'outline_catalog.csv'
    if not path.is_file():
        if explicit:raise ValueError('找不到大纲目录：'+str(path))
        return None
    return outlines.read_source(path,ocr_texts)[0]


def attach_outline(metas,catalog):
    if isinstance(catalog,vehicle_catalogs.VehicleBank):
        vehicle_catalogs.apply_bank(metas,catalog)
        for meta in metas:refresh_filename(meta)
        print('已启用分车辆大纲库：'+', '.join(catalog.catalogs)+'；逐页按完整车号/字母类别选择，禁止跨车匹配。',flush=True)
        pending=sum(not m.outline_no for m in metas)
        if pending:print(f'{pending}页需核对车号或大纲序号，未套用其他车辆的大纲。',flush=True)
        return
    outlines.add_outline(metas,catalog)
    for meta in metas:
        meta.outline_vehicle=''
        meta.outline_source=catalog.path.name if catalog else ''
        refresh_filename(meta)
    if catalog:
        print(f'已启用大纲：{catalog.path.name}，共{len(catalog.entries)}个目录条目。',flush=True)
        if catalog.example:print('注意：当前为示例大纲，输出文件名保留“示例”标记，不能作为正式编号。',flush=True)
        pending=sum(not m.outline_no for m in metas)
        if pending:print(f'{pending}页未能唯一匹配大纲；请在preview.csv核对大纲序号，未填时输出“待匹配”前缀。',flush=True)
    else:print('尚未导入大纲，沿用不带序号的命名。要增加序号请先运行import_outline.bat。',flush=True)


def write_outline_identity(out_dir,catalog):
    import json
    if isinstance(catalog,vehicle_catalogs.VehicleBank):
        data={'active':True,'mode':'vehicle','root':str(catalog.path.resolve()),'catalogs':catalog.snapshot()}
        (out_dir/'preview-outline.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        return
    data={'active':bool(catalog)}
    if catalog:
        data.update({'path':str(catalog.path.resolve()),'sha256':catalog.sha256,'example':catalog.example,
                     'numbers':sorted({e.number for e in catalog.entries})})
    (out_dir/'preview-outline.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def verify_outline_identity(out_dir,metas):
    import json,hashlib
    path=out_dir/'preview-outline.json'
    if not path.is_file():
        if any(m.outline_active for m in metas):raise ValueError('缺少大纲校验记录，请用新版重新生成预览。')
        return
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('mode')=='vehicle':
        return vehicle_catalogs.verify_bank(data,metas)
    if bool(data['active'])!=any(m.outline_active for m in metas):raise ValueError('清单的大纲模式被改变，请重新生成预览。')
    if not data['active']:return
    source=Path(data['path'])
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=data['sha256']:
        raise ValueError('预览使用的大纲已修改或丢失，请重新生成预览后核对，避免用错项目序号。')
    for meta in metas:
        if not meta.outline_active or meta.outline_example!=data['example']:raise ValueError('清单的大纲/示例标记与原预览不一致，请重新生成预览。')
        if meta.outline_no and meta.outline_no not in data['numbers']:raise ValueError('清单中的大纲序号不在当前目录中：'+meta.outline_no+'。请先在目录补充科目，再重新预览。')


def write_preview_csv(metas: List[PageMeta], csv_path: Path, version: str) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "页码(从1开始)",
                "实验名称",
                "车号",
                "试验时间",
                "时间码",
                "试验地点",
                "分组key",
                "文件名(不含版本)",
                "预计文件名",
                "备注",
                "OCR原始车号",
                "OCR原始地点",
                "大纲序号",
                "大纲匹配状态",
                "候选大纲科目",
                "大纲模式",
                "是否示例大纲",
                "大纲车辆",
                "大纲来源",
            ]
        )
        for m in metas:
            refresh_filename(m)
            w.writerow(
                [
                    m.page_index + 1,
                    m.experiment,
                    m.vehicle,
                    m.time_raw,
                    m.time_code,
                    m.location_raw,
                    m.group_key,
                    m.filename_base,
                    f"{m.filename_base}-{version}.pdf",
                    m.note,
                    m.vehicle_raw,
                    m.location_ocr_raw,
                    m.outline_no,
                    m.outline_status,
                    m.outline_candidates,
                    "启用" if m.outline_active else "未启用",
                    "是" if m.outline_example else "否",
                    m.outline_vehicle,
                    m.outline_source,
                ]
            )
    print(f"已写入预览: {csv_path}")


def group_contiguous(metas: List[PageMeta]) -> List[Tuple[PageMeta, List[int]]]:
    """相邻且 group_key 相同的页归为一组；用组内首页 meta 命名。"""
    if not metas:
        return []
    groups: List[Tuple[PageMeta, List[int]]] = []
    cur_meta = metas[0]
    cur_pages = [metas[0].page_index]
    for m in metas[1:]:
        if m.group_key == cur_meta.group_key:
            cur_pages.append(m.page_index)
            # 补全命名字段
            if not cur_meta.experiment and m.experiment:
                cur_meta.experiment = m.experiment
            if not cur_meta.vehicle and m.vehicle:
                cur_meta.vehicle = m.vehicle
            cur_meta.filename_base = build_filename_base(
                cur_meta.experiment,
                cur_meta.vehicle,
                cur_meta.time_code,
                cur_meta.location_raw,
            )
        else:
            groups.append((cur_meta, cur_pages))
            cur_meta = m
            cur_pages = [m.page_index]
    groups.append((cur_meta, cur_pages))
    return groups


def unique_filename(out_dir: Path, base: str, used: dict) -> Path:
    used[base] = used.get(base, 0) + 1
    n = used[base]
    name = f"{base}.pdf" if n == 1 else f"{base}_{n}.pdf"
    while (out_dir / name).exists():
        n += 1
        name = f"{base}_{n}.pdf"
    used[base] = n
    return out_dir / name


def split_pdf(
    pdf_path: Path,
    metas: List[PageMeta],
    out_dir: Path,
    version: str,
    merge_contiguous: bool = False,
) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = group_contiguous(metas) if merge_contiguous else [(m, [m.page_index]) for m in metas]
    src = fitz.open(pdf_path)
    used: dict = {}
    written: List[Path] = []

    for meta, pages in groups:
        refresh_filename(meta)
        base = f"{meta.filename_base}-{version}"
        dest = unique_filename(out_dir, base, used)
        new_doc = fitz.open()
        for pi in pages:
            new_doc.insert_pdf(src, from_page=pi, to_page=pi)
        new_doc.save(dest)
        new_doc.close()
        written.append(dest)
        page_human = ",".join(str(p + 1) for p in pages)
        print(f"  -> {dest.name}  (页 {page_human})")

    src.close()
    return written


def load_preview_csv(csv_path: Path) -> List[PageMeta]:
    metas: List[PageMeta] = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            experiment = row.get("实验名称", "")
            vehicle = row.get("车号", "")
            time_raw = row.get("试验时间", "")
            time_code = row.get("时间码", "")
            location = row.get("试验地点", "")
            group_key = row.get("分组key", "")
            filename_base = row.get("文件名(不含版本)", "")
            if not time_code and time_raw:
                m = TIME_RE.search(time_raw)
                if m:
                    time_code = format_time_code(m.group(1), m.group(2), m.group(3))
            if time_code:
                checked=normalized_date_value(time_code)
                if not checked:raise ValueError("预览清单日期无效："+time_code+"；请填写8位YYYYMMDD")
                time_code=checked
            if location and not parse_place_value(location):
                raise ValueError("清单中存在无效地点："+location+"。请核对试验地点，不要填写温度单位或乱码。")
            filename_base = build_filename_base(experiment, vehicle, time_code, location)
            if not group_key:
                group_key = f"{sanitize_field(time_code)}_{sanitize_field(location)}"
            outline_no=row.get("大纲序号", "").strip()
            if outline_no:outline_no=outlines.normalize_number(outline_no)
            outline_active=row.get("大纲模式", "未启用")=="启用" or bool(outline_no)
            outline_example=row.get("是否示例大纲", "否")=="是"
            filename_base=outlines.prefix_filename(filename_base,outline_no,outline_active,outline_example)
            metas.append(
                PageMeta(
                    page_index=int(row["页码(从1开始)"]) - 1,
                    experiment=experiment,
                    vehicle=vehicle,
                    time_raw=time_raw,
                    time_code=time_code,
                    location_raw=location,
                    group_key=group_key,
                    filename_base=filename_base,
                    note=row.get("备注", ""),
                    vehicle_raw=row.get("OCR原始车号", ""),
                    location_ocr_raw=row.get("OCR原始地点", ""),
                    outline_no=outline_no,
                    outline_status=row.get("大纲匹配状态", "未启用"),
                    outline_candidates=row.get("候选大纲科目", ""),
                    outline_active=outline_active,
                    outline_example=outline_example,
                    outline_vehicle=row.get("大纲车辆", ""),
                    outline_source=row.get("大纲来源", ""),
                )
            )
    return metas


def normalize_version(v: str) -> str:
    v = (v or "V011").strip().upper()
    if not v.startswith("V"):
        v = "V" + v
    if not re.fullmatch(r"V\d{1,4}", v):
        raise ValueError("Version must look like V01 or V011")
    return v


def cmd_preview(args: argparse.Namespace) -> int:
    pdf = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    version = normalize_version(args.version)
    if not pdf.exists():
        print(f"找不到输入文件: {pdf}", file=sys.stderr)
        return 1
    metas = scan_pdf(pdf, top_ratio=args.top_ratio, max_pages=args.max_pages, debug_dir=out_dir / "vehicle_debug")
    catalog=active_outline(getattr(args,'outline',None))
    attach_outline(metas,catalog)
    write_preview_csv(metas, out_dir / "preview.csv", version)
    write_preview_identity(pdf, out_dir)
    write_outline_identity(out_dir,catalog)

    groups = [(m, [m.page_index]) for m in metas]
    print(f"\n预计拆成 {len(groups)} 个实验文件（版本 {version}）：")
    for meta, pages in groups:
        print(f"  {meta.filename_base}-{version}.pdf  ← 页 {[p+1 for p in pages]}")
    print("\n本次只生成预览清单，不导出PDF。请核对车号、日期和地点，保存关闭CSV后运行 run_export.bat。")
    print("命名规则：启用大纲时为 大纲序号-实验名称-完整车号-实际试验日期(YYYYMMDD)-试验地点-版本号.pdf")
    print("命令行导出方式：")
    print(
        f"  python3 split_experiments.py split --input {pdf} --out {out_dir} --version {version}"
    )
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    pdf = Path(args.input).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    version = normalize_version(args.version)
    if not pdf.exists():
        print(f"找不到输入文件: {pdf}", file=sys.stderr)
        return 1

    preview_csv = out_dir / "preview.csv"
    if preview_csv.exists() and not args.rescan:
        count=verify_preview_identity(pdf,out_dir)
        print(f"读取已核对预览 {preview_csv}；保留表格修改，不重新OCR。")
        metas = load_preview_csv(preview_csv)
        selected_outline=Path(args.outline).expanduser() if getattr(args,'outline',None) else Path(__file__).resolve().parent/'outline_catalog.csv'
        current_bank=vehicle_catalogs.VehicleBank.load(Path(__file__).resolve().parent/'outlines') if not getattr(args,'outline',None) else None
        if current_bank:
            import json
            identity_path=out_dir/'preview-outline.json'
            if not identity_path.is_file() or json.loads(identity_path.read_text(encoding='utf-8')).get('mode')!='vehicle':
                raise ValueError('已启用分车辆大纲库，请重新预览记录，不能继续使用旧的共用大纲清单。')
        if (selected_outline.is_file() or current_bank) and not any(m.outline_active for m in metas):
            raise ValueError('已导入大纲，但当前清单尚未按大纲匹配。请先重新运行run_preview.bat，再核对导出。')
        changed=verify_outline_identity(out_dir,metas)
        if changed:
            write_preview_csv(metas,preview_csv,version)
            print('已按人工核对后的车号重新选择对应大纲，并更新清单。',flush=True)
        page_numbers=[m.page_index for m in metas]
        if not page_numbers or len(set(page_numbers))!=len(page_numbers) or any(i<0 or i>=count for i in page_numbers):
            raise ValueError("预览清单的页码重复、为空或超出原PDF范围，请检查清单。")
    else:
        metas = scan_pdf(pdf, top_ratio=args.top_ratio, max_pages=args.max_pages, debug_dir=out_dir / "vehicle_debug")
        catalog=active_outline(getattr(args,'outline',None))
        attach_outline(metas,catalog)
        write_preview_csv(metas, preview_csv, version)
        write_preview_identity(pdf,out_dir)
        write_outline_identity(out_dir,catalog)

    print(f"开始写出拆分 PDF（版本 {version}）…")
    written = split_pdf(pdf, metas, out_dir, version)
    print(f"完成，共 {len(written)} 个文件 -> {out_dir}")
    return 0


def cmd_import_outline(args):
    source=Path(args.input).expanduser().resolve()
    destination=Path(args.out).expanduser().resolve()
    binding=vehicle_catalogs.vehicle_key(args.vehicle) if getattr(args,'vehicle',None) else ''
    if binding:destination=destination/'outlines'
    destination.mkdir(parents=True,exist_ok=True)
    catalog,notes=outlines.read_source(source,ocr_texts)
    stem='vehicle_'+binding if binding else 'outline_catalog'
    review_rows=getattr(catalog,'review_rows',[])
    if review_rows:
        review_path=destination/(stem+'_extraction_review.csv')
        with review_path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['大纲序号','科目名称','来源页码','提取方式','状态','核对提示'])
            writer.writeheader();writer.writerows(review_rows)
        print('完整大纲提取核对表：'+str(review_path),flush=True)
    if not catalog.entries:raise ValueError('所有提取编号均存在冲突，未替换当前有效大纲。请核对提取核对表，整理成CSV后重新导入。')
    target=destination/(stem+'.csv')
    if target.exists():(destination/(stem+'.previous.csv')).write_bytes(target.read_bytes())
    outlines.write_catalog(catalog,target)
    report=['来源：'+source.name,'大纲车辆：'+(binding or '共用目录'),'导入条目：'+str(len(catalog.entries)),
            '当前为示例目录，输出保留示例标记。' if catalog.example else '当前为真实目录，请核对序号与科目名称。',
            *notes,'可在别名列添加记录表名称（多个名称用分号分隔）。',
            '完成后保存关闭目录，运行run_preview.bat并拖入混合车辆原始记录PDF。']
    (destination/(stem+'_import_report.txt')).write_text('\n'.join(report),encoding='utf-8-sig')
    if not binding:
        # Keep the v1.3 report filename for existing users.
        (destination.parent/'outline_import_report.txt' if destination.name=='outlines' else destination/'outline_import_report.txt').write_text('\n'.join(report),encoding='utf-8-sig')
    print('\n'.join(report),flush=True)
    print('已保存：'+str(target),flush=True)
    return 0


def cmd_make_demo(args):
    from demo_vehicle_data import generate_demo
    generate_demo(Path(args.out).expanduser().resolve())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="试验记录归档：可导入大纲，文件名=[大纲序号-]实验名称-车号-时间-地点-版本"
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--input", "-i", required=True, help="输入 PDF 路径")
        sp.add_argument("--out", "-o", default="out", help="输出目录")
        sp.add_argument("--outline", default=None, help="可选大纲文件；默认使用程序目录中的outline_catalog.csv")
        sp.add_argument(
            "--version",
            "-V",
            default="V011",
            help="文件名末尾版本号，默认 V011",
        )
        sp.add_argument(
            "--top-ratio",
            type=float,
            default=0.4,
            help="OCR 顶部裁剪高度占页面比例，默认 0.4（需含车号行）",
        )
        sp.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="仅处理前 N 页（调试用）",
        )

    sp_prev = sub.add_parser("preview", help="OCR 预览，生成 preview.csv")
    add_common(sp_prev)
    sp_prev.set_defaults(func=cmd_preview)

    sp_split = sub.add_parser("split", help="按分组写出单实验 PDF")
    add_common(sp_split)
    sp_split.add_argument(
        "--rescan",
        action="store_true",
        help="忽略已有 preview.csv，重新 OCR",
    )
    sp_split.set_defaults(func=cmd_split)
    sp_outline=sub.add_parser("import-outline",help="导入真实或示例大纲，生成可编辑的目录清单")
    sp_outline.add_argument("--input","-i",required=True,help="大纲CSV/XLSX/DOCX/PDF/TXT")
    sp_outline.add_argument("--out","-o",default=str(Path(__file__).resolve().parent),help="目录清单保存位置")
    sp_outline.add_argument("--vehicle",default=None,help="可选：A~F车辆类别或A204完整车号；不填时导入共用目录")
    sp_outline.set_defaults(func=cmd_import_outline)
    sp_demo=sub.add_parser("make-demo",help="生成A~F车完整示例大纲及混合车辆扫描记录")
    sp_demo.add_argument("--out",default=str(Path(__file__).resolve().parent/'examples'/'multi_vehicle'))
    sp_demo.set_defaults(func=cmd_make_demo)
    return p


def main() -> int:
    print(f"试验记录归档工具 v{PROGRAM_VERSION}：按字段定位识别，使用核对清单导出。",flush=True)
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
