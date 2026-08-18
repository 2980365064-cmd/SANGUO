# 三国人物立绘生成规范

## 风格母版

最新确认方向：后续人物立绘主风格切换为 **暗黑水墨战场风**。画面应像高品质三国武将宣传图：黑灰赭石为主，强墨色、强动势、战场烟尘、飞白和笔触冲击力明显；但人物脸、手、甲胄、服饰主轮廓必须清晰，不能糊成噪点或脏块。

旧版“干净水墨淡彩/工笔国风”仍可作为游戏内静态立绘的可回退方向，但新批量人物与宣传图优先按暗黑水墨战场风执行。

- 前端图：`web/public/portraits/sanguo/sanguo/core_001.webp`
- 源图：`web/public/portraits/sanguo/_source_png/sanguo/core_001.png`
- 参考样本：`web/public/portraits/sanguo/_style_trials/liu_bei_new_from_main_reference.webp`
- 低噪确认样本：`web/public/portraits/sanguo/_style_trials/core_004_zhaoyun_low_noise_long_spear.webp`
- 新暗黑水墨战场风确认样本：`web/public/portraits/sanguo/_style_trials/core_004_zhaoyun_dark_ink_battle_style_16x9.png`
- 营销横版确认样本：`web/public/portraits/sanguo/marketing/core_004_zhaoyun_16x9_final.webp`
- 营销竖版确认样本：`web/public/portraits/sanguo/marketing/core_004_zhaoyun_douyin_9x16_final.webp`

这版不是从主界面直接裁切，而是以主界面刘备气质为参考重新生成。后续人物也应采用同样方法：使用项目内已有风格图作为参考，但输出必须是新图。

重要更新：后续原始生图优先生成 **16:9 横图**，人物全身完整居中，四周保留足够画幅空间；前端竖版、头像、卡面、详情页用图都从 16:9 源图按需要二次裁剪。

宣传素材另行生成 **9:16 竖版原生构图**，不能直接硬裁 16:9 横图。竖版要让人物在手机画幅内完整站住，脸部位于上半屏安全区，侧边预留姓名题字空间，武器、披风、长袍不能被平台 UI 或画幅边缘切断。

## 运行时素材同步（强制）

`web/public/` 是素材源目录；本地 8010 由 `web/dist/` 提供静态文件。任何人物、背景、UI 图、图标或音视频素材的新增与替换，都必须按以下顺序完成，不能只改源文件：

1. 将确认素材写入正确的 `web/public/` 资源位，并核对运行时引用路径；人物通用立绘例如赵云为 `web/public/portraits/sanguo/sanguo/core_004.webp`。
2. 从 `web/` 执行 `npm run build`，同步生成 `web/dist/`。
3. 对 8010 的实际资源 URL 做请求校验，确认 HTTP 200 且返回文件哈希与 `web/public/` 源文件一致；必要时再刷新浏览器进行视觉确认。

未完成构建和 8010 实际响应校验时，不得宣称素材已在游戏内替换完成。营销目录、候选图和 `web/public/` 的修改本身都不代表 8010 已更新。

## 单独密谈展示适配（强制）

“单独密谈”左侧是无边界的宣纸显影区，不是固定比例的图片框。正式游戏仍优先使用 16:9 源图；若人物、坐骑、兵器或全身在该显影区中显得偏左、偏右或展示不完整，应在 `web/src/pages/SecretChat.tsx` 的人物位置映射中，为该人物增加经过截图确认的平移类（例如 `portrait-offset-right`），优先调整画面位置。

- 保持现有墨晕遮罩、`multiply` 融纸效果和无方框结构；不得为了“完整”改成可见矩形、硬裁切卡片或不透明底图。
- 每次新增或替换人物素材都要在 8010 的“单独密谈”中实际选中该人物核验；只有画面确实不完整或重心失衡时才添加该人物专属位置调整，避免对全部人物做统一偏移。
- 张飞当前横版源图在密谈纵向显影区中无法清楚露出脸部：`core_003.webp` 继续作为 16:9 游戏正式源图，密谈专用 `SECRET_CHAT_PORTRAIT_IDS` 改用已确认的 `core_003_vertical.webp`；以 `portrait-offset-vertical-hero` 放大并右移、上移，使脸和上半身落入墨晕核心。不得继续用横版微调掩盖脸部不可读的问题。
- 关羽同样在密谈中使用 `core_002_vertical.webp`，与张飞共用 `portrait-offset-vertical-hero` 的竖向显影参数；`core_002.webp` 保持 16:9 游戏正式源图，不受影响。
- 诸葛亮同样：`core_005.webp` 是 16:9 游戏正式源图；密谈左侧使用确认后的 `core_005_vertical.webp`，并复用 `portrait-offset-vertical-hero`，优先保证脸、羽扇与上半身可读。
- 需要原生竖版展示的场景才使用对应 `*_vertical.webp`；不要以竖版素材替换 16:9 游戏源图。
- 若替换的是已存在的 `portrait_id`，同步更新 `web/src/pages/SecretChat.tsx` 中的 `PORTRAIT_REVISIONS` 对应版本；这样游戏刷新后会请求新 URL，避免同路径旧图被浏览器缓存。仍须完成构建和 8010 实际响应校验。

