import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

/** Accessible, reusable paper dialog for confirmations and contextual details. */
export function GameDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  tone = 'default',
  presentation = 'modal',
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  tone?: 'default' | 'danger' | 'decree';
  /** 地图地方档案不遮断舆图，其余确认与说明仍使用受焦点保护的模态层。 */
  presentation?: 'modal' | 'map-drawer';
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={presentation !== 'map-drawer'}>
      <Dialog.Portal>
        {presentation === 'modal' && <Dialog.Overlay className="game-dialog-overlay" />}
        <Dialog.Content className={`game-dialog-surface game-dialog-${tone} game-dialog-${presentation}`}>
          <header>
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              {description && <Dialog.Description>{description}</Dialog.Description>}
            </div>
            <Dialog.Close aria-label="关闭"><X /></Dialog.Close>
          </header>
          <div className="game-dialog-content">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
