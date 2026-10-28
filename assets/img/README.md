# 立绘来源与授权

站内用到的三张图都由 **蓝色大肥鱼档案馆**（<https://fisharchive.cc/>）的公开立绘加工而来。

| 文件 | 用途 | 来源 |
| --- | --- | --- |
| `whale-chibi.webp` | 首页 / 404 / 页脚 | `character-art/v1/…/deepseek-chibi.webp` |
| `whale-full.webp` | 「关于」页 | `character-art/v1/…/deepseek-full.webp` |
| `whale-companion.webp` | 日记页旁边那只（镜像） | `whale-full.webp` 水平翻转 |
| `whale-avatar.webp`、`favicon.png`、`apple-touch-icon.png` | 顶栏头像、站点图标 | 由 `whale-chibi.webp` 按比例裁头 |

## 授权

- 角色形象原作：**上善无形** <https://space.bilibili.com/4456176>
- DeepSeek 元素二次设计：**ZipZipPipe** <https://space.bilibili.com/4168597>
- 整理与发布：蓝色大肥鱼档案馆（**EDMOK**）<https://fisharchive.cc/>
- 协议：**CC BY-NC-SA 4.0** <https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh>
  —— 署名、非商业、二创同协议。

本站是个人非商业站点，页脚和「关于」页都保留了署名和协议链接。
如果你要换图，保持同样的署名即可；如果原作者要求撤下，删掉对应文件并重新构建。

## 加工方式

原图是白底 WebP（没有 alpha）。处理步骤：

1. 用四角洪水填充（容差 18，只吃「三通道都很亮且接近」的像素）把与画布边缘连通的白色置为透明，
   角色内部的白色（围裙、袜子）因为不连通，不会被误伤；
2. 宽度压到 720 / 760，重新编码为 WebP（质量 88）；
3. 头像从 Q 版按比例裁 `24%–76%` 宽、`6%–58%` 高的区域，再缩到 240px。

角色本身没有做任何改动，没有重绘、没有加滤镜。
