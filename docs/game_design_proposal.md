# 汉祚再兴 · 刘备传 - 游戏机制设计提案

## 一、当前系统分析

### 1.1 核心系统现状

#### 战斗系统（battle.py）
- **当前机制**：60% 硬规则 + 40% AI 战术
- **评分公式**：兵力 × 质量乘数 × 统帅乘数 × 疲劳乘数 × 补给乘数 × 地形乘数 × 特性乘数
- **战术系统**：6 种预设战术（正面交锋、佯攻诱敌、夜袭、火攻、水战突击、山地伏击）
- **问题**：
  - 战术选项固定，玩家无法自由发挥
  - 战术选择受限于角色特性，缺乏创造性
  - AI 评分权重（60/40）可能过于偏向硬规则

#### 外交系统（diplomacy.py）
- **当前机制**：接受率公式（40 + 关系×0.2 + 信任×0.2 + 外交属性修正）
- **问题**：
  - 外交是纯数值计算，缺乏叙事深度
  - 缺乏"外交策略"概念（如离间、利诱、威慑）
  - 势力间的互动过于简单

#### 国策系统（national_focus.py）
- **当前机制**：11 个预设国策，按月推进
- **问题**：
  - 国策是固定列表，玩家无法自定义战略方向
  - 缺乏国策之间的协同效应
  - 缺乏"国策冲突"概念（如"军屯"与"屯田"的竞争）

#### 补给系统（supply.py）
- **当前机制**：郡仓供粮 → 消耗携粮 → 断粮惩罚
- **问题**：
  - 补给线是静态的，缺乏战略纵深
  - 缺乏"劫粮"等战术选项
  - 断粮惩罚过于严厉（2% 逃散 + 65% 战力）

#### 围城系统（siege.py）
- **当前机制**：围城进度 = 34 × 攻方评分/守方评分
- **问题**：
  - 围城过于依赖兵力对比
  - 缺乏"断水"、"火攻"等围城战术
  - 守城方缺乏主动出击选项

#### 势力AI（power_ai.py）
- **当前机制**：行动评分 + 合法候选 + 行动槽限制
- **问题**：
  - AI 行为过于机械化
  - 缺乏"战略意图"概念
  - 势力间的互动缺乏叙事

### 1.2 优势系统

#### 随机性系统（world_random.py）
- **优势**：
  - 存档级确定性随机，完全可复现
  - 区域事件系统丰富（天气、灾害、疫病）
  - 情报分层（谣言、评估、确认）

#### 裁决系统（adjudication.py）
- **优势**：
  - 严格的边界控制，防止 AI 越权
  - 统一的裁决流程
  - 完整的审计追踪

---

## 二、核心设计理念

### 2.1 设计原则

1. **玩家是决策者，不是执行者**
   - 玩家提出策略意图，AI 负责具体执行
   - 玩家应该能够"说"想要做什么，而不是"选"预设选项

2. **叙事驱动，数值支撑**
   - 所有机制都应该服务于叙事
   - 数值变化应该有合理的叙事解释

3. **风险与回报平衡**
   - 高风险策略应该有高回报潜力
   - 低风险策略应该有稳定但有限的收益

4. **历史合理性**
   - 策略应该符合三国时代的历史背景
   - 不应该出现超时代的策略（如火药、蒸汽机）

### 2.2 游戏核心循环

```
每月循环：
1. 情报收集 → 了解天下大势
2. 战略讨论 → 与谋臣商议策略
3. 决策制定 → 确定本月行动方针
4. 执行推演 → AI 执行具体行动
5. 结果反馈 → 查看执行结果和影响
```

---

## 三、战斗系统改进提案

### 3.1 自由战术系统

#### 设计理念
- 玩家可以用自然语言描述战术意图
- AI 基于盘面事实评估可行性
- 保留基准战术作为"安全选项"

#### 实现方案

##### 3.1.1 战术评估框架

