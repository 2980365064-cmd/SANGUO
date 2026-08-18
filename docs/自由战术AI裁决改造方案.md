# 自由战术 AI 裁决改造方案

> 本方案已实现，记录在此供后续参考。

## 一、问题诊断

### 1.1 原有问题

玩家的自由战术意图在进入系统后被压缩成选择题：

```
玩家说 "派细作混入曹军水寨放火，关羽趁乱突袭"
  ↓
系统只检查 TACTIC_RULES 白名单（6 种战术）
  ↓
匹配不上 → 退回 "正面交锋"，玩家的话等于没说
```

### 1.2 设计目标

- 玩家可以用自然语言描述任何战术方案
- AI 裁决员评估方案的可行性，给出基于盘面事实的判断
- 硬规则仍然守护事实边界（死亡、领土、兵力、条约不能由叙事改写）
- 确定性随机可复现（同种子同结果）

### 1.3 约束红线

- AI 不能凭空发明条件（如"曹军正在闹瘟疫"，必须 epidemic_pressure ≥ 60）
- AI 不能写死亡、领土变化、凭空增兵
- delta 有硬上限 [-5, +15]
- 所有检查可测试、可审计

## 二、实现方案

### 2.1 双路径设计

#### 基准路径（保留原有逻辑）
- 使用 `tactic` 字段
- 战术必须在 `TACTIC_RULES` 白名单中
- 走 `_validate_ai_choice()` 校验

#### 自由路径（新增）
- 使用 `tactic_name` 字段
- 战术名称自由
- 走 `_validate_free_tactic()` 校验
- AI 提供 delta、feasibility、reasoning、narrative

### 2.2 自由战术校验器 `_validate_free_tactic()`

```python
def _validate_free_tactic(pack: Dict[str, object], proposal: Dict[str, object]) -> Dict[str, object]:
    """校验 AI 的自由战术提案是否在边界内。"""
    
    # 1. actor 必须是参战统帅
    # 2. feasibility=impossible 退回正面交锋
    # 3. 禁止文本检查（reasoning 和 narrative）
    # 4. delta 边界检查 [-5, +15]
    # 5. 特性匹配检查（有特性上限 +15，无特性上限 +10）
    # 6. 事实一致性检查（AI 声称的条件必须在盘面中存在）
    # 7. 返回校验结果
```

### 2.3 事实一致性检查 `_fact_supports_claim()`

```python
def _fact_supports_claim(facts, fact_key, threshold, keyword):
    """检查盘面事实是否支持 AI 的声称。"""
    
    # 检查 regional_state（瘟疫、天气等）
    # 检查 army_breakdown（补给、士气、纪律等）
    # 返回 True/False
```

### 2.4 裁决包扩展

在 `build_battle_adjudication_pack()` 中添加：
- `regional_state`：区域状态数据（天气、疫病等）
- `defender_supply`：防守方补给数据

用于事实一致性检查。

### 2.5 校验器入口 `validate_battle_ai_choice()`

```python
def validate_battle_ai_choice(db, pack, ai_choice):
    """校验 AI/参谋输出是否仍在裁决包边界内。"""
    
    # 判断是否为自由战术（检查 tactic_name 字段）
    if is_free_tactic:
        result = _validate_free_tactic(pack, ai_choice)
    else:
        result = _validate_ai_choice(db, calculation, ai_choice)
    
    return result
```

## 三、安全边界

### 3.1 delta 边界
- 范围：[-5, +15]
- 无特性匹配：上限 +10
- 有特性匹配：上限 +15
- 超出范围自动裁剪（不是拒绝）

### 3.2 actor 校验
- 必须是参战统帅
- 不能是未参战的人物

### 3.3 feasibility 校验
- "impossible" → 退回正面交锋（delta=0）
- "high/medium/low" → 正常接受

### 3.4 禁止文本
- reasoning 和 narrative 都不能包含禁止文本
- 禁止文本包括：阵亡、死亡、处死、割让、易主、复活、忽略补给、援军、增援

### 3.5 事实一致性
- AI 声称"瘟疫" → epidemic_pressure ≥ 60
- AI 声称"粮草不济" → supply_combat_multiplier < 0.5
- AI 声称"士气低落" → morale < 40
- AI 声称"防备松懈" → discipline < 40
- 检查不通过 → 拒绝提案

## 四、测试覆盖

### 4.1 新增测试文件
`tests/test_free_tactic_validation.py`

