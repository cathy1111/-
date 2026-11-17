# 公司电脑完全离线安装

识别过程使用本地 PaddleOCR，不需要联网或 API。以前缺 `httpx` 是离线依赖不完整，不是识别必须联网。

## A. 在已经成功运行的联网电脑上准备一次

1. 从 GitHub 的 `fix/offline-windows` 分支重新下载 ZIP。
2. 将更新文件合并到原来的 **C:\pro**，保留原 `soft/python`、`soft/vcredist`、`soft/wheels`、`soft/paddleocr_models`。
3. 双击 `soft/prepare_online.bat`。这一步需要联网，且使用 Windows 64位、Python 3.9；推荐在刚才已安装成功的电脑上运行。
4. 等待下载、构建依赖和验证完成。这可能花较长时间，临时环境与离线包也需要较多磁盘空间。
5. 只有显示 **SUCCESS** 并生成 **C:\pro\offline-package.zip** 才表示准备成功。准备失败请保留第一条错误截图。

准备程序会把包括 httpx 在内的依赖一起下载；把 fire 等源码包先构建成 wheel，避免到离线电脑上才要求下载构建工具；在全新环境里以 `--no-index --no-cache-dir` 安装验证，并初始化随包OCR模型。验证通过才生成压缩包。

## B. 在不联网的公司电脑上安装

1. 按公司的文件传输规定，把 **offline-package.zip** 用 U 盘或允许的方式复制到公司电脑。
2. 解压，确保结构是 **C:\pro\soft**、**C:\pro\split_experiments.py**；不要放在中文路径或 ZIP 里运行。
3. 双击 **C:\pro\soft\install_offline.bat**。
4. 按提示安装Python/运行库。安装依赖时只读包内 wheelhouse，禁止访问软件源。看到 **SUCCESS** 后继续。
5. 双击 **C:\pro\run_preview.bat** 或 **run_export.bat**，拖入 PDF 并按回车。

离线电脑不需要运行 `install_online.bat`，也不需要 API 密钥。公司电脑须为兼容的 Windows x64，且允许安装Python和运行库；如无安装权限，请让公司IT协助。原电脑的 `.venv` 不要复制到另一台电脑，安装器会在目标电脑创建独立环境。

## 包含和不包含什么

`offline-package.zip` 包含程序、固定版本依赖、Python安装程序、VC运行库及本地OCR模型。不会把你的输入PDF、输出记录、API密钥或临时构建环境打包。

GitHub上的源码ZIP只是准备工具和补丁，**不是已包含全部大文件的离线包**。必须先执行A步骤生成 offline-package.zip。

## 验证范围

已检查脚本语法、Windows换行与编码、文件完整性验证、离线安装参数、原有日期和导出逻辑。
当前开发环境无法执行Windows安装，也不具备完整的原始离线模型/依赖，所以尚未实际生成大容量离线包；请以联网电脑准备程序的成功验证，以及公司电脑的实际安装结果为准。