```python
TACTIC_EVALUATION_DIMENSIONS = {
    "地形适应性": {
        "山地": ["伏击", "游击", "断后"],
        "平原": ["冲锋", "骑射", "包围"],
        "水网": ["水战", "渡河", "火攻"],
        "城池": ["攻城", "围困", "断水"]
    },
    "天气影响": {
        "雨天": ["火攻失效", "泥泞", " visibility降低"],
        "雪天": ["奇袭", "冻伤", "补给困难"],
        "晴天": ["常规作战", "visibility良好"]
    },
    "兵力对比": {
        "优势": ["包围", "分进合击", "正面碾压"],
        "劣势": ["伏击", "游击", "诈败"],
        "均势": ["对峙", "试探", "寻找破绽"]
    },
    "士气因素": {
        "高士气": ["冲锋", "死战", "追击"],
        "低士气": ["撤退", "投降", "哗变风险"]
    },
    "补给状况": {
        "充足": ["持久战", "围困", "消耗"],
        "紧张": ["速战速决", "劫粮", "撤退"]
    }
}
```

##### 3.1.2 战术可行性评估

```python
def evaluate_tactic_feasibility(pack, tactic_description):
    """
    评估战术可行性，返回：
    - feasibility: "高"/"中"/"低"/"不可行"
    - delta: 修正值 (-5 到 +15)
    - reasoning: 评估理由
    - risks: 潜在风险
    """
    
    # 1. 解析战术意图
    tactic_intent = parse_tactic_intent(tactic_description)
    
    # 2. 检查地形适应性
    terrain_score = check_terrain_fit(tactic_intent, pack.terrain)
    
    # 3. 检查天气影响
    weather_score = check_weather_impact(tactic_intent, pack.weather)
    
    # 4. 检查兵力对比
    force_ratio = pack.attacker_force / pack.defender_force
    force_score = check_force_ratio(tactic_intent, force_ratio)
    
    # 5. 检查士气因素
    morale_score = check_morale(tactic_intent, pack.attacker_morale, pack.defender_morale)
    
    # 6. 检查补给状况
    supply_score = check_supply(tactic_intent, pack.attacker_supply, pack.defender_supply)
    
    # 7. 检查角色特性
    trait_score = check_commander_traits(tactic_intent, pack.commander_traits)
    
    # 8. 综合评分
    total_score = (
        terrain_score * 0.2 +
        weather_score * 0.15 +
        force_score * 0.2 +
        morale_score * 0.15 +
        supply_score * 0.15 +
        trait_score * 0.15
    )
    
    # 9. 计算 delta
    if total_score >= 0.8:
        feasibility = "高"
        delta = min(15, int(total_score * 15))
    elif total_score >= 0.6:
        feasibility = "中"
        delta = min(10, int(total_score * 12))
    elif total_score >= 0.4:
        feasibility = "低"
        delta = min(5, int(total_score * 8))
    else:
        feasibility = "不可行"
        delta = 0
    
    # 10. 生成理由和风险
    reasoning = generate_reasoning(tactic_intent, pack)
    risks = generate_risks(tactic_intent, pack)
    
    return {
        "feasibility": feasibility,
        "delta": delta,
        "reasoning": reasoning,
        "risks": risks
    }
```

##### 3.1.3 玩家交互流程

```
玩家输入："我想让关羽水军趁夜突袭曹军水寨，用火攻烧毁他们的战船"

AI 评估：
1. 地形：水网地形，水战适应性 +8
2. 天气：晴天，visibility良好，适合夜袭 +5
3. 兵力：关羽水军 6500 vs 曹军水军 8000，兵力劣势 -3
4. 士气：关羽军士气 76，曹军士气 82，略低 -2
5. 补给：双方补给充足，无明显影响 0
6. 特性：关羽有"水战"特性 +10，"武圣" +5

综合评分：0.75
可行性：中
delta: +9

理由：
- 水战地形适合水军作战
- 夜袭可以打敌人措手不及
- 兵力略处劣势
- 关羽水战特性加成明显

风险：
- 曹军水寨可能有防备
- 火攻可能失败（需要风向配合）
- 夜袭失败可能导致士气大跌

建议：
- 可以考虑先派小股部队试探
- 或者等待风向有利时再发动
```

