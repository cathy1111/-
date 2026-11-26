"""Extract a reviewable catalog from a full PDF, preferring bookmarks/TOC."""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path
import fitz


def _ocr_lines(pairs):
    import outline_catalog as oc
    result=[];i=0
    while i<len(pairs):
        value=pairs[i][0]
        if oc.NUMBER_RE.fullmatch(value.strip().rstrip('.、')) and i+1<len(pairs):
            value+=' '+pairs[i+1][0];i+=1
        result.append(value);i+=1
    return result


def _toc_page(lines):
    if any(re.fullmatch(r'目\s*录(?:\s*[（(]续[)）])?',line.strip()) for line in lines):return True
    return sum(bool(re.search(r'[.．…⋯·_]{2,}\s*\d+\s*$',line)) for line in lines)>=2


def _parse(lines,page,kind,ocr=False):
    import outline_catalog as oc
    entries=[];i=0
    while i<len(lines):
        line=lines[i].strip()
        # PDF text extraction sometimes separates a sequence number and heading.
        if oc.NUMBER_RE.fullmatch(line.rstrip('.、')) and i+1<len(lines):
            line+=' '+lines[i+1].strip();i+=1
        # Join a wrapped TOC heading only when the next line has a TOC leader.
        if kind=='目录' and oc.LINE_RE.match(line) and not re.search(r'[.．…⋯·_]{2,}',line) and i+1<len(lines):
            following=lines[i+1].strip()
            if not oc.LINE_RE.match(following) and re.search(r'[.．…⋯·_]{2,}\s*\d+\s*$',following):
                line+=following;i+=1
        parsed=oc.entries_from_lines([line])
        for entry in parsed:
            if kind=='正文标题':
                if len(entry.name)>70 or not re.search(r'试验|测定|测量|测试|检验|性能|特性|验证|检查',entry.name):continue
                if re.search(r'应按|应在|应进行|必须|不得|如下所示|见表|见图|应满足',entry.name):continue
            entries.append(oc.OutlineEntry(entry.number,entry.name,(),False,page,kind,
                                          'OCR提取，请核对' if ocr else ('正文标题候选，请核对' if kind=='正文标题' else '请核对序号与名称')))
        i+=1
    return entries


def extract_full_pdf(path,ocr_texts=None):
    import outline_catalog as oc
    notes=[];candidates=[];pages=[];example=False
    with fitz.open(path) as doc:
        if doc.needs_pass:raise ValueError('大纲PDF已加密，请先解除密码。')
        example=doc.metadata.get('subject')=='EXAMPLE_OUTLINE'
        bookmarks=[]
        for _,title,page_no in doc.get_toc():bookmarks+=_parse([title],page_no,'书签')
        for index,page in enumerate(doc):
            text=page.get_text(sort=True)
            if '软件演示示例大纲' in re.sub(r'\s+','',text):example=True
            pages.append((index+1,text.splitlines(),len(re.sub(r'\s+','',text))<30))
        if bookmarks:
            candidates=bookmarks;mode='PDF书签';notes.append('优先使用PDF中带可见编号的书签，不重复提取正文。')
        else:
            # Text TOC pages take priority; avoid OCR over hundreds of body pages
            # when a perfectly readable contents page already exists.
            toc=[(n,lines,False) for n,lines,scanned in pages if not scanned and _toc_page(lines)]
            if not toc:
                readable=[]
                for n,lines,scanned in pages:
                    used_ocr=False
                    if scanned and ocr_texts is not None:
                        print(f'完整大纲第{n}/{len(doc)}页：本地OCR整理目录/标题…',flush=True)
                        pix=doc[n-1].get_pixmap(matrix=fitz.Matrix(2.5,2.5),alpha=False)
                        lines=_ocr_lines(ocr_texts(pix.tobytes('png')));used_ocr=True
                        notes.append(f'第{n}页使用本地OCR提取，请核对。')
                        if any('软件演示示例大纲' in re.sub(r'\s+','',line) for line in lines):example=True
                    readable.append((n,lines,used_ocr))
                toc=[p for p in readable if _toc_page(p[1])]
                if not toc:
                    mode='正文标题候选'
                    for n,lines,used_ocr in readable:candidates+=_parse(lines,n,'正文标题',used_ocr)
                    notes.append('未找到可用目录或编号书签，已整理正文中的试验标题候选，必须核对，正文中的完整上下级关系不会凭空补造。')
            if toc:
                mode='PDF目录'
                for n,lines,used_ocr in toc:candidates+=_parse(lines,n,'目录',used_ocr)
                notes.append('已识别目录页：'+','.join(str(n) for n,_,_ in toc)+'；优先使用目录，不混入正文步骤编号。')
    if not candidates:raise ValueError('完整PDF中未找到可提取的编号科目。请检查是否包含目录/标题，或将目录页另存为PDF、Excel/CSV后导入。')
    grouped=defaultdict(list)
    for e in candidates:grouped[e.number].append(e)
    entries=[];review=[];conflicts=0
    for number,items in grouped.items():
        names={oc.normalized_name(e.name) for e in items}
        conflict=len(names)>1
        if conflict:conflicts+=1
        first=items[0]
        if not conflict:
            entries.append(oc.OutlineEntry(first.number,first.name,first.aliases,example,first.source_page,first.source_kind,first.review_note))
        for e in items:
            review.append({'大纲序号':e.number,'科目名称':e.name,'来源页码':e.source_page,'提取方式':e.source_kind,
                           '状态':'同号异名，暂未纳入匹配目录' if conflict else '已提取，请核对','核对提示':e.review_note})
    if conflicts:notes.append(f'{conflicts}个编号存在同号异名冲突，已从匹配目录排除，详细候选保存在提取核对表。')
    notes.append('扫描识别及复杂多栏/跨行目录可能漏项，请按来源页码核对。')
    catalog=oc.Catalog(entries,Path(path),example)
    catalog.review_rows=review;catalog.source_mode=mode
    return catalog,notes
