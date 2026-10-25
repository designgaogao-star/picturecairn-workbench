# 可公开的演示材料

公开演示只用 `scripts/demo_ui_library.py` 生成的几何图像，不用真实图库、数据库副本、浏览记录或个人路径。品牌目录下的 previews 是设计样机，README／Release 应选用实际桌面截图。

## 生成

通过 `scripts/build.ps1` 构建后运行：

```powershell
node scripts/ui-qa/run.mjs --desktop <GalleryTool.exe绝对路径>
```

每轮生成临时图库、临时数据和动态端口，输出提示 `output/ui-qa/integration-<时间>/`。脚本经过实际 preload／IPC，文件夹对话框的返回值受控，不声称自动点击 Windows 原生对话框。

## 已提交的公开截图

最终候选包 `20261025-180752` 的实际 Electron 验收使用 `output/ui-qa/integration-1792923675523/` 生成的合成几何图片。它们不含真实图库内容、个人路径、真实文件名或数据库数据，已复制到本目录，随源码公开：

| 文件 | 演示内容 |
| --- | --- |
| [stillmark-workbench-light.png](stillmark-workbench-light.png) | 1440×1000 浅色图片墙、图包边界、文件名与尺寸 |
| [stillmark-viewer-dark.png](stillmark-viewer-dark.png) | 1440×1000 深色查看器、包内位置、胶片条和单色品牌标 |
| [stillmark-workbench-narrow.png](stillmark-workbench-narrow.png) | 390px 窄屏图片墙与焦点状态 |

文件摘要和来源记录在 [SHA256SUMS](SHA256SUMS)。不要把开发 QA 的模拟错误图误作普通使用状态，也不要用真实图库截图替换这些文件。