### 3.2 战术协同系统

#### 设计理念
- 多个战术可以组合使用
- 成功的协同可以产生额外效果
- 失败的协同可能导致混乱

#### 实现方案

```python
TACTIC_SYNERGIES = {
    ("佯攻", "伏击"): {
        "success_bonus": 8,
        "description": "佯攻成功时，伏击效果加倍"
    },
    ("火攻", "水战"): {
        "success_bonus": 10,
        "description": "水上火攻，效果显著"
    },
    ("断粮", "围困"): {
        "success_bonus": 6,
        "description": "断粮后围困，守军更快崩溃"
    },
    ("离间", "夜袭"): {
        "success_bonus": 5,
        "description": "离间成功后夜袭，守军反应迟钝"
    }
}

TACTIC_ANTAGONIES = {
    ("冲锋", "撤退"): {
        "penalty": -10,
        "description": "前后矛盾的命令导致混乱"
    },
    ("火攻", "雨天"): {
        "penalty": -8,
        "description": "雨天火攻无效"
    }
}
```

### 3.3 战斗环境系统改进

#### 设计理念
- 环境因素应该更显著地影响战斗
- 玩家可以利用环境因素
- 环境变化应该动态发生

#### 实现方案

```python
ENVIRONMENTAL_FACTORS = {
    "风向": {
        "fire_attack": "+50% 效果" if "顺风" else "-50% 效果" if "逆风",
        "arrow_volley": "+10% 效果" if "顺风" else "-10% 效果" if "逆风"
    },
    "水位": {
        "naval_battle": "+20% 效果" if "水位上涨" else "-20% 效果" if "水位下降",
        "river_crossing": "难度增加" if "水位上涨"
    },
    "温度": {
        "morale": "-5% 士气" if "严寒" else "+5% 士气" if "温暖",
        "supply_consumption": "+20% 消耗" if "严寒"
    },
    "能见度": {
        "ambush": "+30% 成功率" if "低visibility" else "-30% 成功率" if "高visibility",
        "archery": "-20% 效果" if "低visibility"
    }
}
```

---

## 四、外交系统改进提案

### 4.1 外交策略系统

#### 设计理念
- 玩家可以使用多种外交策略
- 不同策略有不同的成功率和代价
- 外交结果影响长期关系

#### 实现方案

```python
DIPLOMATIC_STRATEGIES = {
    "结盟": {
        "base_success": 40,
        "modifiers": {
            "relation": 0.2,
            "trust": 0.2,
            "common_enemy": 15,
            "dynasty_marriage": 20
        },
        "cost": {"gold": 100, "prestige": 50},
        "effects": {
            "military_cooperation": True,
            "trade_agreement": True,
            "non_aggression": True
        }
    },
    "离间": {
        "base_success": 30,
        "modifiers": {
            "target_trust": -0.3,
            "spy_quality": 0.4,
            "existing_rivalry": 20
        },
        "cost": {"gold": 200, "spy": 1},
        "effects": {
            "relation": -30,
            "trust": -20,
            "may_trigger_war": True
        }
    },
    "利诱": {
        "base_success": 50,
        "modifiers": {
            "gift_value": 0.5,
            "target_need": 0.3,
            "target_greed": 0.2
        },
        "cost": {"gold": 500, "goods": "根据需求"},
        "effects": {
            "temporary_cooperation": 3,  # 3 个月
            "prestige": -20
        }
    },
    "威慑": {
        "base_success": 40,
        "modifiers": {
            "military_strength": 0.3,
            "reputation": 0.2,
            "target_courage": -0.2
        },
        "cost": {"prestige": 30},
        "effects": {
            "target_morale": -10,
            "may_trigger_resistance": True
        }
    },
    "联姻": {
        "base_success": 60,
        "modifiers": {
            "bride_value": 0.3,
            "target_need": 0.2,
            "existing_relation": 0.1
        },
        "cost": {"family_member": 1},
        "effects": {
            "trust": +30,
            "relation": +40,
            "alliance_duration": 12  # 12 个月
        }
    }
}
```

