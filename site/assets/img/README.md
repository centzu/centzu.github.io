# 立绘来源与授权

这一版把「到处同一张立绘」拆成了按场景、按心情分配的一组表情图，全部来自
**鲸鱼娘开源资产库**（<https://treapgogo.github.io/deepseek-whale-girl/>）的社区投稿。

| 文件 | 用途 | 来源 |
| --- | --- | --- |
| `whale-hero.webp` | 首页大立绘 | AATINF《鲸鱼娘二创素材扩展包》C07（issue-37-03） |
| `whale-wave.webp` | 关于页 / 默认心情 | 夜殇35《肥鱼头像》issue-46-07（原画参考 Fukuro袋子） |
| `whale-shy.webp` | 嘴硬 / emo / 怂 / 空站 | 夜殇35 issue-46-02 |
| `whale-drool.webp` | 干饭 / 页脚小贴纸 | 夜殇35 issue-46-05 |
| `whale-point.webp` | 得意 / 标签页 | 夜殇35 issue-46-06 |
| `whale-cheer.webp` | 靠谱 / 归档页 | 夜殇35 issue-46-09 |
| `whale-relax.webp` | 摸鱼 / 困 / 日记页侧边 | 夜殇35 issue-46-10 |
| `whale-shock.webp` | 404 | qwt《神秘蓝色大肥鱼表示非常震惊！》（issue-64-01） |
| `avatar-*.webp` | 顶栏、书签、署名头像 | 从对应表情裁头，底色调成 `#e6ecff` |
| `og-cover.webp` | 分享封面 1200×630 | hero + SVG 排版合成 |
| `favicon.png`、`apple-touch-icon.png` | 站点图标 | 由 `avatar-relax` 裁切导出 |
| `github-avatar.png` | GitHub 个人头像 460×460 | 由 `avatar-relax` 放大导出，供上传用 |

## 授权

- 角色形象原作：**上善无形** <https://space.bilibili.com/4456176>
- DeepSeek 元素二次设计：**ZipZipPipe** <https://space.bilibili.com/4168597>
- 表情与全身立绘：**AATINF / 夜殇35 / qwt**，整理于鲸鱼娘开源资产库
  （GitHub: <https://github.com/TreapGoGo/deepseek-whale-girl>）
- 角色原作相关素材沿用 **CC BY-NC-SA 4.0**；资产库里的社区投稿未逐张标注协议，
  本站只做个人非商业使用，并保留作者署名。原作者要求撤下时，删掉对应文件并重新构建。

## 加工方式

原图是已经去掉背景的透明 PNG。用 sharp 处理：

1. 全身图先 `trim` 掉透明留白，再按高度 960 导出；
2. 半身表情缩到 720×720（震惊脸 820×820），WebP 质量 82–86；
3. 头像从原图 `(250,260)` 起裁 650×650（部分用 `(230,250)` 裁 640×640），
   缩到 240×240，垫 `#e6ecff` 底色，方便圆形裁切；
4. `og-cover.webp` 用浅蓝渐变 + 圆点 SVG 打底，右侧合成 hero，文字用系统字体渲染；
5. favicon 64×64、apple-touch-icon 180×180 由 `avatar-relax` 导出。

角色本身没有重绘、没有加滤镜，只做了裁切、缩放和格式转换。
