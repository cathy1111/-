import unittest
import outline_catalog as oc
from full_outline_pdf import _parse,_toc_page

class PDFNumberCompatibilityTests(unittest.TestCase):
    def test_spaced_hierarchical_numbers_are_not_parent_numbers(self):
        rows=[' 1  . 1 外部尺寸与几何特性参数测定    .   .   .   .   .   .   3',
              ' 1  . 2 装备质量质心测定    .   .   .   .   .   .   4',
              ' 1  . 3 加速性能试验    .   .   .   .   .   .   5',
              ' 3 . 2 . 1 制动性能试验 ...... 12']
        entries=oc.entries_from_lines(rows)
        self.assertEqual([e.number for e in entries],['1.1','1.2','1.3','3.2.1'])
        self.assertEqual([e.name for e in entries],['外部尺寸与几何特性参数测定','装备质量质心测定','加速性能试验','制动性能试验'])
        self.assertEqual(oc.normalize_number('A . 1 . 2'),'A.1.2')
        self.assertEqual(oc.normalize_number('3 . 10'),'3.10')
    def test_malformed_numbers_do_not_fall_back_to_a_parent(self):
        for line in ['1..2 加速性能试验','1 . . 2 加速性能试验','一旦操作中断不能成为大纲编号','3 . 2 . 1']:
            self.assertIsNone(oc.split_numbered_line(line))
        self.assertEqual(oc.number_token('3 . 2 . 1'),'3.2.1')
        self.assertEqual(oc.split_numbered_line('一、 加速性能试验'),('一','加速性能试验'))
    def test_spaced_leaders_and_split_number_lines(self):
        lines=['1 . 1 加速性能试验 . . . . 3','1 . 2 制动性能试验 . . . . 4']
        self.assertTrue(_toc_page(lines))
        self.assertEqual(oc.clean_title('加速性能试验⋯⋯1 2'),'加速性能试验')
        parsed=_parse(['3 . 2 . 1','加速性能试验 . . . . 12'],2,'目录')
        self.assertEqual([(e.number,e.name) for e in parsed],[('3.2.1','加速性能试验')])

if __name__=='__main__':unittest.main()
