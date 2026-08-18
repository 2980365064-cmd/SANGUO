/**
 * 廷议大臣选择：立绘卡片多选（最多 10 人）。
 */
import React from "react";
import type { Character } from "../../types";

const COUNCIL_TOPICS = [
  { id: "military", title: "军政方针", note: "战守进退 · 将略裁断" },
  { id: "expedition", title: "征战方略", note: "出师时机 · 行军部署" },
  { id: "civil", title: "内政民生", note: "屯田仓廪 · 吏治安民" },
  { id: "diplomacy", title: "外交谋略", note: "使节往来 · 合纵连衡" },
  { id: "personnel", title: "人事任免", note: "举贤授职 · 赏罚进退" },
];

export function MinisterSelection({
  ministers,
  onSelect,
  onConfirm,
  onCancel,
}: {
  ministers: Character[];
  onSelect: (name: string) => void;
  onConfirm: (selected: string[], topic: string) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = React.useState<string[]>([]);
  const [topic, setTopic] = React.useState(COUNCIL_TOPICS[0].id);

  const toggle = (name: string) => {
    setSelected((prev) => {
      if (prev.includes(name)) {
        return prev.filter((n) => n !== name);
      }
      if (prev.length >= 10) return prev;
      return [...prev, name];
    });
  };

  return (
    <div className="minister-selection council-scroll-selection">
      <div className="minister-selection-inner council-scroll-inner">
        <header className="council-summons-header">
          <button className="council-return" type="button" onClick={onCancel}>← 返回天下舆图</button>
          <div>
            <small>府 堂 廷 议 · 召 集 群 臣</small>
            <h1>府堂议事</h1>
            <h2>召集入席廷臣</h2>
            <p>本月议政，先点将入席，再定所议之事。<b>已召 {selected.length} / 10 人</b></p>
          </div>
          <span className="council-header-seal" aria-hidden="true">议</span>
        </header>
        <div className="minister-selection-layout">
          <section className="minister-roster" aria-label="可参与廷议的大臣">
            <div className="council-roster-heading"><p className="minister-layout-label">群臣名录</p><span>点选名签，以朱印召入议席</span></div>
            <div className="minister-grid">
              {ministers.map((char) => (
                <button
                  key={char.name}
                  className={selected.includes(char.name) ? "selected" : ""}
                  onClick={() => toggle(char.name)}
                >
                  <span className="minister-seal">{char.name.slice(0, 1)}</span>
                  <div className="minister-info">
                    <strong>{char.name}</strong>
                    <small>{char.office || char.political_group}</small>
                  </div>
                  {selected.includes(char.name) && <span className="check-mark">入席</span>}
                </button>
              ))}
            </div>
          </section>
          <aside className="council-seat-ledger" aria-label="本次入席大臣">
            <p className="minister-layout-label">已选群臣</p>
            {selected.length ? <ol>{selected.map((name) => {
              const minister = ministers.find((item) => item.name === name);
              return <li key={name}><strong>{name}</strong><small>{minister?.office || minister?.political_group || '待陈其议'}</small></li>;
            })}</ol> : <p className="council-seat-empty">尚未入席。选择大臣后，方可就本月军政议题陈述利害。</p>}
          </aside>
          <section className="council-topic-folio" aria-label="本月议题库">
            <div className="council-folio-heading"><p className="minister-layout-label">议程奏牍</p><span>择一事，以询群臣</span></div>
            <div className="council-topic-slips" role="radiogroup" aria-label="选择廷议议题">
              {COUNCIL_TOPICS.map((item, index) => <button key={item.id} type="button" role="radio" aria-checked={topic === item.id} className={topic === item.id ? "selected" : ""} onClick={() => setTopic(item.id)}>
                <i aria-hidden="true">{String(index + 1).padStart(2, "0")}</i><strong>{item.title}</strong><small>{item.note}</small><span aria-hidden="true">议</span>
              </button>)}
            </div>
          </section>
        </div>
        <footer>
          <button className="secondary" onClick={onCancel}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm(selected, COUNCIL_TOPICS.find((item) => item.id === topic)?.title || "")}
            disabled={selected.length === 0 || !topic}
          >
            开始廷议 ({selected.length})
          </button>
        </footer>
      </div>
    </div>
  );
}
