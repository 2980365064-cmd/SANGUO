/**
 * 居中模态遮罩：blur + dim + 点击关闭。
 * 仅在 centered modal 打开时挂载。
 */
import React from "react";
import { usePanel } from "../state/panelStore";

export function PanelBackdrop({ onClose }: { onClose: () => void }) {
  const { state } = usePanel();
  if (state.centered === null) return null;

  return (
    <div
      className="panel-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    />
  );
}
