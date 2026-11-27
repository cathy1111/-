"""Real local OCR + visual rules UI smoke; run with outbound firewall blocked."""
import json
from pathlib import Path
import shutil
import sys
import tkinter as tk
app=Path(sys.argv[1]).resolve()
from audit_demo import generate
from record_audit import audit
from split_experiments import get_ocr
from audit_manager import AuditManager
pdf,rules=generate(app);profile=json.loads(rules.read_text(encoding='utf-8'))
root=tk.Tk();root.withdraw();ui=AuditManager(root);ui.demo();root.update_idletasks();assert len(ui.fields)==3;root.destroy()
try:
    run,rows=audit(pdf,profile,app/'out/record_audit',get_ocr())
    print('AUDIT_DEMO_ROWS='+json.dumps(rows,ensure_ascii=False),flush=True)
    assert len(rows)==6,rows
    assert rows[0]['状态']=='未发现格式问题',rows
    assert rows[3]['状态']=='疑似填写格式不符',rows
    assert rows[1]['状态']=='检测到笔迹，待复核',rows
    assert rows[4]['状态']=='疑似漏签，待复核',rows
    assert rows[5]['状态']=='疑似漏填，待复核',rows
    assert len(list((run/'evidence').glob('*.png')))==6
    assert (run/'检查报告.html').is_file()
    print('RECORD_AUDIT_REAL_OCR_AND_GUI: PASS (NOT WIN7 OS CERTIFICATION)',flush=True)
finally:
    get_ocr().close()
if (app/'out').exists():shutil.rmtree(app/'out')
for path in (app/'audit_rules').glob('run_rules_*.json'):path.unlink()
