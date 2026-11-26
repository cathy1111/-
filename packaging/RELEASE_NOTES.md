# 三种Windows交付包

- **TrialRecords-Online-Setup-1.6.0.exe**：联网安装器。安装时下载并校验完整程序，安装完成后识别无需联网。
- **TrialRecords-Portable-Windows-x64.zip**：离线免安装版。自带Python运行环境、OCR模型和依赖，解压到英文目录后双击“启动软件.bat”，无需预装Python。
- **TrialRecords-Offline-Setup-1.6.0.exe**：离线安装器。包含完整运行环境，不需要联网或预装Python，安装后创建桌面图标。

适用Windows 10 1809及以上/Windows 11 x64。程序使用本地PaddleOCR CPU模式，不要求服务器或API；与大型服务器/多模态手写模型的识别能力不等价，重要信息仍需核对。

打包包含的均为程序、开源运行环境和模型，不包含用户的真实大纲、原始PDF、历史结果或本机队列。已有业务目录请按公司规定另行迁移。

构建流程会检查Windows运行环境、搬移后的独立Python、图形资源、实际六车打印扫描OCR、分车大纲匹配及离线安装器部署。模型实际运行时会在测试机中阻断打包Python的外联。该测试不代表所有手写体或真实大纲均能100%准确识别。

SHA256SUMS.txt用于校验三个包的完整性。安装器未进行商业代码签名。