### 4.2 势力关系动态系统

#### 设计理念
- 势力关系不是静态数值
- 关系变化有具体原因
- 关系影响 AI 行为

#### 实现方案

```python
RELATIONSHIP_FACTORS = {
    "历史事件": {
        "helped_in_war": +20,
        "betrayed_alliance": -30,
        "killed_relative": -50,
        "saved_from_disaster": +40
    },
    "当前互动": {
        "trade_partnership": +2,  # 每月
        "military_cooperation": +3,  # 每月
        "border_skirmish": -5,  # 每次
        "diplomatic_insult": -10  # 每次
    },
    "战略态势": {
        "common_enemy": +15,
        "territorial_dispute": -20,
        "power_balance": +5 if "均衡" else -5 if "失衡"
    },
    "个人关系": {
        "friendship": +10,
        "rivalry": -15,
        "family_tie": +25
    }
}
```

### 4.3 外交叙事系统

#### 设计理念
- 外交结果应该有丰富的叙事
- 使臣的能力和性格影响外交过程
- 外交失败也有叙事价值

#### 实现方案

```python
DIPLOMATIC_NARRATIVES = {
    "结盟成功": [
        "使者不辱使命，{target}君主欣然应允，两国歃血为盟。",
        "经过多轮谈判，双方终于达成共识，缔结盟约。",
        "{envoy}凭借三寸不烂之舌，说服{target}君主结盟抗{enemy}。"
    ],
    "结盟失败": [
        "{target}君主态度暧昧，最终婉言拒绝。",
        "谈判陷入僵局，{envoy}无功而返。",
        "{target}提出苛刻条件，双方未能达成一致。"
    ],
    "离间成功": [
        "间谍成功散布谣言，{target}君臣生隙。",
        "{envoy}巧施反间计，{target}内部矛盾激化。",
        "密探传来消息，{target}大将心生不满。"
    ],
    "离间失败": [
        "{target}识破离间计，使者被驱逐出境。",
        "间谍行动暴露，{target}加强戒备。",
        "{target}君臣同心，离间计未能奏效。"
    ]
}
```

---

## 五、国策系统改进提案

### 5.1 国策树系统

#### 设计理念
- 国策形成科技树结构
- 玩家选择战略方向
- 国策之间有协同和冲突

#### 实现方案

```python
NATIONAL_FOCUS_TREE = {
    "军事": {
        "军屯": {
            "cost": 10,
            "prerequisites": [],
            "effects": {
                "grain_output": +8,
                "supply_cost": -10
            },
            "conflicts_with": ["屯田"]
        },
        "精兵": {
            "cost": 12,
            "prerequisites": ["军屯"],
            "effects": {
                "army_training": +15,
                "maintenance_cost": +10
            },
            "conflicts_with": []
        },
        "马政": {
            "cost": 12,
            "prerequisites": [],
            "effects": {
                "cavalry_strength": +15,
                "horse_breeding": +10
            },
            "conflicts_with": ["屯田"]
        }
    },
    "内政": {
        "屯田": {
            "cost": 9,
            "prerequisites": [],
            "effects": {
                "grain_output": +6,
                "population_growth": +5
            },
            "conflicts_with": ["军屯", "马政"]
        },
        "招贤": {
            "cost": 10,
            "prerequisites": [],
            "effects": {
                "recruitment_rate": +10,
                "talent_attraction": +15
            },
            "conflicts_with": []
        },
        "法治": {
            "cost": 11,
            "prerequisites": ["招贤"],
            "effects": {
                "corruption": -10,
                "public_order": +15
            },
            "conflicts_with": ["宽政"]
        }
    },
    "外交": {
        "远交近攻": {
            "cost": 12,
            "prerequisites": [],
            "effects": {
                "distant_relation": +10,
                "neighbor_hostility": +15
            },
            "conflicts_with": ["近交远攻"]
        },
        "合纵连横": {
            "cost": 15,
            "prerequisites": ["远交近攻"],
            "effects": {
                "alliance_slots": +1,
                "diplomacy_cost": -15
            },
            "conflicts_with": []
        }
    }
}
```

