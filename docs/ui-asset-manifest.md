# UI 复兴素材清单（第二阶段）

所有资产均为本项目生成的原创无文字视觉素材；它们只承担纸张、场景、图标与印记的质感，不包含外部作品的界面、角色或可识别元素。

| 分类 | 文件 | 页面用途 | 使用方式 |
| --- | --- | --- | --- |
| 纸纹 | `web/public/assets/ui/texture-paper-revival.webp` | 全局内容层、对话框 | 低不透明度乘算纹理，不能降低正文对比度 |
| 场景 | `scene/council-hall-revival.webp` | 廷议卷 | 非全屏卷内衬景 |
| 场景 | `scene/secret-chamber-revival.webp` | 密谈书案 | 非全屏内容背景 |
| 场景 | `scene/directive-desk-revival.webp` | 军府方略 | 非全屏文书背景 |
| 场景 | `scene/monthly-desk-revival.webp` | 每月总计 | 非全屏史册背景 |
| 场景 | `scene/map-dossier-revival.webp` | 地图地方档案 | 小型抽屉/信息条背景 |
| 场景文书 | `scene/map-desk-vertical-scroll-v1.png` | 天下舆图左侧军府案头 | 原创无文字竖向浅水墨卷轴；竹木轴、淡墨山水与中央留白共同承载可展开的本月待议入口 |
| 场景文书 | `scene/map-desk-scroll-roller-v1.png` | 天下舆图军府案头上下卷轴 | 用户确认的原创无文字透明竹轴；展开与收起共用同一根上轴，竹轴比纸卷宽，收合过程不换图 |
| 场景文书 | `scene/map-desk-scroll-roller-v2.png` | 天下舆图军府案头备用竹轴 | 原创透明竹轴备选素材，未作为默认引用 |
| 场景文书 | `scene/map-desk-scroll-roller-v3.png` | 天下舆图军府案头竹轴 | 原创无文字轻水墨透明竹轴；作为展开和收起的唯一外层竹轴 |
| 场景文书 | `scene/map-desk-scroll-paper-v2.png` | 天下舆图军府案头内页 | 原创无文字浅水墨内页纸；宽度固定小于 v3 竹轴，不含任何竹轴，展开时由同一根 v3 竹轴压住两端 |
| 场景文书 | `scene/map-desk-scroll-roller-v4.png` | 天下舆图军府案头收起竹轴 | 原创无文字短竹轴；由完整卷轴 v2 的竹轴参考先行生成，收起态使用 |
| 场景文书 | `scene/map-desk-vertical-scroll-v2.png` | 天下舆图军府案头展开卷轴 | 原创无文字完整浅水墨卷轴；基于 v4 竹轴生成，图内纸页已固定小于上下竹轴，展开态直接整图呈现，不拼接 |
| 场景文书 | `scene/map-desk-scroll-roller-v5.png` | 天下舆图军府案头细竹轴 | 原创无文字细竹轴；降低轴身与绑绳厚度，收起态默认使用 |
| 场景文书 | `scene/map-desk-vertical-scroll-v3.png` | 天下舆图军府案头细轴展开卷 | 原创无文字完整浅水墨卷轴；基于 v5 细竹轴生成，素材本身无矩形底框，卷纸固定小于竹轴 |
| 场景文书 | `scene/map-desk-scroll-roller-v6.png` | 天下舆图军府案头同源收起竹轴 | 从展开卷轴 v3 的顶部竹轴直接裁出；收起态与展开态使用完全相同的轴身、粗度和绑绳 |
| 场景文书 | `scene/map-desk-scroll-roller-v7.png` | 天下舆图军府案头纯竹轴 | 从展开卷轴 v3 的顶部竹轴直接裁出，并在卷纸起始像素前截断；收起态仅显示竹轴 |
| 舆图底景 | `web/public/底图_expanded-v2.png` | 天下舆图全屏底图 | 原创轻水墨舆图底景；基于旧版扩展图定向修复中央矩形压边，保留省份地貌与案头器物，地图不再呈现黑色容器边框 |
| 图框 | `web/public/assets/ui/bg-county-dossier-v2.png` | 地图地方档案 | 已保留的旧版原创簿册封皮；不再由州郡档案默认引用 |
| 图框 | `web/public/assets/ui/bg-county-dossier-ink-wash-v1.png` | 地图地方档案 | 默认的原创无文字浅水墨档案底景；灰青淡墨边缘、云气和留白，仅承载材质与边界，正文由 DOM 覆盖 |
| 地方簿册 | `web/public/assets/ui/bg-administrative-{province,commandery,city}-ledger-v1.png` | 州郡城地图档案 | 用户审核通过的原创无文字竖向档案底稿；州以统筹军政文书、郡以田亩仓籍、城以城垣军图区分职责。仅由 `MapInfoDrawer` 的对应层级引用，中央留白承载真实地方事实。 |
| 地方簿册 | `web/public/assets/ui/bg-administrative-{province,commandery,city}-ledger-v2.png` | 州郡城地图档案 | 用户审核通过的亮纸面重制版；题签、总览账栏、附卷与批注位置被画入素材结构，正文以卷页定位嵌入，深墨只留边缘以确保可读性。 |
| 地方簿册 | `web/public/assets/ui/bg-administrative-{province,commandery,city}-ledger-v3.png` | 州郡城地图档案 | 用户确认的连续宣纸版；不含表格、方块或数据卡。装饰仅留在边缘，正文以题签、墨线、留白和自然错页组织阅读。 |
| 场景文书 | `web/public/assets/ui/archive/council-record-v2.png` | 府堂廷议 | 原创无文字浅水墨府堂议录；中央留白承载议题、参议名录与书记记录，厅堂与案头物件只留在边缘 |
| 场景文书 | `web/public/assets/ui/archive/secret-letter-v2.png` | 单独密谈 | 原创无文字浅水墨私札书案；中央留白承载人物落款、往来私札与输入区，信封、封缄与砚台仅留在边缘 |
| 场景文书 | `web/public/assets/ui/archive/directive-ledger-v2.png` | 军府方略簿 | 原创无文字浅水墨军府簿；左缘来函、竹简与地形墨图组织建议附卷，中央留白承载连续四节军令 |
| 场景文书 | `web/public/assets/ui/archive/decree-review-v2.png` | 审阅颁令与确认短笺 | 原创无文字浅水墨封缄校阅卷；封缄、细绳与朱砂印记只留在边缘，中央承载待颁文书与最终确认 |
| 场景文书 | `web/public/assets/ui/archive/adjudication-record-v2.png` | 行止推演录 | 原创无文字浅水墨行军编年页；右缘行军路线与边缘地形只服务阶段纪事，中央承载连续推演记录 |
| 场景文书 | `web/public/assets/ui/archive/{city-ledger,character-biography,army-register,diplomacy-correspondence,event-memorial}-v2.png` | 地方、人物、军队、外交、事件档案 | 五张原创无文字浅水墨档案底景；分别以城镇、传记、军籍、使节往来与急报器物标识身份，中央均保留干净阅读区 |
| 场景文书 | `web/public/assets/ui/archive/{situation-desk,monthly-chronicle,history-book}-v2.png` | 局势、本月总计、史册 | 原创无文字浅水墨案头、月结册与编年册；中央留白承载真实游戏记录，边缘器物仅服务阅读身份 |
| 辅助纸签 | `web/public/assets/ui/archive/menu-paper-slip-v2.png` | 主菜单局势旁白 | 原创无文字轻水墨纸签，已去除色键背景，仅作菜单旁白边缘的辅助印记 |
| 道具图标 | `web/public/assets/ui/strategy-drafting-emblem-v1.png` | 天下舆图「拟定方略」入口 | 原创无文字方略纸、竹简与毛笔图标；透明底，朱砂仅作为小印记，由浅宣纸题签承载 |
| 城池图标 | `web/public/assets/ui/cities/{capital,fort,port,town}.png` | 天下舆图城池与势力范围图层 | 内置 AI 生成的原创、无文字、透明底浅水墨城池组；分别表现郡治、关隘、港埠与普通城，DOM 只叠加真实城权旗记与名称 |
| 图框 | `frame/frame-atlas-revival.webp` | 分隔、折页、重点框、档案框 | 图谱源文件；后续按组件需要切片 |
| 印记 | `seal/slices/{action,confirmed,danger,month-end}.webp` | 主行动、确认、危急、月结 | 不含文字；仅用于语义强调 |
| 状态 | `icon/slices/{people,legitimacy,morale,grain,wealth,intel,relation,risk,pending}.webp` | 国政指标、关系、风险和待裁决 | 1x 小图标，CSS 缩放到 14–20px |
| 道具 | `prop/command-prop-atlas-revival.webp` | 木牍、封缄、签牌 | 图谱源文件；仅用于密令与档案内容 |

## 质量门槛

- 优先以 WebP 提供；当构建环境无法无损转换新生成的场景文书时，允许前端直接引用已登记 PNG 源文件，后续构建链具备编码器后再补 WebP。
- 所有生成图均避免可读文字、伪汉字和外部作品标识；如日后发现问题，应重新生成而非在页面中掩盖。
- 内容卷的最大不透明度由 CSS 的浅纸渐变控制；地图是全局底层，素材不得把功能页改回全屏换场。
- 朱砂印记只表达提交、危急、月结或已确认；灰青用于结构和普通可行动状态。
