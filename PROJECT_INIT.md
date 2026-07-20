# PROJECT_INIT — 汉祚再兴·刘备传

## 产品边界

- 玩家固定为刘备。
- 开局固定为 208 年 8 月赤壁前夕。
- 一回合一个月，最迟 223 年 4 月收束。
- 演义人物关系与事件顺序为叙事依据。
- LLM 文本不得直接写入人物死亡、领土易主、割地、军队覆灭或政权消亡。

## 当前盘面

- `scenario_id=sanguo_liubei_208`
- 35 节点、46 边、9 势力、25 军、140 人。
- 刘备无正式控制郡县，以夏口驻军权开局。
- 六指标：军资、粮秣、民望、名分、军心、士族支持。

## 启动

```bash
python3 -m pip install -r requirements.txt
cd web && npm ci && npm run build && cd ..
python3 -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

桌面模式：

```bash
python3 launcher.py
```

## 验证

```bash
python3 -m pytest tests -q
cd web && npm run build
```

专项发布门：

```bash
python3 -m pytest \
  tests/test_legacy_cleanup.py \
  tests/test_army_orders.py \
  tests/test_battle_resolution.py \
  tests/test_diplomacy.py \
  tests/test_historical_events.py \
  tests/test_power_ai.py -q
```

## 事实源

实施与恢复必须先读：

1. `docs/superpowers/plans/2026-07-16-sanguo-liubei-full-conversion.md`
2. `/Users/zhuanzmima0000/Desktop/三国刘备视角_二开设计决策.md`
3. `/Users/zhuanzmima0000/Desktop/刘备视角_赤壁前夕至蜀汉建国_三国演义时间线.md`
4. `/Users/zhuanzmima0000/Desktop/208开局人物能力表_审核版.md`
5. `/Users/zhuanzmima0000/Desktop/208开局人物初始状态注册表_审核版.md`
6. `/Users/zhuanzmima0000/Desktop/人物特性效果对照表_审核版.md`
7. `/Users/zhuanzmima0000/Desktop/人物属性作用矩阵_最终版.md`
8. `/Users/zhuanzmima0000/Desktop/208开局军队编制表_审核版.md`
9. `/Users/zhuanzmima0000/Desktop/36节点路线与关隘表_审核版.md`

审核通过的具体数据表覆盖同类早期概述；地图最终口径为 13 州、35 节点、46 边。

## 会话结束

每次编程会话结束前更新：

`/Users/zhuanzmima0000/Documents/Obsidian Vault/wiki/DeepSeek-观察/2026-07-16.md`

记录完成阶段、验证命令、测试证据、长期发现与下一恢复点。
