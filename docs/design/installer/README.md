# PictureCairn 安装体验样机

打开 `picturecairn-installer.html` 可以查看 Windows 安装器的视觉和交互结构样机。样机默认停在“安装位置”，可以通过“上一步”进入欢迎页，再按“开始设置”“开始安装”走到动态进度和完成；安装页还提供原型专用的“查看失败样式”，可进入失败重试路径。安装位置既可以直接编辑，也可以用“浏览…”替换示例路径；用户选择的路径会贯穿进度、失败返回和完成页。取消安装会回到位置页，许可会打开独立说明页，关闭按钮会给出取消／完成语义。

本样机用于锁定安装体验，不是可执行安装程序。它保留了四个关键语义：程序位置与图库数据分开、兼容已有 `GalleryTool` 数据目录、安装前说明不会移动原图、安装后直接打开 PictureCairn。进度条只模拟状态变化，不代表实际写入速度或文件校验结果。

2026-10-27 已用本机 Edge 无头实际点击验证完整状态链，并在 390×844 下检查无横向溢出；验证截图位于 `output/ui-qa/installer-prototype-complete.png` 和 `output/ui-qa/installer-prototype-narrow.png`。路径按钮在样机中只替换示例路径，不调用真实文件选择器。

未来接入 NSIS 或 WiX 时，必须继续支持：

- 便携包现有的 `GalleryTool.exe`、`GalleryTool.local.json` 和 `GALLERY_DATA` 兼容名。
- 首次安装不覆盖已有数据；升级前提示备份，失败时保留原安装目录。
- 卸载只移除程序文件，默认保留 `%LOCALAPPDATA%\GalleryTool` 和用户图库原图。
- 安装、校验、启动和失败重试均有明确状态，不用无解释的长时间 spinner。