### 5.2 国策推进系统

#### 设计理念
- 国策推进需要时间和资源
- 可以并行推进多个国策
- 国策效果逐步显现

#### 实现方案

```python
FOCUS_PROGRESSION = {
    "monthly_progress": 10,  # 基础每月进度
    "modifiers": {
        "minister_ability": 0.1,  # 负责官员能力
        "resource_allocation": 0.2,  # 资源投入
        "public_support": 0.05  # 民心支持
    },
    "completion_effects": [
        "第一月：效果 30%",
        "第二月：效果 60%",
        "第三月：效果 100%"
    ]
}
```

---

## 六、补给系统改进提案

### 6.1 动态补给线系统

#### 设计理念
- 补给线是动态的，可以被切断
- 玩家可以保护补给线
- 劫粮成为有效战术

#### 实现方案

```python
SUPPLY_LINE_SYSTEM = {
    "supply_route": {
        "length": "从粮仓到军队的距离",
        "security": "沿线友方城池数量",
        "vulnerability": "敌方军队威胁度"
    },
    "supply_consumption": {
        "base": "兵力 / 1000",
        "modifiers": {
            "terrain": "山地 +20%，平原 0%",
            "weather": "雨天 +10%，雪天 +20%",
            "morale": "低士气 +15%"
        }
    },
    "supply_interrupt": {
        "causes": [
            "敌方军队驻扎在补给线上",
            "补给线经过敌方 territory",
            "山贼/流寇骚扰"
        ],
        "effects": [
            "粮食消耗 +50%",
            "士气 -10",
            "可能出现逃兵"
        ]
    }
}
```

### 6.2 劫粮战术

#### 设计理念
- 玩家可以派小队劫掠敌方粮草
- 劫粮成功可以大幅削弱敌人
- 劫粮失败可能导致小队覆没

#### 实现方案

```python
GRAIN_RAID_SYSTEM = {
    "success_formula": {
        "base": 50,
        "modifiers": {
            "raid_leader_intelligence": 0.3,
            "raid_leader_courage": 0.2,
            "target_supply_security": -0.4,
            "raid_force_size": -0.2,  # 越小越容易成功
            "terrain": "山地 +15，平原 -10"
        }
    },
    "success_effects": {
        "target_supply": -30,
        "target_morale": -15,
        "raider_morale": +10,
        "loot": "获得部分粮草"
    },
    "failure_effects": {
        "raid_force": "可能全军覆没",
        "raider_morale": -20,
        "prestige": -10
    }
}
```

---

## 七、围城系统改进提案

### 7.1 围城战术系统

#### 设计理念
- 围城不只是兵力对比
- 玩家可以使用多种围城战术
- 守城方也有主动选项

#### 实现方案

```python
SIEGE_TACTICS = {
    "围困": {
        "description": "长期围困，等待守军断粮",
        "effects": {
            "defender_supply": -5,  # 每月
            "defender_morale": -3,  # 每月
            "attacker_supply": -2  # 每月
        },
        "duration": "3-6 个月"
    },
    "强攻": {
        "description": "集中兵力强行攻城",
        "success_formula": {
            "base": 40,
            "modifiers": {
                "attacker_force": 0.3,
                "defender_fortification": -0.2,
                "attacker_morale": 0.1,
                "siege_equipment": 0.2
            }
        },
        "cost": {
            "attacker_casualties": 15-25%
        }
    },
    "断水": {
        "description": "切断城中水源",
        "requirements": "城池靠近河流",
        "effects": {
            "defender_morale": -10,
            "defender_health": -15,
            "may_cause_surrender": True
        }
    },
    "火攻": {
        "description": "用火攻破坏城防",
        "requirements": "需要火攻特性或易燃物",
        "success_formula": {
            "base": 35,
            "modifiers": {
                "wind_direction": 0.3,
                "city_material": 0.2,
                "fire_attack_trait": 0.3
            }
        },
        "effects": {
            "fortification": -20,
            "civilian_casualties": 10-20%
        }
    },
    "离间": {
        "description": "离间守军内部",
        "success_formula": {
            "base": 30,
            "modifiers": {
                "spy_quality": 0.3,
                "defender_cohesion": -0.2,
                "defender_morale": -0.1
            }
        },
        "effects": {
            "may_cause_betrayal": True,
            "defender_morale": -15
        }
    }
}
```

