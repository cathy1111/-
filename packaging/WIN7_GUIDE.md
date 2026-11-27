# Windows 7 SP1 64位离线便携兼容试用版 V1.6.1

本包面向 Windows 7 企业版/专业版 SP1 64位；不是32位版，不支持未安装SP1的Win7。
不需要预装Python；不需要联网识别。与Win10版使用不同OCR运行组件，不能混用runtime/soft目录。

1. 完整解压到英文短路径，例如 C:\TrialRecords-Win7，不能在ZIP内运行。
2. 首次双击“检查运行环境.bat”，成功后双击“启动软件.bat”。
3. 先导入各车真实大纲，再选择原始PDF、识别预览、核对保存关闭CSV、导出PDF。
4. 已有大纲可以将旧软件的outlines文件夹复制到本目录；不要复制旧runtime和soft覆盖本包。
5. 日常识别本地运行；不使用TCP/HTTP识别接口，不需要服务器。

## Win7系统先决条件
Python 3.8仍依赖Windows 7 SP1及系统Universal CRT等基础组件。
若提示api-ms-win-crt、ucrtbase、VCRUNTIME/MSVCP缺失，请交网信/IT检查并按单位规定安装相应离线系统组件。
本程序不会自动安装系统补丁、VC运行库、驱动，也不修改终端安全策略。不能保证未更新的纯净Win7免补丁运行。

## 测试范围
这是兼容试用包：已选择上游声明兼容Win7的OCR组件及Python3.8，随包提供构建测试报告。
构建机不是Windows7，尚未进行真实Windows7系统端到端验证。因此不能宣称已在所有Win7电脑实测可用。
请先经单位审批，在目标机运行环境检查和少量非敏感示例，核对识别准确性后再使用正式资料。

## 报错定位
程序目录logs/startup-check.txt和logs/compatibility-check.json记录启动/环境情况。
若Python无法启动，JSON可能不会生成，请保留屏幕错误及startup-check.txt。
手写车号、日期、地点、科目序号必须人工核对。示例生成的大纲带“示例”前缀，不能用于正式编号。
