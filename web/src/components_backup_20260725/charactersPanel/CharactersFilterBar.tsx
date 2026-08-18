/**
 * 人物筛选栏：势力/州/文武/属性排序。
 */
import React from "react";

export type FilterState = {
  scope: "liu_bei" | "all";
  province: string | null;
  role: "civil" | "military" | null;
  sortBy: string | null;
};

const PROVINCES = ["荆州", "益州", "扬州", "交州", "凉州", "并州", "冀州", "青州", "兖州", "豫州", "徐州", "司隶"];
const ATTRIBUTES = ["武力", "统率", "智略", "政治", "外交", "魅力"];

export function CharactersFilterBar({
  filter,
  onChange,
}: {
  filter: FilterState;
  onChange: (filter: FilterState) => void;
}) {
  return (
    <aside className="characters-filter">
      <section>
        <h4>势力</h4>
        <div className="filter-buttons">
          <button
            className={filter.scope === "liu_bei" ? "active" : ""}
            onClick={() => onChange({ ...filter, scope: "liu_bei" })}
          >
            本势力
          </button>
          <button
            className={filter.scope === "all" ? "active" : ""}
            onClick={() => onChange({ ...filter, scope: "all" })}
          >
            全天下
          </button>
        </div>
      </section>

      <section>
        <h4>州</h4>
        <select
          value={filter.province || ""}
          onChange={(e) => onChange({ ...filter, province: e.target.value || null })}
        >
          <option value="">全部</option>
          {PROVINCES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
      </section>

      <section>
        <h4>类型</h4>
        <div className="filter-buttons">
          <button
            className={filter.role === "civil" ? "active" : ""}
            onClick={() => onChange({ ...filter, role: filter.role === "civil" ? null : "civil" })}
          >
            文臣
          </button>
          <button
            className={filter.role === "military" ? "active" : ""}
            onClick={() => onChange({ ...filter, role: filter.role === "military" ? null : "military" })}
          >
            武将
          </button>
        </div>
      </section>

      <section>
        <h4>排序</h4>
        <select
          value={filter.sortBy || ""}
          onChange={(e) => onChange({ ...filter, sortBy: e.target.value || null })}
        >
          <option value="">默认</option>
          {ATTRIBUTES.map((attr) => (
            <option key={attr} value={attr}>{attr}</option>
          ))}
        </select>
      </section>
    </aside>
  );
}