## 生成流程

1. 先查《三国演义》原文或可靠转录文本，提取人物外貌、性格、身份、关键命运节点。
2. 把人物设定分成四类：
   - 外貌锚点：身形、脸型、须发、眼神、标志性特征。
   - 气质锚点：仁义、威严、刚烈、阴鸷、清雅、忠直等。
   - 服饰锚点：君主、文臣、武将、谋士、宗室、使者等身份差异。
   - 名场面锚点：优先选择《三国演义》中最能代表人物的动作、场景、命运瞬间。
3. 再按当前确认的暗黑水墨战场风生成 16:9 横图源图。
4. 每个核心人物至少出 2-3 张候选，人工挑不丑、气质对、风格统一的一张入库。
5. 后续按 UI 需要裁剪成竖版立绘、头像、卡面，不直接让模型生成不同构图的小图。
6. 抖音/短视频宣传图单独生成 9:16 原生构图，营销图可以让 AI 直接生成原生毛笔草书/行草姓名题字，但必须人工验字；游戏正式立绘源图仍保持无字。

## 画风要求

- 2D 中国暗黑水墨历史概念插画，不要 3D、CG、照片写实、塑料皮肤、动漫脸或现代游戏 UI 海报感。
- 主色为黑、灰、赭石、暗青灰；允许强墨块、飞白、战场烟尘、风暴式笔触和高反差边缘光。
- 人物主体必须是画面最清晰区域：五官清楚、眼神明确、手部可信、甲胄和衣纹连续、武器完整。
- 宣纸纹理、墨点、飞溅和烟尘主要留在背景与画面边缘；人物脸、手、武器、衣袍主轮廓必须低噪点、高清晰。
- 背景应有名场面与战场氛围，但复杂度和对比度必须低于人物，不能抢主体。
- 长兵器必须结构完整、透视自然；枪、矛、偃月刀等不能缩短、断裂、错位或重复，必要时应从人物身后延伸以体现真实长度。
- 长枪类武器必须先锁定几何关系再生图：只能有一个锋刃；枪尾必须是钝头木杆；枪杆必须是一条连续直线，并穿过或贴近握手点；不得同时在两端出现枪头、红缨或金属刃。
- 对竖版手机图，长枪不要横跨过大画幅。优先采用稳定姿势：枪头在左下方，枪尾在右上方，赵云手握中下段，枪杆斜向穿过身体前侧或身体旁侧；右上只能是钝尾，不得画成第二个枪头。
- 人物要有好看的古典脸型，不能丑、不能怪、不能表情僵硬。
- 原始生图必须是 16:9 横图；人物全身完整，头冠到靴履完整入画，不能裁脚、裁袖、裁头。
- 人物应位于画面中央或略偏黄金分割位置，四周留出可裁剪空间。
- 名场面必须“烘托人物”，不能喧宾夺主；动作、道具、环境都要让人物更准确，而不是变成战场风景画。
- 不要可读文字、题字、印章、水印、签名。

## 字体与宣传图

- 角色姓名放在画面右侧，营销图优先让 AI 原生画入毛笔草书/行草题字，使其成为画面的一部分，而不是后期贴字。
- 原生题字必须人工检查，确保只出现角色姓名、没有错字、乱码、多字、印章、水印或现代标题感。
- 若需要批量稳定产出或二次修正，可使用后期文字图层兜底；当前本机可用 `Xingkai SC` / `行楷-简`。
- 横版 16:9 可在右侧留 15%-25% 空白给姓名；竖版 9:16 可在右上或右侧中段留题字区。
- 题字颜色以深墨色为主，可加极轻的浅色墨晕或纸色衬底，不能像 UI 标签或现代标题。
- 游戏内正式立绘源图不带姓名；营销导出图可以带原生姓名题字。
- 画质优先保留 PNG 源图；WebP 仅作为前端或宣传压缩导出版。核心源图和营销母版不要过度压缩。

## 刘备样本风格要点

- 气质：仁义、温厚、寡言、喜怒不形于色，有晚年悲情但不软弱。
- 名场面：白帝城托孤 / 夷陵败后。画面用江雾、残阳、孤舟、败旗、远城暗示，不直接画多人托孤，避免抢主角。
- 服饰：宽袍为主，轻甲或佩剑为辅，不做重甲猛将。
- 表情：温和、克制、悲悯、有承担感，不凶、不丑、不油腻。

