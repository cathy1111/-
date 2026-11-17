# 实验记录 PDF 重命名工具

本仓库提供现有 `pro` 程序的修复补丁。**不是完整离线安装包**，不包含原来的 Python 安装包、OCR 模型和离线依赖。

## 下载修复版

- [打开修复版文件](https://github.com/cathy1111/-/tree/fix/offline-windows)
- [下载修复版 ZIP](https://github.com/cathy1111/-/archive/refs/heads/fix/offline-windows.zip)

下载后解压，把里面的文件复制到原来的 `pro` 文件夹，合并文件夹并替换同名文件。请先备份旧代码，**不要删除原有 soft 文件夹里的模型和安装包**。

## 使用

1. 双击 `soft/install_offline.bat`，完成安装，出现 **SUCCESS** 后再继续。
2. 双击 `run_preview.bat`，把一个 PDF 拖入黑色窗口，按回车，查看 `out/preview.csv`。
3. 双击 `run_export.bat`，拖入 PDF，按回车，生成单页 PDF。

输出格式：`实验名称-车号-日期-地点-V011.pdf`。日期取实际识别值；V011 是归档版本设置，不是识别结果。无法读取的字段标为未知。

必须保留原包中的 `soft/python`、`soft/vcredist`、`soft/wheels`、`soft/paddleocr_models`。运行环境为 Windows 64 位、Python 3.9，使用本地 PaddleOCR，默认 CPU，不需要 API 密钥。

## 修复范围与验证

修复安装脚本的编码与换行、解释器版本选择、安装失败误报；明确使用本地模型；识别范围扩大到页面顶部 40%；默认逐页导出，避免不同实验误合并；不覆盖已有 PDF。

已完成 Python 语法、日期/版本校验、分页导出、重名保护、批处理 ASCII/CRLF 检查。**尚未在 Windows 实测安装流程，也未验证真实手写识别准确率。**手写文字仍可能误读，重要记录请核对。
