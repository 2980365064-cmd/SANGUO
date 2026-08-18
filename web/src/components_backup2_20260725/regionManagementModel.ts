import type { RegionDetail } from "../types";

export const REGION_LEDGER_ITEMS = [
  {
    key: "grain_stock",
    label: "粮仓余量",
    short: "可撑补给与灾荒",
    description: "郡县当前可动用存粮。数值越高，越能支撑驻军补给、赈灾与临时借粮。",
  },
  {
    key: "grain_output",
    label: "月度粮产",
    short: "每月新增粮秣",
    description: "本地每月可产出的粮秣规模。粮产高，长期出兵和屯驻的压力更小。",
  },
  {
    key: "fortification",
    label: "城防韧性",
    short: "守城抗压能力",
    description: "城墙、关隘、守备器械与防务组织的综合水平。数值越高，越不容易被围攻速破。",
  },
  {
    key: "commerce_tax",
    label: "商税潜力",
    short: "钱粮收入来源",
    description: "市易、渡口、商旅与税课带来的收入潜力。数值越高，越适合支撑投资和军费。",
  },
  {
    key: "transport",
    label: "道路粮道",
    short: "调粮行军效率",
    description: "道路、渡口和粮道的通达程度。数值越高，军队调动和后方转运越顺畅。",
  },
  {
    key: "gentry_resistance",
    label: "士族阻力",
    short: "治理掣肘风险",
    description: "地方豪强、士族与旧吏对政令的抵触程度。数值越高，投资、征发和治理越容易受阻。",
  },
];

export const REGION_INVESTMENTS = [
  {
    category: "屯田粮仓",
    hint: "增粮与存粮",
    description: "组织屯田、修仓、清点粮簿，提高月度粮产和粮仓缓冲。适合前线长期驻军或准备出兵前使用。",
  },
  {
    category: "城防守备",
    hint: "加固城防",
    description: "修城、备械、整顿守卒，提高城防韧性。适合边境、要冲或刚经历战事的郡县。",
  },
  {
    category: "军备练兵",
    hint: "训练驻军",
    description: "整训驻军、补充军械、统一号令，提高驻军训练与临战执行。适合准备守城或反攻前使用。",
  },
  {
    category: "水军船政",
    hint: "水路战备",
    description: "修船、练水军、整治津渡，提高水路机动与江河作战准备。适合江陵、江夏等水网地区。",
  },
  {
    category: "道路粮道",
    hint: "通路转运",
    description: "修路、疏通渡口、设粮站，提高道路粮道。适合补给吃紧、要频繁调兵的区域。",
  },
  {
    category: "民政市易",
    hint: "稳民与税课",
    description: "安抚民户、恢复市集、整顿税课，提高商税潜力并改善民心。适合动乱或财政吃紧时使用。",
  },
];

export function fiscalNumber(detail: RegionDetail | null, key: string) {
  const raw = detail?.fiscal?.[key];
  return typeof raw === "number" ? raw : Number(raw || 0);
}
