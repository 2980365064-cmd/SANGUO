import { useEffect, useMemo, useState } from 'react';
import { Check, Sparkles } from 'lucide-react';
import { getSuggestions } from '../api';
import { createDirectiveDraft, listDirectiveDrafts, polishDirectiveSections, updateDirectiveDraft, validateDirectiveDraft } from '../api/directiveDrafts';
import { createDirectiveBatch, executeDirectiveBatch, issueDirectiveBatch } from '../api/directiveBatches';
import { GameDialog } from '../components/GameDialog';
import { SceneShell } from '../components/SceneShell';
import { ActionSealButton, AppFrame, PaperPanel, SectionHeading } from '../components/ui';
import { useCurrentBatch, useDrafts, useGameStore } from '../state/gameStore';
import type { DirectiveDraft } from '../types';

type SlotType = 'internal' | 'military' | 'diplomatic' | 'other';
type Suggestion = { id: number; text: string; source: string; status: string };
type SlotValue = { narrative: string; compiled: string; draft?: DirectiveDraft };

const SLOT_DEFINITIONS: Array<{ type: SlotType; label: string }> = [
  { type: 'internal', label: '内政' },
  { type: 'military', label: '军事' },
  { type: 'diplomatic', label: '外交' },
  { type: 'other', label: '其他' },
];

const EMPTY_SLOTS = (): Record<SlotType, SlotValue> => ({
  internal: { narrative: '', compiled: '' },
  military: { narrative: '', compiled: '' },
  diplomatic: { narrative: '', compiled: '' },
  other: { narrative: '', compiled: '' },
});

function compiledText(title: string, narrative: string) {
  const lines = narrative.split('\n').map((line) => line.trim()).filter(Boolean);
  return lines.length ? `【${title.trim() || '未题方略'}】\n${lines.map((line) => `— ${line}`).join('\n')}` : '';
}

