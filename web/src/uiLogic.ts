import type { TimelineItem, Turn } from "./types";

export const GAME_ENTRANCES = ["朝议", "军令", "任事", "外交", "国策", "家族", "史册", "府堂议事", "人物"] as const;
export type GameEntrance = typeof GAME_ENTRANCES[number];
export const RESOURCE_METRICS = ["军资", "粮秣", "民望", "名分", "军心", "士族支持"] as const;
export const COMMAND_DOCK_ITEMS = [
  ...GAME_ENTRANCES.map((key) => ({ key, dock: "right" as const })),
  { key: "API 配置", dock: "right" as const },
  { key: "月末推演", dock: "right" as const },
] as const;

export type FutureMonthSlot = {
  key: string;
  year: number;
  month: number;
  label: string;
  events: TimelineItem[];
};

const STAGE_SCENES: Record<string, { label: string; asset: string; position: string }> = {
  流亡军: { label: "夏口军营", asset: "/底图.jpg", position: "center 72%" },
  荆州立足: { label: "荆州治所", asset: "/底图.jpg", position: "center 58%" },
  益州治蜀: { label: "成都军府", asset: "/底图.jpg", position: "left 68%" },
  汉中王: { label: "汉中王府", asset: "/底图.jpg", position: "center 42%" },
  称帝后: { label: "蜀汉宫城", asset: "/底图.jpg", position: "right 62%" },
};

export function getStageScene(stage: string) {
  return STAGE_SCENES[stage] || STAGE_SCENES["流亡军"];
}

export function timelineStatusLabel(status: string) {
  return ({
    scheduled: "史势将至",
    eligible: "时机已至",
    adapted: "已改写",
    resolved: "已发生",
    superseded: "变体发生",
    expired: "已失效",
  } as Record<string, string>)[status] || status;
}

function parseTimelineWindow(window: string) {
  const match = window.match(/(\d{3,4})\s*年\s*(\d{1,2})\s*月/);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) };
}

export function buildFutureMonthLine(turn: Pick<Turn, "year" | "period">, timeline: TimelineItem[]): FutureMonthSlot[] {
  const slots = Array.from({ length: 12 }, (_, index) => {
    const zeroBased = turn.period - 1 + index;
    const year = turn.year + Math.floor(zeroBased / 12);
    const month = zeroBased % 12 + 1;
    return { key: `${year}-${month}`, year, month, label: `${year}.${month}`, events: [] as TimelineItem[] };
  });
  const byKey = new Map(slots.map((slot) => [slot.key, slot]));
  const fallback = slots[0];
  timeline.forEach((event) => {
    const parsed = parseTimelineWindow(event.window);
    const slot = parsed ? byKey.get(`${parsed.year}-${parsed.month}`) : fallback;
    if (slot) slot.events.push(event);
  });
  return slots;
}
