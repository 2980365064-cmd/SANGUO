# 三国人物立绘生成规范

## 风格母版

后续人物立绘以当前刘备候选为风格母版，但生成时不再追求强噪点式“粗糙水墨”。人物本体应改为更干净的水墨淡彩/工笔国风插画，纸纹与旧化感后期轻叠。

- 前端图：`web/public/portraits/sanguo/sanguo/core_001.webp`
- 源图：`web/public/portraits/sanguo/_source_png/sanguo/core_001.png`
- 参考样本：`web/public/portraits/sanguo/_style_trials/liu_bei_new_from_main_reference.webp`
- 低噪确认样本：`web/public/portraits/sanguo/_style_trials/core_004_zhaoyun_low_noise_long_spear.webp`
- 营销横版确认样本：`web/public/portraits/sanguo/marketing/core_004_zhaoyun_16x9_final.webp`
- 营销竖版确认样本：`web/public/portraits/sanguo/marketing/core_004_zhaoyun_douyin_9x16_final.webp`

这版不是从主界面直接裁切，而是以主界面刘备气质为参考重新生成。后续人物也应采用同样方法：使用项目内已有风格图作为参考，但输出必须是新图。

重要更新：后续原始生图优先生成 **16:9 横图**，人物全身完整居中，四周保留足够宣纸空间；前端竖版、头像、卡面、详情页用图都从 16:9 源图按需要二次裁剪。

宣传素材另行生成 **9:16 竖版原生构图**，不能直接硬裁 16:9 横图。竖版要让人物在手机画幅内完整站住，脸部位于上半屏安全区，右侧预留姓名题字空间，武器、披风、长袍不能被平台 UI 或画幅边缘切断。

## 生成流程

1. 先查《三国演义》原文或可靠转录文本，提取人物外貌、性格、身份、关键命运节点。
2. 把人物设定分成四类：
   - 外貌锚点：身形、脸型、须发、眼神、标志性特征。
   - 气质锚点：仁义、威严、刚烈、阴鸷、清雅、忠直等。
   - 服饰锚点：君主、文臣、武将、谋士、宗室、使者等身份差异。
   - 名场面锚点：优先选择《三国演义》中最能代表人物的动作、场景、命运瞬间。
3. 再按当前刘备样本的画风生成 16:9 横图源图。
4. 每个核心人物至少出 2-3 张候选，人工挑不丑、气质对、风格统一的一张入库。
5. 后续按 UI 需要裁剪成竖版立绘、头像、卡面，不直接让模型生成不同构图的小图。
6. 抖音/短视频宣传图单独生成 9:16 原生构图，营销图可以让 AI 直接生成原生毛笔草书/行草姓名题字，但必须人工验字；游戏正式立绘源图仍保持无字。

## 画风要求

- 2D 中国水墨历史插画，不要 3D、CG、照片写实、塑料皮肤、厚重金属高光。
- 人物本体采用干净的工笔水墨/淡彩国风插画：线条清楚、五官清晰、衣纹连续、武器完整。
- 宣纸纹理、灰褐云雾、低饱和淡彩可以保留，但不要让模型把纸纹、飞白、烟尘画成人物身上的随机噪点。
- 背景可以有少量水墨颗粒；人物脸、手、武器、衣袍主轮廓必须低噪点、高清晰。
- 长兵器必须结构完整、透视自然；枪、矛、偃月刀等不能缩短、断裂、错位或重复，必要时应从人物身后延伸以体现真实长度。
- 长枪类武器必须先锁定几何关系再生图：只能有一个锋刃；枪尾必须是钝头木杆；枪杆必须是一条连续直线，并穿过或贴近握手点；不得同时在两端出现枪头、红缨或金属刃。
- 对竖版手机图，长枪不要横跨过大画幅。优先采用稳定姿势：枪头在左下方，枪尾在右上方，赵云手握中下段，枪杆斜向穿过身体前侧或身体旁侧；右上只能是钝尾，不得画成第二个枪头。
- 人物要有好看的古典脸型，不能丑、不能怪、不能表情僵硬。
- 原始生图必须是 16:9 横图；人物全身完整，头冠到靴履完整入画，不能裁脚、裁袖、裁头。
- 人物应位于画面中央或略偏黄金分割位置，四周留出可裁剪空间。
- 背景服务人物气质，不能抢主体；背景复杂度和对比度必须低于人物。
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
Create a new full-body 2D Chinese ink-and-wash historical illustration of {人物名}
for a Three Kingdoms strategy game.

Use the current Liu Bei portrait as the style anchor:
clean 2D Chinese ink-and-wash / gongbi-tinted historical illustration,
clear brush outlines, muted gray-brown ink clouds, low-saturation colors,
controlled xuan-paper texture mostly in the background, hand-painted key art.

Character source from Romance of the Three Kingdoms:
{三国演义原文依据或概括}

Character design:
{外貌锚点}
{气质锚点}
{服饰锚点}

Environment:
{三国演义名场面锚点，作为背景和动作依据；场景只烘托人物，不能喧宾夺主}

Composition:
16:9 horizontal source image. Full body, crown to boots visible, centered,
generous xuan-paper breathing room for later cropping into portrait, avatar, or card art.

Avoid:
ugly face, distorted anatomy, generic warrior, 3D render, CGI, photorealism,
glossy armor, anime, readable text, calligraphy, title, seal stamp, watermark,
heavy random grain, noisy face, broken dry-brush artifacts on the character,
speckled skin, fragmented weapon, over-textured robe.
```
