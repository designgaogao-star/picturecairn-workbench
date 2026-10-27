# PictureCairn 品牌资产源文件

交付的 SVG 和 PNG 都由这里的脚本生成，可以重复生成。图形按网格规则计算，字标和副标题由字体转成路径；交付文件不依赖任何字体。

| 文件 | 作用 |
|---|---|
| `brandlib.py` | 网格与比例、圆角、布尔运算、字体转曲、SVG 输出 |
| `build_assets.py` | 生成 `docs/brand/picturecairn/` 下的全部 SVG，并检查组合标没有超出画布 |
| `pages.py` | 生成预览页 HTML，写到 `output/brand/pages/`（已被 `.gitignore` 忽略） |
| `render.cjs` | 用无头 Edge 把预览页渲染成 PNG，写回 `docs/brand/picturecairn/` |
| `requirements.txt` | Python 依赖 |

## 环境

- Python 3.12 及以上（`pages.py` 用到 3.12 的 f-string 写法）：`pip install -r requirements.txt`
- 字体只在重新生成时需要。放进 `source/fonts/`（不要提交），或用环境变量 `PICTURECAIRN_FONTS` 指向字体目录：

  | 保存为 | 来源（google/fonts 仓库 `ofl/` 目录，均为 SIL OFL 1.1） | 用途 |
  |---|---|---|
  | `InstrumentSans.ttf` | `ofl/instrumentsans/InstrumentSans[wdth,wght].ttf` | 定稿字标 |
  | `IBMPlexSans.ttf` | `ofl/ibmplexsans/IBMPlexSans[wdth,wght].ttf` | 探索稿 A |
  | `HankenGrotesk.ttf` | `ofl/hankengrotesk/HankenGrotesk[wght].ttf` | 探索稿 B |
  | `SourceSans3.ttf` | `ofl/sourcesans3/SourceSans3[wght].ttf` | 探索稿 C |

- 中文副标题用 Noto Sans SC 可变字体，默认读 `C:/Windows/Fonts/NotoSansSC-VF.ttf`，可用 `PICTURECAIRN_CJK` 改路径。
- PNG 渲染需要仓库根目录先 `npm install`（devDependencies 里的 `playwright-core`），以及本机的 Microsoft Edge。

## 生成

```powershell
cd docs/brand/picturecairn/source
python build_assets.py
python pages.py
node render.cjs ../../../../output/brand/pages/manifest.json
```

`build_assets.py` 最后会打印组合标的墨迹范围，确认没有超出 560 × 128 和 320 × 256 画布。

## 修改时注意

- 改比例只改 `brandlib.py` 里的 `Grid`：`MASTER` 是 64 网格母版，`SMALL16 / SMALL20 / SMALL24` 是托盘和界面用的像素对齐版，`PLATE16 / PLATE24` 是 favicon 和 24px 应用图标。小尺寸版本的直边必须落在整数上。
- 字标参数在 `RECOMMENDED_WORD`：Instrument Sans，字重 560，字距 +10/1000，i 点收成与竖笔等宽的正方形。
- 交付 SVG 保持纯路径：不加滤镜、渐变、外部字体或位图。