## 蜀汉核心人物名场面锚点

- 刘备：白帝城托孤 / 夷陵败后。动作克制，可静立、按剑、回望江雾；环境为残阳、江水、远城、孤舟、残旗。
- 关羽：千里走单骑 / 华容道义释曹操 / 麦城之悲。优先用青龙偃月刀、月夜江风、孤城、远舟；动作沉稳持刀，不做夸张挥砍。
- 张飞：长坂桥一声喝退曹军。动作可立于断桥或桥头，丈八蛇矛自然立起，身后风暴、残旗、敌影远处压低，人物必须最大。
- 赵云：长坂坡单骑救主。动作应清俊稳健，长枪采用“枪头左下、枪尾右上”的稳定构图：左下是唯一枪刃和红缨，枪杆穿过握手点向右上延伸，右上为钝尾木杆；远处追兵只做墨影，不能抢主体。
- 诸葛亮：隆中对 / 草船借箭 / 北伐前的远望。动作以羽扇、远眺、山雾为主；背景可有草庐或远处军阵淡影，不能魔法化。

## Prompt 模板

```text
Use case: historical-scene
Asset type: SANGUO Three Kingdoms game character key art, 16:9 horizontal source image.

Create a new full-body 2D dark heroic Chinese ink-and-wash historical illustration of {人物名}
for a Three Kingdoms strategy game.

Use the confirmed dark Zhao Yun battlefield sample as the style anchor:
dark heroic Chinese ink-and-wash battlefield concept art,
black-gray-sepia palette, strong ink masses, expressive brush strokes,
controlled ink splatter, xuan-paper tone, cinematic rim light,
high-detail 2D painterly key art, dramatic but readable.

Character source from Romance of the Three Kingdoms:
{三国演义原文依据或概括}

Character design:
{外貌锚点}
{气质锚点}
{服饰锚点}

Environment:
{三国演义名场面锚点，作为背景和动作依据；场景只烘托人物，不能喧宾夺主}

Composition:
16:9 horizontal source image. Full body, crown to boots visible,
main character large and readable, centered or slightly off-center,
generous margins for later cropping into portrait, avatar, card art, or vertical poster.
Background is secondary and lower contrast than the character.

If weapon is present:
{武器几何约束：只保留一件主武器；结构连续；不得重复、断裂、错位或遮挡脸和关键动作}

Avoid:
ugly face, distorted anatomy, generic warrior, 3D render, CGI, photorealism,
glossy plastic armor, anime, modern fantasy armor, readable text, watermark,
heavy random grain on the face, noisy face, muddy facial details,
broken dry-brush artifacts on the character, speckled skin,
fragmented weapon, duplicated weapon, extra limbs, distorted hands,
background stealing attention from the character.
```

## 9:16 宣传图 Prompt 模板

```text
Use case: historical-scene
Asset type: SANGUO Douyin/TikTok native 9:16 vertical promotional character poster.

Create a native 9:16 vertical full-body 2D dark heroic Chinese ink-and-wash illustration of {人物名}.

Use the confirmed dark Zhao Yun battlefield sample as the style anchor:
dark heroic Chinese ink-and-wash battlefield concept art,
black-gray-sepia palette, strong ink masses, expressive brush strokes,
controlled ink splatter, xuan-paper tone, cinematic rim light,
high-detail 2D painterly key art, dramatic but readable.

Character source from Romance of the Three Kingdoms:
{三国演义原文依据或概括}

Character design:
{外貌锚点}
{气质锚点}
{服饰锚点}

Scene:
{名场面锚点；战场、城池、江雾、残旗、追兵、火光等只作为烘托}

Composition:
Native vertical phone-safe composition, not a crop.
Full body visible from head to boots. Face in the upper-middle safe area.
The character is large and dominant, with enough margins around head, feet, cloak, and weapon.
Background remains secondary and lower contrast than the character.

Calligraphy:
Include native hand-brushed Chinese running/cursive calligraphy writing exactly "{人物名}"
in a quiet empty side area, integrated into the original painting, not a pasted overlay.
No other readable text, no watermark, no logo. The generated calligraphy must be manually checked.

If weapon is present:
{武器几何约束：只保留一件主武器；结构连续；不得重复、断裂、错位或遮挡脸和关键动作；复杂武器优先静态稳定构图}

Avoid:
ugly face, distorted anatomy, generic warrior, 3D render, CGI, photorealism,
glossy plastic armor, anime, modern fantasy armor, incorrect Chinese characters,
extra inscriptions, heavy random grain on the face, noisy face, muddy facial details,
fragmented weapon, duplicated weapon, extra limbs, distorted hands,
background stealing attention from the character.
```
