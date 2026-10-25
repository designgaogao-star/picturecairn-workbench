# 可公开的演示材料

公开演示只用 `scripts/demo_ui_library.py` 生成的几何图像，不用真实图库、数据库副本、浏览记录或个人路径。品牌目录下的 previews 是设计样机，README／Release 应选用实际桌面截图。

## 生成

通过 `scripts/build.ps1` 构建后运行：

```powershell
node scripts/ui-qa/run.mjs --desktop <GalleryTool.exe绝对路径>
```

每轮生成临时图库、临时数据和动态端口，输出提示 `output/ui-qa/integration-<时间>/`。脚本经过实际 preload／IPC，文件夹对话框的返回值受控，不声称自动点击 Windows 原生对话框。

## 当前预览包选图

本轮来源是 `output/ui-qa/integration-1792872932764/`，对应 `build-out/20261025-040954/GalleryTool/GalleryTool.exe`。桌面图片墙、查看器及 390px 窄屏均已实际查看，以下三张为主要演示图，都是 1440×1000：

| 文件 | 演示内容 |
| --- | --- |
| images-desktop.png | 原图包的图片墙、完整显示、常驻名称和尺寸 |
| viewer-desktop.png | 固定深色查看器、包内位置、有界胶片条、单色品牌标 |
| compare-all-files-desktop.png | 全部文件 SHA-256 核验，包含非图片文件及明确结论 |

如需展示品牌与主题，可补选同目录的 `brand-workbench-light.png`、`brand-workbench-dark.png` 和 `brand-sidebar-narrow.png`。不要把开发 QA 的模拟错误图误作普通使用状态，不在宣传中突出旧目录分类规则。

本机已将前三张、深浅品牌区和两张窄屏图连同 SHA-256 来源清单整理到 `output/showcase/20261025-040954/`，旧包选图保留。截图和生成输出不暂存、不提交；因此根 README 不放指向忽略目录的图片链接。公开发布时再由发布者选择随 Release 上传或在获准后存入仓库的最终图片，避免克隆后出现失效链接。
