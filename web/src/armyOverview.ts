import type { Army, Power } from './types';

export type ArmySort = 'manpower' | 'risk' | 'station';
export type ArmyRiskFilter = 'all' | 'urgent' | 'watch' | 'order';

export type ArmyPowerGroup = { id: string; name: string; armies: Army[]; manpower: number; riskCount: number };

const normalized = (value: string | undefined | null) => (value || '').trim().toLocaleLowerCase();

export function armyRisk(army: Army): { level: 'urgent' | 'watch' | 'steady'; label: string } {
  if (army.supply < 35 || army.morale < 35 || army.fatigue >= 70) return { level: 'urgent', label: '军情紧急' };
  if (army.supply < 55 || army.morale < 55 || army.fatigue >= 50) return { level: 'watch', label: '军情可虑' };
  return { level: 'steady', label: '军情安定' };
}

export function groupArmiesByPower(armies: Army[], powers: Power[]): ArmyPowerGroup[] {
  const names = new Map(powers.map((power) => [power.id, power.name]));
  const groups = new Map<string, ArmyPowerGroup>();
  armies.forEach((army) => {
    const id = army.owner_power || 'unknown';
    const group = groups.get(id) || { id, name: names.get(id) || army.owner_power || '未录势力', armies: [], manpower: 0, riskCount: 0 };
    group.armies.push(army);
    group.manpower += Number(army.manpower || 0);
    if (armyRisk(army).level !== 'steady') group.riskCount += 1;
    groups.set(id, group);
  });
  return [...groups.values()].sort((left, right) => right.manpower - left.manpower || left.name.localeCompare(right.name, 'zh-CN'));
}

export function filterAndSortArmies(armies: Army[], query: string, sort: ArmySort): Army[] {
  const needle = normalized(query);
  return armies.filter((army) => !needle || [army.name, army.commander, army.station_node, army.troop_type].some((value) => normalized(value).includes(needle)))
    .sort((left, right) => {
      if (sort === 'risk') {
        const riskRank = { urgent: 2, watch: 1, steady: 0 } as const;
        return riskRank[armyRisk(right).level] - riskRank[armyRisk(left).level] || right.manpower - left.manpower;
      }
      if (sort === 'station') return (left.station_node || '').localeCompare(right.station_node || '', 'zh-CN') || right.manpower - left.manpower;
      return right.manpower - left.manpower || left.name.localeCompare(right.name, 'zh-CN');
    });
}

export function filterArmiesByRisk(armies: Army[], filter: ArmyRiskFilter): Army[] {
  if (filter === 'all') return armies;
  if (filter === 'order') return armies.filter((army) => Boolean(army.current_order));
  return armies.filter((army) => armyRisk(army).level === filter);
}

export function groupArmiesByStation(armies: Army[]) {
  const groups = new Map<string, { id: string; armies: Army[]; manpower: number; riskCount: number }>();
  armies.forEach((army) => {
    const id = army.station_node || 'unrecorded';
    const group = groups.get(id) || { id, armies: [], manpower: 0, riskCount: 0 };
    group.armies.push(army);
    group.manpower += Number(army.manpower || 0);
    if (armyRisk(army).level !== 'steady') group.riskCount += 1;
    groups.set(id, group);
  });
  return [...groups.values()].sort((left, right) => right.manpower - left.manpower || left.id.localeCompare(right.id, 'zh-CN'));
}
