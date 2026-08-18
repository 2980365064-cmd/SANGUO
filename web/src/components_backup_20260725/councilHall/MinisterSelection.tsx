/**
 * 廷议大臣选择：立绘卡片多选（最多 10 人）。
 */
import React from "react";
import type { Character } from "../../types";
import { Portrait } from "../Portrait";

export function MinisterSelection({
  ministers,
  onSelect,
  onConfirm,
  onCancel,
}: {
  ministers: Character[];
  onSelect: (name: string) => void;
  onConfirm: (selected: string[]) => void;
  onCancel: () => void;
}) {
  const [selected, setSelected] = React.useState<string[]>([]);

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
    <div className="minister-selection ink-frame-panel">
      <div className="minister-selection-wash" />
      <div className="minister-selection-inner">
        <header>
          <h2>选择廷议大臣</h2>
          <p>已选 <strong>{selected.length}</strong> / 10 人</p>
          <button className="close-button" onClick={onCancel}>✕</button>
        </header>
        <div className="minister-selection-layout">
          <section className="minister-roster" aria-label="可参与廷议的大臣">
            <p className="minister-layout-label">群臣名录</p>
            <div className="minister-grid">
              {ministers.map((char) => (
                <button
                  key={char.name}
                  className={selected.includes(char.name) ? "selected" : ""}
                  onClick={() => toggle(char.name)}
                >
                  <Portrait character={char} />
                  <div className="minister-info">
                    <strong>{char.name}</strong>
                    <small>{char.office || char.political_group}</small>
                  </div>
                  {selected.includes(char.name) && <span className="check-mark">✓</span>}
                </button>
              ))}
            </div>
          </section>
          <section className="council-theme-preview" aria-label="本次廷议主题">
            <p className="minister-layout-label">本月议题</p>
            <h3>请诸臣共陈军政利害</h3>
            <p>入席者将围绕你提出的议题，分别陈述立场、可用专长与可能的风险。廷议记录可被收录为待审建议。</p>
            <dl>
              <div><dt>当前步骤</dt><dd>一 · 选定议席</dd></div>
              <div><dt>下一步骤</dt><dd>二 · 陈议录入</dd></div>
            </dl>
          </section>
          <aside className="council-seat-ledger" aria-label="本次入席大臣">
            <p className="minister-layout-label">本次议席</p>
            {selected.length ? <ol>{selected.map((name) => {
              const minister = ministers.find((item) => item.name === name);
              return <li key={name}><strong>{name}</strong><small>{minister?.office || minister?.political_group || '待陈其议'}</small></li>;
            })}</ol> : <p className="council-seat-empty">尚未入席。选择大臣后，方可就本月军政议题陈述利害。</p>}
          </aside>
        </div>
        <footer>
          <button className="secondary" onClick={onCancel}>取消</button>
          <button
            className="primary"
            onClick={() => onConfirm(selected)}
            disabled={selected.length === 0}
          >
            开始廷议 ({selected.length})
          </button>
        </footer>
      </div>
    </div>
  );
}
