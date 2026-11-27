# 构建与系统验证边界
- 目标：Windows7 SP1 x64兼容性试用，离线便携。
- Python：3.8.10（Python官方支持Win7的系列）。
- OCR：RapidOCR-json v0.2.0；上游README明确声明适用于Win7 x64及以上。
- 上游：https://github.com/hiroi-sora/RapidOCR-json
- 引擎发布包SHA256：7ad9b283d03436c6cd0296723188699299cb4e5cf9140b410c59543aa5793c40。
- PDF/图像组件：PyMuPDF1.20.2、NumPy1.21.6、Pillow9.5.0。
- 构建机：GitHub Windows Server2022。在该机器上进行独立运行环境、Tk、六车扫描识别与命名导出测试，并阻断Python和OCR子进程外联。
- 未完成：真实Win7虚拟机或实体机测试、单位网信安全审查、所有Win7补丁组合验证。
- 不宣称Win7实测通过、不宣称手写识别100%准确、不替代单位准入审批。
