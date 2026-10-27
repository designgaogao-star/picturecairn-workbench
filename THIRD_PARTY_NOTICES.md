# 第三方许可

本项目代码使用根目录的 MIT License。便携包的 `LICENSE.txt` 是项目许可证；原有 `LICENSE` 与 `LICENSES.chromium.html` 属于 Electron 及其内含组件，均保留。

构建时由 `scripts/collect_licenses.py` 从锁定环境复制第三方许可证到 `licenses/`，并生成 `licenses/index.json`，记录实际版本、依赖作用及相对文件位置。

- `licenses/python/`：FastAPI、Pydantic、Uvicorn、Pillow、NumPy、SciPy、watchfiles、pywin32、threadpoolctl 及对应传递依赖。NumPy、SciPy、Pillow 等发行包中的第三方声明按所安装 wheel 保留。
- `licenses/python/pyinstaller/` 等构建作用条目：PyInstaller 及其构建依赖的许可。PyInstaller 的 GPL 许可含引导程序分发例外，完整原文随包保留，不将其改称 MIT。
- `licenses/javascript/`：正式前端内含的 Preact、Signals、Signals Core 和 Lucide。
- `licenses/python-interpreter.txt`：随便携包分发的 Python 解释器许可。
- Electron 的 Chromium、Node.js 等声明以随包的 `LICENSES.chromium.html` 为准。

品牌 SVG 中的字标已转为路径；字体来源与授权见 `docs/brand/picturecairn/picturecairn-brand-guidelines.md`。包内不分发品牌生成时使用的字体文件。设计探索和演示图片不使用真实图库内容。

完整许可原文与构建清单一同分发。上面的说明用于索引各文件，具体条款以对应许可证原文为准。
