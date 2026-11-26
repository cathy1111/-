# 实验记录 PDF 重命名工具

## 软件 v1.2.0：本次下载的是修改后的程序

已安装用户请备份并替换 `split_experiments.py`、`run_export.bat`、`field_rules.json`，不要重装或删除模型。先运行预览核对，再运行导出。[更新步骤及验证范围](SOFTWARE_UPDATE.md)。

新版拒绝把温度单位当地点，按标签位置读日期/地点，支持局部重试；已核对页面的A204/河北官厅修正仅在完整页面指纹一致时生效，不会固定套用到其他同名表格。通用手写识别仍可能需要核对。

## 最新更新：已确认误识别校正与核对后导出

已安装用户只需更新 `split_experiments.py`、`run_export.bat` 和新增的 `field_rules.json`，无需重装依赖。先运行预览，再核对CSV，最后用同一份原PDF导出；新版导出不会重新OCR覆盖表格修改。

本次用户确认的“A车”表名范围内，完整误识别值 `204`、`河眺宽万` 可按规则校正为 `A204`、`河北官厅`。原始OCR值和修正备注保留在清单中。这是已确认业务规则校正，不代表模型已正确识别所有手写文字。[详细更新和使用说明](REVIEW_EXPORT.md)。

本仓库提供现有 `pro` 程序的修复补丁。**不是完整离线安装包**，不包含原来的 Python 安装包、OCR 模型和离线依赖。

## 新增：公司电脑完全离线安装

**先在联网电脑准备一次，公司电脑无需联网。**

1. 下载此修复分支的 ZIP，将文件合并到已运行成功的 `C:\pro`，保留原模型和安装包。
2. 在联网 Windows 电脑上运行 `soft/prepare_online.bat`，等待检查成功并生成 `offline-package.zip`。
3. 将该 ZIP 复制到公司电脑，解压成 `C:\pro`，运行 `soft/install_offline.bat`。
4. 安装成功后运行 `run_preview.bat` 或 `run_export.bat`。

[完整离线操作说明](OFFLINE_GUIDE.md)。GitHub 源码 ZIP 本身不含模型、Python 安装包和完整依赖，不能直接当作完整离线包。准备程序会在干净环境中验证禁止软件源访问的安装及本地模型初始化，成功后才打包。这里尚未实际生成大容量离线包，需在你的联网 Windows 电脑上运行验证。

## 下载修复版

- [打开修复版文件](https://github.com/cathy1111/-/tree/fix/offline-windows)
- [下载修复版 ZIP](https://github.com/cathy1111/-/archive/refs/heads/fix/offline-windows.zip)

下载后解压，把里面的文件复制到原来的 `pro` 文件夹，合并文件夹并替换同名文件。请先备份旧代码，**不要删除原有 soft 文件夹里的模型和安装包**。

## 使用

1. 完整离线包请运行 `soft/install_offline.bat`；尚未准备离线包的联网电脑可使用 `soft/install_online.bat`。出现 **SUCCESS** 后再继续。
2. 双击 `run_preview.bat`，把一个 PDF 拖入黑色窗口，按回车，查看 `out/preview.csv`。
3. 双击 `run_export.bat`，拖入 PDF，按回车，生成单页 PDF。

输出格式：`实验名称-车号-日期-地点-V011.pdf`。日期取实际识别值；V011 是归档版本设置，不是识别结果。无法读取的字段标为未知。

必须保留原包中的 `soft/python`、`soft/vcredist`、`soft/wheels`、`soft/paddleocr_models`。运行环境为 Windows 64 位、Python 3.9，使用本地 PaddleOCR，默认 CPU，不需要 API 密钥。

## 修复范围与验证

修复安装脚本的编码与换行、解释器版本选择、安装失败误报；明确使用本地模型；识别范围扩大到页面顶部 40%；默认逐页导出，避免不同实验误合并；不覆盖已有 PDF。

已完成 Python 语法、日期/版本校验、分页导出、重名保护、批处理 ASCII/CRLF 检查。**尚未在 Windows 实测安装流程，也未验证真实手写识别准确率。**手写文字仍可能误读，重要记录请核对。

## 离线包缺少 httpx 等依赖时

如果出现 `No matching distribution found for httpx`，说明本地 wheels 不完整。联网后运行 `soft/install_online.bat`，它使用本地 wheel，并从 PyPI 补全缺少的依赖。此入口不是完全离线安装；不会下载或更改你的 PDF。安装成功后再运行 `run_preview.bat`。

## 车号显示未知时的增强版

已改进车号标签定位、拆分文字框合并及局部放大复识别。[更新方法](VEHICLE_UPDATE.md)：已装好的电脑只替换 `split_experiments.py`，无需重装依赖。未知页面的局部图片和OCR日志保存在 `out/vehicle_debug`。规则和模拟OCR回归测试已通过；实际失败页面仍需样本验证。