### 7.2 守城战术系统

#### 设计理念
- 守城方不是被动挨打
- 守城方可以主动出击
- 守城战术影响战局

#### 实现方案

```python
DEFENSE_TACTICS = {
    "坚守": {
        "description": "死守城池，等待援军",
        "effects": {
            "fortification_bonus": +20,
            "defender_morale": +5
        }
    },
    "夜袭": {
        "description": "夜间突袭围城军队",
        "success_formula": {
            "base": 40,
            "modifiers": {
                "sortie_leader_courage": 0.3,
                "attacker_vigilance": -0.2,
                "defender_morale": 0.2
            }
        },
        "effects": {
            "attacker_siege_progress": -15,
            "attacker_morale": -10
        }
    },
    "求援": {
        "description": "向友军求援",
        "success_formula": {
            "base": 50,
            "modifiers": {
                "relation_with_allies": 0.3,
                "distance_to_allies": -0.2,
                "prestige": 0.1
            }
        },
        "effects": {
            "may_trigger_relief_army": True
        }
    },
    "诈降": {
        "description": "假装投降，伺机反击",
        "success_formula": {
            "base": 25,
            "modifiers": {
                "defender_intelligence": 0.3,
                "attacker_suspicion": -0.2,
                "desperation": 0.2
            }
        },
        "effects": {
            "may_assassinate_attacker": True,
            "may_open_gate_for_sortie": True
        }
    }
}
```

---

## 八、势力AI改进提案

### 8.1 战略意图系统

#### 设计理念
- AI 有长期战略目标
- 战略意图影响 AI 行为
- 玩家可以探测 AI 意图

#### 实现方案

```python
STRATEGIC_INTENTIONS = {
    "扩张型": {
        "description": "积极扩张领土",
        "behaviors": [
            "优先攻击弱邻",
            "积极结盟",
            "大力发展军备"
        ],
        "indicators": [
            "兵力集中在边境",
            "外交活跃",
            "军费开支高"
        ]
    },
    "防守型": {
        "description": "固守现有领土",
        "behaviors": [
            "加强城防",
            "避免主动出击",
            "寻求和平"
        ],
        "indicators": [
            "兵力分散在城池",
            "外交低调",
            "军费开支低"
        ]
    },
    "平衡型": {
        "description": "维持势力平衡",
        "behaviors": [
            "合纵连横",
            "制衡强权",
            "伺机而动"
        ],
        "indicators": [
            "外交频繁但谨慎",
            "兵力适度",
            "关注多方动态"
        ]
    }
}
```

### 8.2 AI 决策树

#### 设计理念
- AI 决策有清晰的逻辑
- 决策考虑多方因素
- 决策有可解释性

#### 实现方案

```python
AI_DECISION_TREE = {
    "评估威胁": {
        "military_threat": "敌方兵力 vs 我方兵力",
        "economic_threat": "敌方经济 vs 我方经济",
        "diplomatic_threat": "敌方盟友 vs 我方盟友"
    },
    "评估机会": {
        "weak_neighbor": "有弱邻可以攻击",
        "internal_unrest": "敌方内部动乱",
        "diplomatic_opportunity": "可以结盟的机会"
    },
    "决策矩阵": {
        "高威胁 + 高机会": "主动出击",
        "高威胁 + 低机会": "防守求援",
        "低威胁 + 高机会": "扩张领土",
        "低威胁 + 低机会": "发展内政"
    }
}
```

