/**
 * 统一面板壳：header + close button + ink-frame 边框。
 * 用于居中模态面板（DialogueModal, ApiConfigModal 等）。
 */
import React from "react";
import { GameDialog } from "./GameDialog";

interface PanelRootProps {
  title?: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

export function PanelRoot({ title, subtitle, onClose, children, className = "" }: PanelRootProps) {
  return (
    <GameDialog open onOpenChange={(open) => { if (!open) onClose(); }} title={title || "档案"} description={subtitle} tone="default">
      <div className={`panel-root-content ${className}`}>{children}</div>
    </GameDialog>
  );
}