/** 一月四槽：建议先归类，文书再润色、下达。 */
export function DirectiveBook() {
  const { state, navigate } = useGameStore();
  const { drafts, setDrafts, addDraft, updateDraft } = useDrafts();
  const { setCurrentBatch } = useCurrentBatch();
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<number[]>([]);
  const [targetSlot, setTargetSlot] = useState<SlotType>('internal');
  const [activeSlot, setActiveSlot] = useState<SlotType>('internal');
  const [slots, setSlots] = useState<Record<SlotType, SlotValue>>(EMPTY_SLOTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmIssue, setConfirmIssue] = useState(false);

  const turn = state.gameState.turn.turn;
  const editableDrafts = useMemo(
    () => drafts.filter((draft) => draft.turn === turn && draft.status !== 'issued'),
    [drafts, turn],
  );

  const loadDesk = async () => {
    setLoading(true); setError(null);
    try {
      const [draftResult, suggestionResult] = await Promise.all([
        listDirectiveDrafts({ turn }),
        getSuggestions(),
      ]);
      setDrafts(draftResult.drafts);
      setSuggestions(suggestionResult.suggestions.filter((item) => item.status !== 'deleted'));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '方略簿暂不可读取。');
    } finally { setLoading(false); }
  };

  useEffect(() => { void loadDesk(); }, [turn]);

  useEffect(() => {
    const next = EMPTY_SLOTS();
    for (const definition of SLOT_DEFINITIONS) {
      const matching = editableDrafts.filter((draft) => draft.directive_type === definition.type);
      const draft = matching[0];
      if (draft) next[definition.type] = {
        narrative: draft.narrative_text,
        compiled: draft.compiled_text,
        draft,
      };
    }
    setSlots(next);
  }, [editableDrafts]);

  const updateSlot = (type: SlotType, field: 'narrative', value: string) => {
    setSlots((current) => ({ ...current, [type]: { ...current[type], [field]: value } }));
    setMessage(null);
  };

  const toggleSuggestion = (id: number) => setSelectedSuggestionIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  const appendSuggestions = () => {
    const selected = suggestions.filter((item) => selectedSuggestionIds.includes(item.id));
    if (!selected.length) { setError('请先在建议库勾选至少一条建议。'); return; }
    const addition = selected.map((item) => `［${item.source || '建议'}］${item.text}`).join('\n');
    setSlots((current) => ({
      ...current,
      [targetSlot]: {
        ...current[targetSlot],
        narrative: [current[targetSlot].narrative.trim(), addition].filter(Boolean).join('\n'),
      },
    }));
    setActiveSlot(targetSlot); setSelectedSuggestionIds([]); setError(null); setMessage(`已归入${SLOT_DEFINITIONS.find((item) => item.type === targetSlot)?.label}方略，保存后进入草案。`);
  };

  const persistSlot = async (type: SlotType): Promise<DirectiveDraft | null> => {
    const slot = slots[type];
    if (!slot.narrative.trim()) return null;
    const label = SLOT_DEFINITIONS.find((item) => item.type === type)?.label || type;
    const payload = {
      title: `${label}方略`,
      narrative_text: slot.narrative.trim(),
      compiled_text: slot.compiled || compiledText(`${label}方略`, slot.narrative),
    };
    const result = slot.draft
      ? await updateDirectiveDraft(slot.draft.id, payload)
      : await createDirectiveDraft({ source_type: 'manual', directive_type: type, duration_months: 1, priority: 50, constraints_json: '[]', risks_json: '[]', ...payload });
    if (slot.draft) updateDraft(result.draft.id, result.draft); else addDraft(result.draft);
    setSlots((current) => ({ ...current, [type]: { ...current[type], draft: result.draft, compiled: result.draft.compiled_text } }));
    return result.draft;
  };

  const polishDocument = async () => {
    const sections = Object.fromEntries(SLOT_DEFINITIONS.map((item) => [item.type, slots[item.type].narrative.trim()]));
    if (!Object.values(sections).some(Boolean)) { setError('先写入正文或从建议库归入建议，再润色文书。'); return; }
    setSaving(true); setError(null);
    try {
      const result = await polishDirectiveSections(sections);
      setSlots((current) => Object.fromEntries(SLOT_DEFINITIONS.map((item) => [item.type, {
        ...current[item.type], narrative: result.sections[item.type] || current[item.type].narrative, compiled: '',
      }])) as Record<SlotType, SlotValue>);
      setMessage('四节军令已润色为三国军府文风；请检查后下达。');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '文书润色失败，请重试。'); }
    finally { setSaving(false); }
  };

  const issueCommand = async () => {
    setSaving(true); setError(null);
    try {
      const saved = (await Promise.all(SLOT_DEFINITIONS.map((definition) => persistSlot(definition.type)))).filter((draft): draft is DirectiveDraft => Boolean(draft));
      if (!saved.length) { setError('至少写入一节军令后才能下达。'); return; }
      const invalid: string[] = [];
      for (const draft of saved) {
        const result = await validateDirectiveDraft(draft.id);
        if (!result.valid) invalid.push(...result.errors);
      }
      if (invalid.length) { setError(invalid.join('；')); return; }
      const decreeText = saved.map((draft) => draft.compiled_text || compiledText(draft.title, draft.narrative_text)).join('\n\n');
      const created = await createDirectiveBatch({
        batch_title: `${state.gameState.turn.year}年${state.gameState.turn.period}月军府军令`,
        draft_ids: saved.map((draft) => draft.id), decree_text: decreeText,
      });
      const issued = await issueDirectiveBatch(created.batch.id);
      setCurrentBatch(issued.batch);
      setMessage('军令已下达，正在推演内政、军事、外交与月度核销……');
      await executeDirectiveBatch(issued.batch.id, (event) => { if (event.message) setMessage(event.message); });
      navigate('report');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '下达军令失败，请重试。'); }
    finally { setSaving(false); setConfirmIssue(false); }
  };

  return <SceneShell scene="directive">
    <AppFrame className="directive-book" title="本月军府方略簿" eyebrow="建议归类 · 草拟 · 下达" back={<ActionSealButton priority="ghost" onClick={() => navigate('map')}>返回天下舆图</ActionSealButton>}>
      {error && <PaperPanel className="directive-desk-notice" tone="floating" role="alert">{error}</PaperPanel>}
      {message && <PaperPanel className="directive-desk-notice" tone="floating">{message}</PaperPanel>}
      <div className="directive-desk-layout">
        <aside className="directive-suggestion-library"><PaperPanel tone="floating">
          <SectionHeading index="建议">建议库</SectionHeading>
          <p>勾选建议后归入一类方略，不会直接产生行动。</p>
          <div className="suggestion-assign">归入<select value={targetSlot} onChange={(event) => setTargetSlot(event.target.value as SlotType)}>{SLOT_DEFINITIONS.map((item) => <option key={item.type} value={item.type}>{item.label}</option>)}</select><ActionSealButton priority="secondary" onClick={appendSuggestions}>归入方略</ActionSealButton></div>
          <div className="directive-suggestion-list">{loading ? <p>正在调阅建议……</p> : suggestions.length ? suggestions.map((item) => <label key={item.id}><input type="checkbox" checked={selectedSuggestionIds.includes(item.id)} onChange={() => toggleSuggestion(item.id)} /><span>{item.text}<small>{item.source || '未署来源'}</small></span></label>) : <p>本月尚无建议。可先在廷议、密谈或地图中形成建议。</p>}</div>
        </PaperPanel></aside>
        <main className="directive-sections-column">
          {SLOT_DEFINITIONS.map((definition) => {
            const slot = slots[definition.type];
            const active = activeSlot === definition.type;
            return <div key={definition.type} className={`directive-section ${active ? 'is-active' : ''}`} onClick={() => setActiveSlot(definition.type)}>
              <div className="directive-section-label"><strong>{definition.label}</strong></div>
              <textarea
                aria-label={`${definition.label}方略正文`}
                value={slot.narrative}
                onFocus={() => setActiveSlot(definition.type)}
                onChange={(event) => updateSlot(definition.type, 'narrative', event.target.value)}
                placeholder={`在此写入${definition.label}要点，或从建议库归入。`}
                rows={4}
              />
            </div>;
          })}
          <div className="directive-bottom-bar">
            <ActionSealButton priority="secondary" onClick={() => void polishDocument()} disabled={saving}><Sparkles /> 润色文书</ActionSealButton>
            <ActionSealButton priority="primary" onClick={() => setConfirmIssue(true)} disabled={saving}><Check /> 下达军令</ActionSealButton>
          </div>
        </main>
      </div>
      <GameDialog open={confirmIssue} onOpenChange={setConfirmIssue} title="下达本月军令" description="军令会统一校验、进入既有分阶段推演，并写入本月执行记录；此操作不可撤回。" tone="decree" bgAsset="var(--archive-scene-decree-review-v2)"><div className="decree-confirmation-actions"><ActionSealButton priority="ghost" onClick={() => setConfirmIssue(false)} disabled={saving}>返回修改</ActionSealButton><ActionSealButton priority="primary" onClick={() => void issueCommand()} disabled={saving}>{saving ? '推演中…' : '确认下达军令'}</ActionSealButton></div></GameDialog>
    </AppFrame>
  </SceneShell>;
}
