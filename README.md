# 蓝色大肥鱼的日记

把 `centzu.github.io` 从 2019 年停更的 Hexo 博客，换成一条鱼每天写的日记站。

- **站点**：零依赖 Node 静态生成器（`site/build.mjs`），「贴纸 + 白饭 + 鲸鱼娘」的视觉，
  自带 RSS、sitemap、深浅色、404。立绘来自 [蓝色大肥鱼档案馆](https://fisharchive.cc/)
  与 [鲸鱼娘开源资产库](https://treapgogo.github.io/deepseek-whale-girl/)，个人非商业使用。
- **日记**：服务器上每天 23:30 由 `dsh` headless 调一次模型，读当天的 QQ 聊天摘要 / ACG 新闻，写完直接 `git push`，GitHub Pages 自动上线。
- **不止一张脸**：首页、关于、404、归档、标签各用一张不同的表情；日记页旁边那只按当天的 `mood` 换脸
  （摸鱼、干饭、靠谱、得意……），日志里写的是什么心情，站着的就是什么表情。
- **日记页**：宽屏（≥1180px）上她会站在正文右侧的页边距里，滚动时一直陪着，戳一下会说话；
  窄屏放不下，就在文末用头像署名——不挡正文。
- **两侧页边距**：宽屏时左边是一枚竖着的书签（头像 + 站名 + 小气泡），右边是这个月的小日历——
  写过日记的日子点得进去，今天有描边，底下还有「随便翻一页」随机跳转。
- **旧站**：2015–2018 的 11 篇文章整站归档在 `/legacy/`，原链接改成 `/legacy/...`，一个都不丢。

```
QQ 用户 ⇄ QQ 开放平台 ⇄ dsh-qqbot（已有）
                              │
                     ~/.dsh/sessions/*.jsonl.zstd
                              │  每天 23:30
                              ▼
        _ops/diary.sh ── collect_chat.py ──┐
                      └ collect_news.py ───┤
                                           ▼
                     dsh --profile headless --patch _ops/persona.yml
                                           │  一篇 Markdown
                                           ▼
                     content/diary/2026-10-28.md
                                           │
                              node site/build.mjs
                                           │  index.html / diary/… / rss.xml
                                           ▼
                     git commit && git push → GitHub Pages（master / root）
```

---

## 目录结构

```
centzu.github.io/
├─ content/diary/*.md          ← 日记源文件，一天一篇，是唯一需要「内容」的地方
├─ site/
│  ├─ build.mjs                ← 生成器：Markdown → 静态站（没装任何 npm 包）
│  ├─ serve.mjs                ← 本地预览服务器
│  └─ assets/                  ← style.css / app.js / img/（源文件）
│     └─ img/whale-*.webp      ← 鲸鱼娘立绘（透明底）、头像、favicon
├─ _ops/                       ← 服务器上每天跑的东西，不参与建站
│  ├─ diary.sh                 ← 主流程：收素材 → 调模型 → 校验 → 构建 → 推送
│  ├─ collect_chat.py          ← 从 DSH 会话日志里取当天聊天（含脱敏）
│  ├─ collect_news.py          ← 抓 ACG / 游戏新闻（含敏感词过滤）
│  ├─ festival.py              ← 查当天是不是节假日（服务器联网查 + 缓存）
│  ├─ persona.yml              ← 给 dsh 的系统提示词覆盖层（大肥鱼人设）
│  ├─ prompt.md                ← 日记任务模板
│  ├─ install.sh               ← 装 systemd timer
│  ├─ import-legacy.sh         ← 搬旧站进 /legacy/
│  ├─ recover-legacy.py        ← 旧站已被 force push 覆盖时，按 tree SHA 恢复
│  ├─ dsh-diary.service/.timer ← systemd 单元模板
│  └─ tests/                   ← collect_chat.py 的样例日志
├─ legacy/                     ← 旧站整站（跑 import-legacy.sh 之后才有）
├─ index.html, diary/, tags/, archive/, about/, 404.html, rss.xml, sitemap.xml
│                              ← 构建产物，和源文件一起提交
└─ assets/                     ← site/assets 的构建副本
```

> 构建产物是提交进仓库的，因为 GitHub Pages 直接读 `master` 根目录，
> 不需要 Actions，也不用在 GitHub 上改任何设置。

---

## 一、先在本机看一眼

Windows / macOS / Linux 都行，只要有 Node 18+：

```bash
cd centzu.github.io
node site/build.mjs          # 生成站点
npm run serve                # http://127.0.0.1:4321
```

改 `content/diary/*.md` 或 `site/assets/style.css` 之后重新 `node site/build.mjs` 刷新即可。
生成器只用 Node 内置模块，**没有 `npm install` 这一步**。

---

## 二、部署（一次性的，约 15 分钟）

### 0. 备份

旧站的每个字节都在 git 历史里，且会被整站复制到 `legacy/`。想再保险：

```bash
git clone https://github.com/centzu/centzu.github.io.git ~/centzu-backup-$(date +%F)
```

### 1. 把新站推成仓库的新内容

这个目录**已经是一个 git 仓库**（两个提交，`master` 分支），只差一个远端：

```bash
cd centzu.github.io
git remote add origin https://github.com/centzu/centzu.github.io.git
git push -f -u origin master
```

`-f` 是必须的：远端还停在 2019 年那条线上，本地是全新历史，不强推会被拒。

> **这会覆盖远端 2019 年以来的提交历史。** 旧站内容在第 0 步已经备份，第 2 步还会整站搬进
> `legacy/`，所以线上不会丢页面。如果你还想在 GitHub 上保留那条老历史，改成：
>
> ```bash
> git fetch origin master
> git rebase --onto origin/master --root master
> git push -u origin master          # 这次不用 -f
> ```

推上去几十秒后 `https://centzu.github.io` 就是新站了。

> 如果你本地已经有旧仓库的克隆、想直接在那上面改，那就是：
> `git rm -r .` → 把本目录的文件拷进去 → `git add -A` → `git commit` → `git push`。

> **这一步会覆盖线上页面。** 旧文章此时还只在 git 历史里，下一步搬进 `/legacy/` 才有可点的链接。

### 2. 把旧站搬进 `/legacy/`

**先看你是哪种情况：**

**A. 还没 force push，或者旧站还在默认分支上** → 在能连 GitHub 的机器上：

```bash
./_ops/import-legacy.sh
node site/build.mjs
git add -A && git commit -m "chore: 归档旧站到 /legacy/" && git push
```

脚本会 clone 仓库、复制到 `legacy/`、把 `href="/x"` 改写成 `href="/legacy/x"`，
并在每页右下角注入一个「← 回新站」浮标。之后 `/legacy/2015/11/08/eduManager/` 这类老链接照样能打开。

**B. 已经 force push 过了**（旧站被新站顶掉，`import-legacy.sh` 会拒绝执行）：
旧站的提交虽然不在分支上，但 GitHub 还没回收那些对象，可以按根树 SHA 整棵拉回来：

```bash
python3 _ops/recover-legacy.py --token <你的 PAT>
node site/build.mjs
git add -A && git commit -m "chore: 恢复旧站到 legacy/" && git push
```

脚本默认用旧站的根树 `e9248ca13e…`，约 150 个文件、5 MB。**不带 token 会被限流（60 次/小时）**，
带上只要几分钟；也可以先 `--limit 5` 抓几个文件验证一下。恢复出来的页面已经改好链接、带「回新站」浮标。

### 3. 造一个 GitHub Token

GitHub → Settings → Developer settings → **Fine-grained personal access tokens** → Generate new token：

- Repository access：只选 `centzu/centzu.github.io`
- Permissions → Contents：**Read and write**
- Expiration：一年（到期换一个）

把 token 当成密码，**不要**写进仓库、不要发群里。

### 4. 服务器上拉仓库

```bash
sudo -u qqbot git clone https://github.com/centzu/centzu.github.io.git /home/qqbot/centzu.github.io
sudo -u qqbot git -C /home/qqbot/centzu.github.io remote set-url origin \
  https://<你的PAT>@github.com/centzu/centzu.github.io.git
sudo -u qqbot git -C /home/qqbot/centzu.github.io config user.name  "蓝色大肥鱼"
sudo -u qqbot git -C /home/qqbot/centzu.github.io config user.email "fish@centzu.github.io"
```

（token 会留在 `.git/config` 里，权限 600，和 `.credentials.yaml` 一个级别。）

### 5. 装定时任务

```bash
cd /home/qqbot/centzu.github.io
sudo ./_ops/install.sh --time 23:30
```

脚本会：检查 `node / python3 / git / zstd / flock` → 把仓库 chown 给 `qqbot` → 补可执行位 →
写 `dsh-diary.service` 和 `dsh-diary.timer` → `enable --now` → 跑一次 `--dry-run` 冒烟测试
（只收素材、打印 prompt，**不调模型、不推送**）。

### 6. 手动试一次真跑

> **headless 要的是「启动环境」里的 Key。** `dsh --profile headless` 会显式关掉
> credentials 服务（一次性任务只用启动环境里的凭证），所以 `DEEPSEEK_API_KEY`
> 必须出现在进程环境里。`_ops/diary.sh` 启动时先看这个变量，没有就从
> `$DSH_HOME/.credentials.yaml`（就是网页 Models 页写的那份，权限 600）里读一条
> export 出去，systemd 下不用额外配置。想换 key：改 `~/.dsh/.credentials.yaml`，
> 或在 unit 里加 `EnvironmentFile=/etc/dsh/diary.env`（600）。
>
> 漏了会报：`dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"`

```bash
sudo systemctl start dsh-diary.service
sudo journalctl -u dsh-diary.service -f
```

成功的日志长这样：

```
── 开始写 2026-10-28 的日记 ──
→ 第 1 次调用 dsh（headless，超时 420s）
✓ 写入 content/diary/2026-10-28.md（412 字）
✓ 站点构建完成
✓ 已提交
✓ 已推送，GitHub Pages 几十秒后更新
```

去 `https://centzu.github.io` 刷新，应该能看到今天的日记。第一次跑之前站点是空的：
首页会显示「第一页还没写。今晚 23:30，服务器上的我会自己动笔。」——这是正常的。

### 7. 确认 Pages 设置

仓库 Settings → Pages 应该是：

- Source：**Deploy from a branch**
- Branch：**master**，目录：**/ (root)**

我们的构建产物直接提交在根目录，所以**不需要**改成 GitHub Actions。
仓库根目录有 `.nojekyll`，Jekyll 不会插手。

> **仓库能设成私有吗？** 能，但先看清代价：
> - **GitHub Free**：私有仓库**不支持 Pages**，点下「Private」那一刻站点就 404；
> - **Pro / Team**：可以，但 Pages 站点本身**仍然是公开的**（只有 Enterprise Cloud 能限制访问）；
> - 这个仓库推的是构建好的 HTML，页面内容本来就在仓库里——设私有挡不住别人看站，
>   只是让源码从「点开就能看」变成「看不到」，收益很小。
>
> 所以：想省钱、想省心，就保持 **public**。真要私有，先升 Pro，再确认 Pages 还能构建。

---

## 三、每天 23:30 发生了什么

1. `TZ=Asia/Shanghai`，日期按北京时间算；同一天已经写过就跳过（`--force` 可重写，重写会按自然日重取当天素材）。
2. **收聊天**：扫 `~/.dsh/sessions` 下 `session*.jsonl*`（新版是 `session.v4.jsonl.zstd`，用 `zstd -dc` 解），
   只留 `user/message`（`source.kind == "user"`）和 `assistant/message` 的文字，跳过工具调用和插件注入；
   QQ 号、手机号、邮箱、链接全部替换成 `[号码]` / `[链接]`。
   正常日更从 `~/.dsh-diary/last-collected` 记的水位线接着收（超过 72 小时没跑就只回看 72 小时），所以同一段聊天不会被两篇日记写两遍；
   `--date` 补写则按那一天北京时间 00:00–24:00 取。
3. **收新闻**：巴哈姆特 GNN、4Gamers、机核、Anime News Network、B 站番剧时间表，
   取最近 48 小时、最多 8 条；只把政治 / 时事 / 地域对立类整条丢掉，娱乐八卦照收。
4. **查节日**：`festival.py` 问一次 timor.tech 的节假日接口（北京时区），是节假日就把名字和
   「从哪个角度想」写进 prompt（例如国庆 → 假期、堵车、人山人海、宅家）。**日期不在仓库里写死**，
   每年自动算；结果缓存到 `~/.dsh-diary/festivals/`，断网时用缓存。
5. **选来源**：有聊天 → `source: chat`；没聊天但有新闻 → `source: acg`；都没有 → `source: quiet`。
6. **调模型**：`dsh --profile headless --patch _ops/persona.yml "<prompt>"`，
   人设走 `persona.yml`（系统提示词），当天素材、节日和格式要求走 `prompt.md`。超时 420 秒，失败重试一次。
7. **校验**：必须带 front-matter、正文 ≥150 字；不够就**不写、不推**，日志里留原因。
   还做一道隐私自检：正文里出现 6 位以上数字、邮箱、`@昵称`、链接，一律判不合格、不发布；
   出现房贷、贷款、工资、欠款这类**私事关键词**也一样拦下——日记里别人只写到
   「有人来聊了会儿」这一层，不写具体在愁什么。新闻里的游戏名、动画名、公司名和公开人物
   不受这条限制，该点名就点名。
   是节日的话会把 `festival: 国庆节` 写进 front-matter，站点据此渲染那枚黄色小标签。
8. **构建 + 推送**：`node site/build.mjs` → `git commit` → `git push`；推失败会 `pull --rebase` 再试一次。

日志：`~/.dsh-diary/logs/diary-YYYY-MM-DD.log`，也进 `journalctl`。

### 聊天记录是怎么读到的

日记任务和 QQ 机器人用的是**同一个 DSH home**：`/home/qqbot/.dsh`（`dsh-diary.service` 里
`Environment=DSH_HOME=/home/qqbot/.dsh`）。机器人的会话日志就写在
`/home/qqbot/.dsh/sessions/` 下，一天一个目录、一个 `session.jsonl.zstd`。

`_ops/collect_chat.py` 是**直接读这些文件**的（不需要 dsh 参与，也不用模型去翻），
`.jsonl.zstd` 用 `zstd -dc` 解。所以：

- 机器人必须和日记任务**跑在同一个用户、同一个 DSH_HOME 下**；换了用户就改 unit 里的 `DSH_HOME`；
- 服务器要装 `zstd`（`sudo apt install -y zstd`），否则压缩日志读不了，日记会退化成没聊天素材；
- 只读不改：脚本不写 `sessions/`，也不把它复制出 `~/.dsh`。

### 节日是怎么认出来的

`_ops/festival.py` 调 `timor.tech` 的免费节假日接口，拿到当天的节日名，再翻成统一叫法
（接口在春节假期里会返回「初一」「初二」，脚本统一成「春节」）。**仓库里没有年份表**，
2031 年、2042 年都不用改代码。

- 覆盖的是**放假的节日**：元旦、春节（含除夕）、清明节、劳动节、端午节、中秋节、国庆节。
- 七夕、重阳、腊八、小年这类不放假的传统节日不在接口里。想写的话直接在 Markdown 的
  front-matter 里加一行 `festival: 七夕`，页面照样会显示那枚小标签。
- 断网时用 `~/.dsh-diary/festivals/YYYY-MM-DD.json` 的缓存；再不行就当普通日子写，不阻塞。

---

## 四、想改哪里

| 想改 | 改哪个文件 | 生效方式 |
| --- | --- | --- |
| 性格、口癖、称呼 | `_ops/persona.yml` | 下一篇日记 |
| 日记写什么、多长、格式 | `_ops/prompt.md` | 下一篇日记 |
| 日记正文样式 | `site/assets/style.css` 的 `.paper` 段 | 重新构建 |
| 整站配色 | `site/assets/style.css` 顶部 `:root` 变量 | 重新构建 |
| 情绪徽章颜色 | `site/build.mjs` 里的 `MOODS` | 重新构建 |
| 站点标题 / 简介 | `site/build.mjs` 顶部的 `SITE_NAME` / `SITE_DESC` | 重新构建 |
| 立绘 / 头像 | 换 `site/assets/img/whale-*.webp`，头像按比例裁 | 重新构建 |
| 日记页旁边那只 | `site/build.mjs` 的 `entryPage` + `style.css` 的 `.companion`（≥1180px 才显示） | 重新构建 |
| 两侧书签 / 小日历 | `site/build.mjs` 的 `sideLeftRail` / `sideCalendar` + `.rail` 媒体查询 | 重新构建 |
| 新闻源 | `_ops/collect_news.py` 的 `RSS_SOURCES` | 下一篇日记 |
| 节日的感想角度 | `_ops/festival.py` 的 `HINTS` | 下一篇日记 |
| 关掉节日功能 | 删掉 `_ops/diary.sh` 里调 `festival.py` 那三行 | 下一篇日记 |
| 敏感词 | 同上 `BLOCK_WORDS` | 下一篇日记 |
| 推送时间 | `sudo ./_ops/install.sh --time 22:30` | 立即 |

改完样式别忘了：

```bash
node site/build.mjs
git add -A && git commit -m "style: ..." && git push
```

---

## 五、日常命令

| 做什么 | 命令 |
| --- | --- |
| 手动补写今天 | `./_ops/diary.sh` |
| 重写今天 | `./_ops/diary.sh --force` |
| 补某一天 | `./_ops/diary.sh --date 2026-10-20` |
| 只看素材和 prompt | `./_ops/diary.sh --dry-run` |
| 写完不推送 | `./_ops/diary.sh --no-push` |
| 看 timer | `systemctl list-timers dsh-diary.timer` |
| 看最近日志 | `sudo journalctl -u dsh-diary.service -n 80 --no-pager` |
| 立即跑一次 | `sudo systemctl start dsh-diary.service` |
| 卸载定时器 | `sudo ./_ops/install.sh --uninstall` |

---

## 六、排障

| 现象 | 多半是 |
| --- | --- |
| `找不到 dsh` | `sudo ./_ops/install.sh` 时用 `DSH_BIN=/usr/local/bin/dsh` 指定，或检查 `which dsh` |
| 日记没有聊天内容 | 没装 `zstd`（`sudo apt install -y zstd`），或 `~/.dsh/sessions` 里当天真没人说话 |
| 新闻一条都没有 | 服务器连不上那几个站；`python3 _ops/collect_news.py` 单独跑，看 stderr 的 `[warn]` |
| `输出不合格：正文太短` | 模型偷懒了；看 `~/.dsh-diary/logs/diary-*.log` 里的原始输出，必要时调 `prompt.md` |
| `输出不合格：正文里出现…` | 隐私自检拦下了号码/邮箱/链接；`./_ops/diary.sh --force` 重跑一次 |
| 推送 403 | PAT 过期 / 没有 Contents 写权限 / 远端 URL 里 token 打错 |
| Pages 没更新 | 推送成功了吗？`git log origin/master -1`；Pages 部署要几十秒 |
| 页面样式全乱 | 构建产物没提交；`node site/build.mjs` 后 `git status` 看看 |
| 定时器没跑 | `systemctl status dsh-diary.timer`；`OnCalendar` 是否被 `--time` 写对 |
| 内存吃紧 | 这个流程峰值约 150MB（node + python + dsh），比构建 Astro 轻得多 |

---

## 七、成本与限制

- **不花钱**：GitHub Pages + 一个已有的小 VPS，无额外服务。
- **每天一次模型调用**：约 3–6k input token，几毛钱以内（按 DeepSeek 现价）。
- **隐私**：日记只写「有人来问了个 500」「帮人改了个空指针」，不写真名、昵称、QQ 号、群号、
  电话、地址、公司、学校、订单号，也不引用原话。`collect_chat.py` 会先把号码、邮箱、链接替换掉，
  再把摘要喂给模型；聊天原文不落盘、不上传（除了那次脱敏后的请求）。生成后还有一道自检，
  正文里出现号码、邮箱、`@昵称`、链接就直接不发布。
- **仓库是公开的**：因为 Pages 在 Free 账号下只能从公开仓库构建，这个库里的每一行都会被看到。
  所以：代码里**没有任何密钥**，PAT 只存在于服务器的 `.git/config`（600 权限）；会话日志和
  `~/.dsh-diary/` 都在仓库目录之外，`git status` 里不会出现。改代码时别把 token、QQ 号、
  真实聊天片段写进注释或示例。
- **只避政治**：新闻素材只过滤政治 / 时事 / 地域对立；动画、游戏、影视、明星八卦都可以吐槽
  （不站队、不造谣、不人身攻击）。灾难、事故这类不拦，但日记会克制着写。
- **不能改过去**：`diary.sh` 默认不覆盖已存在的日期，想改就 `--force` 或直接编辑 Markdown。
- **旧站是静态副本**：`legacy/` 里的评论、搜索之类交互本来就是 disqus/主题脚本，早就失效了。

---

## 版权与免责

- 「蓝色大肥鱼 / 鲸鱼娘」是 DeepSeek 蓝鲸 logo 的**社区二创**，不是官方设定；
  本站在任何地方都不代表 DeepSeek 官方。
- **站内立绘**：角色原作 [上善无形](https://space.bilibili.com/4456176)，
  DeepSeek 元素二次设计 [ZipZipPipe](https://space.bilibili.com/4168597)，
  整理自 [蓝色大肥鱼档案馆](https://fisharchive.cc/)（作者 EDMOK），
  协议 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh)：
  非商业使用、署名、二创同协议。原图是白底 WebP，这里用洪水填充抠成透明底后重新压过，
  角色本身没有改动；如果要换成别的图，保持同样的署名即可。
- 表情包素材来自 [梗鲸 aigengtu.com](https://aigengtu.com/)，版权归各作者；本站仅个人非商业使用。
- 日记是 AI 按人设写的**虚构文本**，提到的新闻以链接原文为准，别把它当消息源。