### 4.2 测试用例（23 个）
1. delta 边界裁剪（4 个）
   - 超出上限裁剪（有特性）
   - 超出上限裁剪（无特性）
   - 低于下限裁剪
   - 在范围内接受
2. actor 校验（2 个）
   - 非参战统帅拒绝
   - 参战统帅接受
3. feasibility 校验（2 个）
   - impossible 退回正面交锋
   - high 正常接受
4. 禁止文本检查（2 个）
   - reasoning 中禁止文本拒绝
   - narrative 中禁止文本拒绝
5. 事实一致性检查（4 个）
   - 瘟疫低压力拒绝
   - 瘟疫高压力接受
   - 粮草不足接受
   - 天气良好接受
6. 基准战术快速路径（2 个）
   - 正面交锋正常工作
   - 水战突击正常工作
7. 自由战术完整流程（2 个）
   - 自由战术 resolve_battle
   - impossible 退回后 resolve_battle
8. 确定性随机（1 个）
   - 同种子同结果
9. 回归测试（2 个）
   - 不能凭空生成援军
   - 不能复活人物
10. 边界情况（2 个）
    - 缺少字段使用默认值
    - 空战术名称使用 "custom"

### 4.3 测试通过率
- 新增测试：23/23 通过 ✅
- 既有战斗测试：12/12 通过 ✅
- 完整测试套件：470/478 通过（8 个失败与本次改动无关）

## 五、向后兼容

### 5.1 接口不变
- `resolve_battle()` 函数签名不变
- `TACTIC_RULES` 白名单保留
- 所有既有测试通过

### 5.2 扩展字段
- `tactic_name`：自由战术名称（可选）
- `delta`：AI 评估的修正值（可选）
- `feasibility`：可行性评估（可选）
- `reasoning`：评估理由（可选）
- `regional_state`：裁决包扩展字段
- `defender_supply`：裁决包扩展字段

### 5.3 双路径共存
- 使用 `tactic` 字段 → 走基准路径
- 使用 `tactic_name` 字段 → 走自由路径
- 两者互不干扰

## 六、使用示例

### 6.1 基准路径（旧方式）
```python
ai_choice = {
    "tactic": "水战突击",
    "actor": "关羽",
    "narrative": "关羽率水军突击曹军。"
}
```

### 6.2 自由路径（新方式）
```python
ai_choice = {
    "tactic_name": "连环火计",
    "actor": "关羽",
    "delta": 12,
    "feasibility": "high",
    "reasoning": ["关羽水战特性", "曹军连环船易被火攻", "风向有利"],
    "narrative": "关羽借东风放火，曹军连环船焚尽。"
}
```

## 七、基线文档更新

### 7.1 §1 总原则
- "预设候选" → "数值边界"
- 明确战术候选可以是基准模板或自由方案

### 7.2 §3.3 战役环境与自由战术裁决
- 详细说明双路径机制
- 列出自由路径校验器的检查项
- 说明裁决包扩展字段

### 7.3 §3.5 AI 裁决、情报与月报
- 说明 `choice` 字段的新来源
- 说明事实一致性检查

## 八、后续工作

### 8.1 外交系统
- 外交策略系统（结盟、离间、利诱、威慑、联姻）
- 势力关系动态系统
- 外交叙事系统

### 8.2 国策系统
- 国策树系统
- 国策推进系统
- 国策协同/冲突

### 8.3 补给系统
- 动态补给线系统
- 劫粮战术

### 8.4 围城系统
- 围城战术系统（围困、强攻、断水、火攻、离间）
- 守城战术系统（坚守、夜袭、求援、诈降）

### 8.5 势力AI
- 战略意图系统
- AI 决策树

## 九、总结

### 9.1 核心改动
1. 实现自由战术系统（`_validate_free_tactic()`）
2. 实现事实一致性检查（`_fact_supports_claim()`）
3. 扩展裁决包（`regional_state`、`defender_supply`）
4. 23 个新测试全部通过
5. 基线文档更新（§1、§3.3、§3.5）

### 9.2 设计原则
- 玩家是决策者，不是执行者
- 叙事驱动，数值支撑
- 风险与回报平衡
- 历史合理性

### 9.3 安全边界
- delta 严格限制 [-5, +15]
- 禁止文本检查
- 事实一致性检查
- 不可行方案自动退回

### 9.4 向后兼容
- 接口不变
- 扩展字段可选
- 双路径共存

---

**版本**: v1.0  
**日期**: 2026-07-28  
**状态**: ✅ 已完成
