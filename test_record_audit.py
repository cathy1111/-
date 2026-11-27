import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageDraw
from record_audit import numeric_result,ink_metrics,validate,device_notes,audit

class AuditTests(unittest.TestCase):
    def test_decimal_format_and_step_are_not_device_accuracy(self):
        field={'increment':'0.1'}
        self.assertEqual(numeric_result('12.3',.99,field)[0],'未发现格式问题')
        self.assertEqual(numeric_result('12.34',.99,field)[0],'疑似填写格式不符')
        self.assertEqual(numeric_result('12',.99,field)[0],'疑似填写格式不符')
        self.assertEqual(numeric_result('12.30',.99,field)[0],'疑似填写格式不符')
        self.assertEqual(numeric_result('12.3',.6,field)[0],'待人工复核')
        self.assertEqual(numeric_result('1 2.3',.99,field)[0],'待人工复核')
        status,detail=numeric_result('12.34',.84,field)
        self.assertEqual(status,'待人工复核');self.assertIn('小数位',detail)
        self.assertEqual(numeric_result('1.3',.99,{'increment':'.5'})[0],'疑似填写格式不符')
    def test_blank_form_lines_are_not_signatures(self):
        image=Image.new('RGB',(300,80),'white');draw=ImageDraw.Draw(image);draw.rectangle((0,0,299,79),outline='black',width=2);draw.line((0,60,299,60),fill='black',width=1)
        self.assertFalse(ink_metrics(image)['ink'])
        draw.line([(50,30),(80,20),(70,45),(110,25),(140,40),(170,20)],fill='black',width=2)
        self.assertTrue(ink_metrics(image)['ink'])
    def test_missing_device_metadata_and_finer_record_increment_are_not_passed(self):
        self.assertTrue(device_notes({'kind':'numeric','increment':'.1'}))
        self.assertIn('步长细于设备分辨力',''.join(device_notes({'kind':'numeric','increment':'.01','resolution':'.1','device_id':'M1','accuracy':'±0.5'})))
    def test_invalid_roi_and_rules_rejected(self):
        p={'schema':1,'name':'x','basis':'x','page_ratio':.7,'fields':[{'name':'x','kind':'numeric','bbox':[0,0,1,1],'increment':'0'}]}
        with self.assertRaises(ValueError):validate(p)
        p['fields'][0]['increment']='.1';p['fields'][0]['bbox']=[0,0,2,1]
        with self.assertRaises(ValueError):validate(p)
    def test_full_report_covers_empty_signatures_and_leaves_original_unchanged(self):
        from audit_demo import generate
        class FakeOCR:
            def __init__(self):self.calls=0
            def ocr(self,*a,**kw):self.calls+=1;return [[('12.3' if self.calls==1 else '12.34',.99)]]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pdf,rules=generate(root);before=pdf.read_bytes();profile=json.loads(rules.read_text(encoding='utf-8'));profile['title_contains']=''
            out,rows=audit(pdf,profile,root/'reports',FakeOCR(),emit=lambda *a,**kw:None)
            self.assertEqual(len(rows),6);self.assertEqual(rows[0]['状态'],'未发现格式问题');self.assertIn('检测到笔迹',rows[1]['状态'])
            self.assertEqual(rows[3]['状态'],'疑似填写格式不符');self.assertIn('疑似漏签',rows[4]['状态']);self.assertIn('疑似漏填',rows[5]['状态'])
            self.assertEqual(pdf.read_bytes(),before);self.assertTrue((out/'检查报告.html').is_file());self.assertEqual(len(list((out/'evidence').glob('*.png'))),6)
            self.assertTrue(json.loads((out/'检查信息.json').read_text(encoding='utf-8'))['example_rules'])
    def test_wrong_template_is_unchecked_not_a_clean_result(self):
        from audit_demo import generate
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pdf,rules=generate(root);p=json.loads(rules.read_text(encoding='utf-8'));p['page_ratio']=2
            out,rows=audit(pdf,p,root/'reports',None,emit=lambda *a,**kw:None)
            self.assertEqual([r['状态'] for r in rows],['未检查','未检查'])
if __name__=='__main__':unittest.main()
