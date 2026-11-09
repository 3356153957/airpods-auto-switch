# AirPods 自动接管 · Windows

电脑开始播放时，将已配对的 AirPods 连接到 Windows，并切换默认播放输出。需要时开启，用完可从托盘暂停。

[下载 Windows 版](https://github.com/3356153957/airpods-auto-switch/releases/latest) · [使用与更新说明](README.zh-CN.md) · [第三方声明](THIRD-PARTY-NOTICES.md)

## 快速开始

1. 在 Windows 蓝牙设置中配对 AirPods。
2. 从 Releases 下载 `AirPodsSwitch-v版本号-windows-x64.zip`，完整解压。
3. 运行 `AirPodsSwitch/AirPodsSwitch.exe`，选择耳机并保存设置。
4. 打开“电脑播放时自动接管”。电脑持续播放达到确认时间后，程序尝试连接耳机。

整个 `AirPodsSwitch` 文件夹必须一起保留，其中 `_internal` 是运行所需文件。无需安装 Python。面向 Windows 10/11 x64；不同蓝牙芯片、驱动及 AirPods 固件的接管效果可能不同。

## 功能

- 自动接管开关、手动连接、断开并暂停，均可从浅色控制面板或托盘操作。
- 播放确认时间可选 0.5、1、2、3 秒，过滤短促声音；支持忽略指定应用。
- Windows 右下角连接进度和结果通知，可关闭并测试。
- 原生标题栏、可滚动设置、固定底部操作、可折叠高级设置。
- 收起约 6 秒后转入轻量后台，重新打开时恢复窗口和未保存输入。
- “版本与更新”手动查询 GitHub 最新正式版，发现新版后打开下载页面。

这是一款面向 Windows 的单向接管工具。暂停播放不会主动断开耳机；自动切回 iPhone/iPad 的苹果生态功能不在本项目范围内。耳机离开电脑后，当前连续播放期间会让出连接，静音至少 1 秒后的新播放才会再次接管。

## 更新

主界面下方“版本与更新” → “检测更新”。发现新版后点击“下载新版本”，在 GitHub Releases 下载压缩包。先从托盘退出程序，再将新版本解压到一个完整文件夹运行。设置保存在 `%LOCALAPPDATA%\AirPodsSwitchLocal`，更换程序文件夹不会删除设置。

程序仅在点击检查时访问 GitHub 公共 Releases API，不上传耳机名称、蓝牙地址、应用列表或日志，不自动下载或安装更新。

## 源码运行与打包

在 Windows 上使用 Python 3.12 x64：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1 -Package
```

产物位于 `dist/`。`build.ps1` 支持 `-Python` 和 `-OutputDirectory`。打包会核对随附蓝牙工具的 SHA-256，并附带第三方许可证。发布新版本时同步修改 `app_version.py`，推送对应 `v主.次.修订` 标签并创建包含 Windows 压缩包的正式 Release；客户端不提示预览版。

开发调试可设置 `AIRPODS_SWITCH_DATA_DIR` 使用独立数据目录；`--background` 只启动托盘，`--ui-preview` 只预览界面，不接管耳机。

## 来源

本仓库派生自 [DvivekD/airpods-auto-switch](https://github.com/DvivekD/airpods-auto-switch)，基于提交 `77535fdcfad3f2ea6b07fee2bf2989b145878622` 改造。保留上游 Git 历史，重写接管策略、界面、通知和后台生命周期，移除未使用的云端交接与全局媒体按键代码。原项目未附带根许可证，本仓库不将上游代码重新声明为 MIT；具体组件声明见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
