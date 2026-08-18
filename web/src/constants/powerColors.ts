export const POWER_COLORS: Record<string, string> = {
  liu_bei: "#B46B37",
  cao_cao: "#53687D",
  sun_quan: "#278A91",
  liu_qi: "#C09232",
  liu_zhang: "#A6503D",
  zhang_lu: "#718B4F",
  ma_han: "#805F97",
  gongsun_kang: "#3D82A9",
  shi_xie: "#3E806D",
  none: "#655c4b",
};

export function getPowerColor(powerId: string): string {
  return POWER_COLORS[powerId] || POWER_COLORS["none"]!;
}
