import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';

/** Accessible, reusable paper dialog for confirmations and contextual details. */
export function GameDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  tone = 'default',
  presentation = 'modal',
  bgAsset,
  className,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  tone?: 'default' | 'danger' | 'decree';
  /** 地图地方档案不遮断舆图，其余确认与说明仍使用受焦点保护的模态层。 */
  presentation?: 'modal' | 'map-drawer';
  /** Optional background asset CSS variable, e.g. 'var(--ink-bg-city)'. */
  bgAsset?: string;
  /** Optional world-specific surface marker; keeps scene materials scoped to their artifact. */
  className?: string;
}) {
  const surfaceStyle: CSSProperties | undefined = bgAsset
    ? {
        ['--dialog-bg' as string]: bgAsset,
        ...(presentation === 'modal' ? {
          backgroundImage: `linear-gradient(rgba(247,242,231,.35) 0%, rgba(247,242,231,.88) 6%, rgba(247,242,231,.90) 94%, rgba(247,242,231,.40) 100%), ${bgAsset}`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        } : {}),
      }
    : undefined;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={presentation !== 'map-drawer'}>
      <Dialog.Portal>
        {presentation === 'modal' && <Dialog.Overlay className="game-dialog-overlay" />}
        <Dialog.Content className={`game-dialog-surface game-dialog-${tone} game-dialog-${presentation}${className ? ` ${className}` : ''}`} style={surfaceStyle}>
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
