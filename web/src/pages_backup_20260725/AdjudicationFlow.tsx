import { SceneShell } from '../components/SceneShell';
import { useGameStore, useCurrentBatch } from '../state/gameStore';
import { useState, useEffect, useRef } from 'react';
import { submitBatchDecision } from '../api';

interface ExecutionEvent {
  type: string;
  phase?: string;
  phase_label?: string;
  draft_id?: number;
  message?: string;
  data?: any;
}

/**
 * 分阶段推演 - P0 执行反馈页面
 * 流式显示执行，支持阶段检查点裁断
 */
export function AdjudicationFlow() {
  const { state, navigate } = useGameStore();
  const { currentBatch } = useCurrentBatch();
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>('');
  const [awaitingDecision, setAwaitingDecision] = useState<any>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeToken, setResumeToken] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!currentBatch || (currentBatch.status !== 'issued' && resumeToken === 0)) return;

    // 开始执行
    setIsExecuting(true);
    setError(null);
    setEvents([]);
    setCurrentPhase('');

    // 创建 SSE 连接
    const eventSource = new EventSource(
      `/api/directive-batches/${currentBatch.id}/execute`
    );
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as ExecutionEvent;
        setEvents((prev) => [...prev, data]);

        // 更新当前阶段
        if (data.type === 'phase_start' && data.phase) {
          setCurrentPhase(data.phase_label || data.phase);
        }

        // 检查决策点
        if (data.type === 'decision_point') {
          setAwaitingDecision(data);
          eventSource.close();
          setIsExecuting(false);
        }

        // 检查完成
        if (data.type === 'batch_complete') {
          eventSource.close();
          setIsExecuting(false);
        }

        // 检查错误
        if (data.type === 'error') {
          setError(data.message || '执行出错');
          eventSource.close();
          setIsExecuting(false);
        }
      } catch (err) {
        console.error('解析 SSE 事件失败:', err);
      }
    };

    eventSource.onerror = () => {
      setError('SSE 连接错误');
      eventSource.close();
      setIsExecuting(false);
    };

    return () => {
      eventSource.close();
    };
  }, [currentBatch?.id, currentBatch?.status, resumeToken]);

  const handleDecision = async (choice: string) => {
    if (!currentBatch || !awaitingDecision) return;

    try {
      await submitBatchDecision(currentBatch.id, Number(awaitingDecision.draft_id), choice);
      setAwaitingDecision(null);
      setResumeToken((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : '决策提交失败');
    }
  };

  const getPhaseLabel = (phase: string): string => {
    const labels: Record<string, string> = {
      internal: '内政',
      military: '军事',
      diplomatic: '外交',
      civilian: '民生',
      settlement: '核销',
    };
    return labels[phase] || phase;
  };

  const getEventColor = (type: string): string => {
    switch (type) {
      case 'phase_start':
        return '#4a90e2';
      case 'phase_complete':
        return '#7ed321';
      case 'draft_executed':
        return '#50e3c2';
      case 'decision_point':
        return '#f5a623';
      case 'error':
        return '#d0021b';
      case 'batch_complete':
        return '#9013fe';
      default:
        return '#9b9b9b';
    }
  };

  return (
    <SceneShell scene="adjudication">
      <div className="adjudication-flow">
        <header>
          <h1>分阶段推演</h1>
          <p>批次: {currentBatch?.batch_title}</p>
          <p>当前阶段: {currentPhase ? getPhaseLabel(currentPhase) : '准备中'}</p>
          {isExecuting && <p className="executing-indicator">执行中...</p>}
        </header>

        {error && (
          <div className="error-message">
            <p>错误: {error}</p>
          </div>
        )}

        <div className="execution-log">
          <h2>执行日志 ({events.length})</h2>
          <div className="event-list">
            {events.map((event, idx) => (
              <div
                key={idx}
                className={`event-item event-${event.type}`}
                style={{ borderLeftColor: getEventColor(event.type) }}
              >
                <div className="event-header">
                  <span className="event-type">{event.type}</span>
                  {event.phase && (
                    <span className="event-phase">
                      {getPhaseLabel(event.phase)}
                    </span>
                  )}
                  {event.draft_id !== undefined && (
                    <span className="event-draft">草案 #{event.draft_id}</span>
                  )}
                </div>
                <div className="event-message">
                  {event.message || JSON.stringify(event.data)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {awaitingDecision && (
          <div className="decision-dialog">
            <h2>需要决策</h2>
            <p>{awaitingDecision.message}</p>
            <div className="decision-options">
              {awaitingDecision.data?.options?.map((option: any, idx: number) => (
                <button
                  key={idx}
                  onClick={() => handleDecision(option.label || option)}
                  className="decision-option"
                >
                  {option.label || option}
                  {option.description && (
                    <span className="option-description">{option.description}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {!awaitingDecision && !isExecuting && events.length > 0 && (
          <div className="execution-actions">
            <button onClick={() => navigate('report')} className="primary">
              查看每月总计
            </button>
            <button onClick={() => navigate('directive')}>
              返回方略簿
            </button>
          </div>
        )}

      </div>
    </SceneShell>
  );
}