---

## 九、平衡性设计

### 9.1 战斗平衡

#### 核心原则
- 兵力不是唯一因素
- 地形和士气很重要
- 奇谋可以以弱胜强

#### 平衡参数

```python
BATTLE_BALANCE = {
    "force_ratio_weight": 0.3,  # 兵力权重
    "quality_weight": 0.2,  # 质量权重
    "terrain_weight": 0.15,  # 地形权重
    "morale_weight": 0.15,  # 士气权重
    "tactic_weight": 0.2,  # 战术权重
    
    "max_delta": 15,  # 最大战术修正
    "min_win_probability": 5,  # 最低胜率
    "max_win_probability": 95,  # 最高胜率
    
    "casualty_rate": {
        "winner": "5-8%",
        "loser": "18-21%"
    },
    
    "morale_change": {
        "winner": "+3",
        "loser": "-10"
    }
}
```

### 9.2 外交平衡

#### 核心原则
- 外交不是万能药
- 背叛有代价
- 信誉很重要

#### 平衡参数

```python
DIPLOMACY_BALANCE = {
    "base_success_rate": 40,
    "max_success_rate": 90,
    "min_success_rate": 5,
    
    "betrayal_penalty": {
        "trust": -30,
        "relation": -20,
        "prestige": -15
    },
    
    "alliance_benefits": {
        "military_cooperation": True,
        "trade_agreement": True,
        "intelligence_sharing": True
    },
    
    "maintenance_cost": {
        "gold": 10,
        "prestige": 5
    }
}
```

### 9.3 经济平衡

#### 核心原则
- 经济发展需要时间
- 战争消耗资源
- 平衡军事与民生

#### 平衡参数

```python
ECONOMY_BALANCE = {
    "monthly_income": {
        "base": 100,
        "per_city": 20,
        "per_trade_route": 10
    },
    
    "monthly_expense": {
        "per_soldier": 0.1,
        "per_official": 5,
        "per_diplomat": 10
    },
    
    "war_cost": {
        "supply_consumption": 1.5,
        "equipment_wear": 1.2,
        "morale_maintenance": 1.3
    }
}
```

---

## 十、实现建议

### 10.1 优先级排序

#### 第一阶段（核心体验）
1. 自由战术系统
2. 外交策略系统
3. 补给线系统

#### 第二阶段（深度体验）
1. 国策树系统
2. 围城战术系统
3. 战略意图系统

#### 第三阶段（完善体验）
1. 战术协同系统
2. 外交叙事系统
3. AI 决策树

### 10.2 测试策略

#### 单元测试
- 每个系统独立测试
- 边界条件测试
- 异常输入测试

#### 集成测试
- 系统间交互测试
- 月度循环测试
- 长期平衡测试

#### 平衡测试
- AI 行为测试
- 玩家选择测试
- 历史合理性测试

### 10.3 迭代策略

#### 快速原型
- 先实现核心机制
- 快速验证设计
- 收集玩家反馈

#### 渐进优化
- 根据反馈调整
- 逐步增加深度
- 保持系统稳定

---

## 十一、总结

### 核心改进点

1. **自由战术系统**：让玩家能够创造性地表达战术意图
2. **外交策略系统**：让外交成为真正的策略维度
3. **动态补给线**：让后勤成为战略考量
4. **国策树系统**：让玩家有长期战略规划
5. **围城战术**：让攻城战更有深度

### 设计哲学

- **玩家是决策者**：提供选择，不是答案
- **叙事驱动**：所有机制服务于故事
- **风险与回报**：高风险高回报，低风险稳收益
- **历史合理**：符合三国时代背景

### 预期效果

- 玩家有更大的策略自由度
- 游戏有更高的重玩价值
- AI 行为更加智能合理
- 平衡性更加完善

---

**文档版本**: v1.0  
**创建日期**: 2026-07-28  
**作者**: WorkBuddy 游戏设计助手  
**状态**: 提案阶段，待评审
