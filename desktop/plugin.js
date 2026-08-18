import {
  atom,
  cn,
  haptic,
  host,
  PANES_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  Tip,
  useValue
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'agent-hud'
const POLL_MS = 2500
const MAX_PRIMARY = 32
const MAX_DELEGATIONS = 64
const MAX_CHILDREN = 64
const MAX_ACTIVITY = 12
const EMPTY = Object.freeze({
  version: 3,
  generated_at: 0,
  gateway: { running: false, state: 'unknown' },
  counts: { primary: 0, primary_visible: 0, primary_truncated: false, subagents: 0, total: 0 },
  primary: [],
  delegations: []
})

const $snapshot = atom(EMPTY)
const $request = atom({ loading: true, error: '' })
const $selection = atom(null)
let requestGeneration = 0

const color = {
  active: '#61d6a0',
  complete: '#739684',
  danger: '#ff7777',
  finishing: '#8986ff',
  idle: 'var(--ui-text-tertiary)',
  warning: '#d6aa63'
}

const shellStyle = {
  background: 'var(--ui-surface-background)',
  color: 'var(--ui-text-primary)',
  height: '100%',
  minHeight: 0,
  overflow: 'hidden'
}
const headerStyle = {
  alignItems: 'center',
  borderBottom: '1px solid var(--ui-stroke-tertiary)',
  display: 'flex',
  gap: 10,
  padding: '12px 14px'
}
const scrollStyle = {
  height: 'calc(100% - 58px)',
  minHeight: 0,
  overflow: 'auto',
  padding: '10px 12px 18px'
}
const groupStyle = {
  background: 'var(--ui-bg-quinary)',
  border: '1px solid var(--ui-stroke-tertiary)',
  borderRadius: 10,
  marginBottom: 10,
  overflow: 'hidden'
}
const buttonStyle = {
  alignItems: 'flex-start',
  background: 'transparent',
  border: 0,
  color: 'inherit',
  cursor: 'pointer',
  display: 'flex',
  gap: 9,
  padding: '10px 11px',
  textAlign: 'left',
  width: '100%'
}

function safeText(value, limit = 180) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  return text.length <= limit ? text : `${text.slice(0, Math.max(0, limit - 1))}…`
}

function safeNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? Math.max(0, number) : 0
}

function normalizeActivity(value) {
  if (!Array.isArray(value)) return []
  return value.slice(0, MAX_ACTIVITY).map(item => ({
    at: safeNumber(item?.at),
    clock: safeText(item?.clock, 8),
    detail: safeText(item?.detail, 220) || 'invoked',
    kind: safeText(item?.kind, 24) || 'tool',
    tool: safeText(item?.tool, 80) || 'tool'
  }))
}

function normalizeSnapshot(value) {
  if (!value || typeof value !== 'object') return EMPTY
  const primary = Array.isArray(value.primary)
    ? value.primary.slice(0, MAX_PRIMARY).map(agent => ({
      action: safeText(agent?.action, 140),
      activity: normalizeActivity(agent?.activity),
      branch: safeText(agent?.branch, 140),
      goal: safeText(agent?.goal, 140),
      last_activity_at: safeNumber(agent?.last_activity_at),
      project: safeText(agent?.project, 140),
      session_id: safeText(agent?.session_id, 160),
      session_key: safeText(agent?.session_key, 160),
      source: safeText(agent?.source, 80),
      started_at: safeNumber(agent?.started_at),
      state: safeText(agent?.state, 32) || 'running',
      title: safeText(agent?.title, 140) || 'Hermes agent',
      tool_calls: safeNumber(agent?.tool_calls),
      api_calls: safeNumber(agent?.api_calls),
      effort: safeText(agent?.effort, 20)
    }))
    : []
  const delegations = Array.isArray(value.delegations)
    ? value.delegations.slice(0, MAX_DELEGATIONS).map(delegation => ({
      children: Array.isArray(delegation?.children)
        ? delegation.children.slice(0, MAX_CHILDREN).map(child => ({
          action: safeText(child?.action, 140),
          activity: normalizeActivity(child?.activity),
          goal: safeText(child?.goal, 140) || 'Subagent',
          index: Number.isInteger(child?.index) ? child.index : 0,
          last_activity_at: safeNumber(child?.last_activity_at),
          state: safeText(child?.state, 32) || 'running'
        }))
        : [],
      delegation_id: safeText(delegation?.delegation_id, 160),
      goal: safeText(delegation?.goal, 140) || 'Delegated work',
      parent_session_id: safeText(delegation?.parent_session_id, 160),
      progress: delegation?.progress && typeof delegation.progress === 'object' ? {
        completed: safeNumber(delegation.progress.completed),
        failed: safeNumber(delegation.progress.failed),
        finalizing: safeNumber(delegation.progress.finalizing),
        running: safeNumber(delegation.progress.running),
        stalling: safeNumber(delegation.progress.stalling),
        total: safeNumber(delegation.progress.total)
      } : {},
      started_at: safeNumber(delegation?.started_at),
      state: safeText(delegation?.state, 32) || 'running'
    }))
    : []
  const counts = value.counts && typeof value.counts === 'object' ? value.counts : {}
  return {
    version: safeNumber(value.version),
    generated_at: safeNumber(value.generated_at),
    gateway: {
      running: value.gateway?.running === true,
      state: safeText(value.gateway?.state, 64) || 'unknown'
    },
    counts: {
      primary: safeNumber(counts.primary),
      primary_visible: safeNumber(counts.primary_visible),
      primary_truncated: counts.primary_truncated === true,
      subagents: safeNumber(counts.subagents),
      total: safeNumber(counts.total)
    },
    primary,
    delegations
  }
}

function toneForState(state) {
  const value = String(state || '').toLowerCase()
  if (['error', 'failed', 'stalled', 'interrupted'].includes(value)) return 'danger'
  if (value === 'stalling') return 'warning'
  if (value === 'finalizing') return 'finishing'
  if (value === 'completed') return 'complete'
  return value === 'running' ? 'active' : 'idle'
}

function ageText(timestamp) {
  if (!timestamp) return ''
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m ago`
}

function summaryText(counts) {
  const parts = []
  if (counts.primary) parts.push(`${counts.primary} ${counts.primary === 1 ? 'agent' : 'agents'}`)
  if (counts.subagents) parts.push(`${counts.subagents} ${counts.subagents === 1 ? 'subagent' : 'subagents'}`)
  return parts.length ? parts.join(' · ') : 'Hermes idle'
}

function progressText(progress = {}) {
  return [
    [progress.running, 'running'],
    [progress.finalizing, 'finalizing'],
    [progress.stalling, 'stalling'],
    [progress.failed, 'failed'],
    [progress.completed, 'done']
  ].filter(([count]) => count > 0).map(([count, label]) => `${count} ${label}`).join(' · ')
}

function primaryKey(agent, index) {
  return agent.session_id || agent.session_key || `generic:${index}`
}

function identityColor(key) {
  let hash = 2166136261
  for (const character of String(key || '')) {
    hash ^= character.codePointAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return `hsl(${(hash >>> 0) % 360} 62% 66%)`
}

function ownerKeys(agent) {
  return [agent.session_id, agent.session_key].filter(Boolean)
}

function activityGlyph(kind) {
  return { command: '>_', diff: '±', file: '▤', tool: '◇' }[kind] || '◇'
}

function StateDot({ state, size = 8 }) {
  const tone = toneForState(state)
  return jsx('span', {
    'aria-label': state,
    style: {
      background: color[tone],
      borderRadius: '50%',
      display: 'inline-block',
      flex: '0 0 auto',
      height: size,
      marginTop: 5,
      width: size
    }
  })
}

function TechnicalLine({ children }) {
  return jsx('div', {
    style: {
      color: 'var(--ui-text-tertiary)',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 11,
      lineHeight: 1.45,
      marginTop: 3
    },
    children
  })
}

function AgentButton({ agent, identity, onClick }) {
  const detail = [agent.source, agent.effort ? `${agent.effort} effort` : '', agent.project, agent.branch]
    .filter(Boolean).join(' · ')
  return jsxs('button', {
    onClick,
    style: buttonStyle,
    type: 'button',
    children: [
      jsx('span', { 'aria-hidden': true, style: { color: identity, fontSize: 13, marginTop: 1 }, children: '◆' }),
      jsx(StateDot, { state: agent.state }),
      jsxs('span', {
        style: { display: 'block', minWidth: 0 },
        children: [
          jsx('span', { style: { display: 'block', fontSize: 13, fontWeight: 650, lineHeight: 1.35 }, children: agent.title }),
          jsx('span', {
            style: { color: 'var(--ui-text-secondary)', display: 'block', fontSize: 11, lineHeight: 1.45, marginTop: 2 },
            children: [agent.action || agent.state, ageText(agent.last_activity_at)].filter(Boolean).join(' · ')
          }),
          detail ? jsx(TechnicalLine, { children: detail }) : null
        ]
      })
    ]
  })
}

function ChildButton({ child, identity, onClick }) {
  return jsxs('button', {
    onClick,
    style: { ...buttonStyle, borderTop: '1px solid var(--ui-stroke-tertiary)', paddingLeft: 29 },
    type: 'button',
    children: [
      jsx('span', { 'aria-hidden': true, style: { color: identity, fontFamily: 'monospace', fontSize: 13 }, children: '└' }),
      jsx(StateDot, { state: child.state, size: 7 }),
      jsxs('span', {
        style: { display: 'block', minWidth: 0 },
        children: [
          jsx('span', { style: { display: 'block', fontSize: 12, fontWeight: 600, lineHeight: 1.4 }, children: child.goal }),
          jsx('span', {
            style: { color: 'var(--ui-text-secondary)', display: 'block', fontSize: 11, lineHeight: 1.45, marginTop: 2 },
            children: [child.action || child.state, ageText(child.last_activity_at)].filter(Boolean).join(' · ')
          })
        ]
      })
    ]
  })
}

function ActivityView({ selection, snapshot }) {
  let title = ''
  let subtitle = ''
  let activity = []
  if (selection.type === 'primary') {
    const index = snapshot.primary.findIndex((agent, offset) => primaryKey(agent, offset) === selection.key)
    const agent = snapshot.primary[index]
    if (!agent) return null
    title = agent.title
    subtitle = [agent.action || agent.state, ageText(agent.last_activity_at)].filter(Boolean).join(' · ')
    activity = agent.activity
  } else {
    const delegation = snapshot.delegations.find(item => item.delegation_id === selection.delegationId)
    const child = delegation?.children.find(item => item.index === selection.index)
    if (!delegation || !child) return null
    title = child.goal
    subtitle = `${child.action || child.state} · ${progressText(delegation.progress)}`
    activity = child.activity
  }
  return jsxs('div', {
    style: scrollStyle,
    children: [
      jsx('button', {
        onClick: () => $selection.set(null),
        style: { ...buttonStyle, color: 'var(--ui-text-secondary)', fontSize: 11, padding: '2px 0 10px' },
        type: 'button',
        children: '← Current work'
      }),
      jsx('div', { style: { fontSize: 16, fontWeight: 680, lineHeight: 1.35 }, children: `Hermes › ${title}` }),
      subtitle ? jsx('div', { style: { color: 'var(--ui-text-secondary)', fontSize: 11, marginTop: 4 }, children: subtitle }) : null,
      jsx('div', {
        style: { color: 'var(--ui-text-tertiary)', fontSize: 10, fontWeight: 650, letterSpacing: '0.12em', margin: '16px 0 7px', textTransform: 'uppercase' },
        children: 'Recent tool activity'
      }),
      activity.length ? activity.map((item, index) => jsxs('div', {
        style: {
          background: index === 0 ? 'var(--ui-bg-quinary)' : 'transparent',
          borderLeft: `1px solid ${index === 0 ? color.active : 'var(--ui-stroke-tertiary)'}`,
          display: 'flex',
          gap: 10,
          padding: '9px 10px'
        },
        children: [
          jsx('span', { 'aria-hidden': true, style: { color: 'var(--ui-text-secondary)', fontFamily: 'monospace', fontSize: 12, width: 22 }, children: activityGlyph(item.kind) }),
          jsxs('span', {
            style: { display: 'block', minWidth: 0 },
            children: [
              jsx('span', { style: { color: 'var(--ui-text-secondary)', display: 'block', fontFamily: 'monospace', fontSize: 10 }, children: `${item.tool}${item.at ? ` · ${ageText(item.at)}` : item.clock ? ` · ${item.clock}` : ''}` }),
              jsx('span', { style: { display: 'block', fontFamily: 'monospace', fontSize: 12, lineHeight: 1.5, marginTop: 3, overflowWrap: 'anywhere' }, children: item.detail })
            ]
          })
        ]
      }, `${item.tool}:${item.at}:${index}`)) : jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontSize: 12, padding: '12px 0' }, children: 'No recent structured tool calls' }),
      jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontFamily: 'monospace', fontSize: 9, marginTop: 12 }, children: 'Bounded · sanitized · recent first' })
    ]
  })
}

function Overview({ snapshot }) {
  const matched = new Set()
  const groups = snapshot.primary.map((agent, index) => {
    const key = primaryKey(agent, index)
    const keys = ownerKeys(agent)
    const owned = snapshot.delegations.filter(delegation => keys.includes(delegation.parent_session_id))
    owned.forEach(delegation => matched.add(delegation.delegation_id))
    const identity = identityColor(key)
    return jsxs('section', {
      style: groupStyle,
      children: [
        jsx(AgentButton, {
          agent,
          identity,
          onClick: () => {
            haptic('tap')
            $selection.set({ type: 'primary', key })
          }
        }),
        ...owned.flatMap(delegation => [
          jsxs('div', {
            style: { alignItems: 'center', borderTop: '1px solid var(--ui-stroke-tertiary)', color: 'var(--ui-text-tertiary)', display: 'flex', fontSize: 10, gap: 8, justifyContent: 'space-between', padding: '7px 11px 4px 39px' },
            children: [
              jsx('span', { style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: delegation.goal }),
              jsx('span', { style: { flex: '0 0 auto', fontFamily: 'monospace', fontSize: 9 }, children: progressText(delegation.progress) })
            ]
          }, `${delegation.delegation_id}:heading`),
          ...delegation.children.map(child => jsx(ChildButton, {
            child,
            identity,
            onClick: () => {
              haptic('tap')
              $selection.set({ type: 'child', delegationId: delegation.delegation_id, index: child.index })
            }
          }, `${delegation.delegation_id}:${child.index}`))
        ])
      ]
    }, key)
  })
  const unassigned = snapshot.delegations.filter(delegation => !matched.has(delegation.delegation_id))
  return jsxs('div', {
    style: scrollStyle,
    children: [
      jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontSize: 10, fontWeight: 650, letterSpacing: '0.12em', margin: '2px 2px 8px', textTransform: 'uppercase' }, children: 'Primary agents' }),
      groups.length ? groups : jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontSize: 13, padding: '18px 4px' }, children: 'No agents are running' }),
      unassigned.length ? jsxs('div', {
        children: [
          jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontSize: 10, fontWeight: 650, letterSpacing: '0.12em', margin: '16px 2px 8px', textTransform: 'uppercase' }, children: 'Unassigned subagents' }),
          ...unassigned.map(delegation => jsx('section', {
            style: groupStyle,
            children: delegation.children.map(child => jsx(ChildButton, {
              child,
              identity: 'var(--ui-text-tertiary)',
              onClick: () => $selection.set({ type: 'child', delegationId: delegation.delegation_id, index: child.index })
            }, `${delegation.delegation_id}:${child.index}`))
          }, delegation.delegation_id))
        ]
      }) : null,
      jsx('div', { style: { color: 'var(--ui-text-tertiary)', fontFamily: 'monospace', fontSize: 9, margin: '12px 4px 0' }, children: snapshot.generated_at ? `Updated ${ageText(snapshot.generated_at)} · read-only` : 'Waiting for backend…' })
    ]
  })
}

function AgentHudView() {
  const snapshot = useValue($snapshot)
  const request = useValue($request)
  const selection = useValue($selection)
  return jsxs('div', {
    style: shellStyle,
    children: [
      jsxs('header', {
        style: headerStyle,
        children: [
          jsx(StateDot, { state: request.error ? 'failed' : snapshot.gateway.running ? 'running' : 'idle', size: 9 }),
          jsxs('div', {
            style: { flex: 1, minWidth: 0 },
            children: [
              jsx('div', { style: { fontSize: 14, fontWeight: 680 }, children: 'Hermes Agent HUD' }),
              jsx('div', { style: { color: 'var(--ui-text-secondary)', fontFamily: 'monospace', fontSize: 10, marginTop: 2 }, children: request.error || summaryText(snapshot.counts) })
            ]
          }),
          jsx('span', { style: { color: 'var(--ui-text-tertiary)', fontFamily: 'monospace', fontSize: 9 }, children: 'READ-ONLY' })
        ]
      }),
      request.loading && snapshot === EMPTY
        ? jsx('div', { style: { color: 'var(--ui-text-tertiary)', padding: 18 }, children: 'Loading agent activity…' })
        : request.error && snapshot === EMPTY
          ? jsx('div', { style: { color: 'var(--ui-text-secondary)', padding: 18 }, children: 'Agent HUD backend is unavailable. Enable the agent-hud plugin and restart the Hermes backend.' })
          : selection
            ? jsx(ActivityView, { selection, snapshot })
            : jsx(Overview, { snapshot })
    ]
  })
}

function StatusChip() {
  const snapshot = useValue($snapshot)
  const request = useValue($request)
  const label = request.error ? 'HUD unavailable' : summaryText(snapshot.counts)
  return jsx(Tip, {
    label: `Agent HUD · ${label}`,
    children: jsxs('button', {
      className: cn(
        'inline-flex h-full items-center gap-1.5 px-1.5 text-[0.6875rem] tabular-nums transition-colors',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      onClick: () => {
        haptic('tap')
        host.navigate('/agent-hud')
      },
      type: 'button',
      children: [
        jsx(StateDot, { state: request.error ? 'failed' : snapshot.gateway.running ? 'running' : 'idle', size: 6 }),
        jsx('span', { children: label })
      ]
    })
  })
}

async function refresh(ctx, generation) {
  try {
    const value = await ctx.rest('/state', { timeoutMs: 5000 })
    if (generation !== requestGeneration) return
    $snapshot.set(normalizeSnapshot(value))
    $request.set({ loading: false, error: '' })
  } catch {
    if (generation !== requestGeneration) return
    $request.set({ loading: false, error: 'Backend unavailable' })
  }
}

export default {
  id: ID,
  name: 'Hermes Agent HUD',
  description: 'Privacy-safe live operations view for agents and subagents',
  defaultEnabled: false,
  register(ctx) {
    let generation = ++requestGeneration
    let activeProfile = host.state.profile.get()
    const load = () => refresh(ctx, generation)
    $snapshot.set(EMPTY)
    $selection.set(null)
    $request.set({ loading: true, error: '' })
    void load()
    const timer = setInterval(() => void load(), POLL_MS)
    const stopProfile = host.state.profile.listen(profile => {
      if (profile === activeProfile) return
      activeProfile = profile
      generation = ++requestGeneration
      $snapshot.set(EMPTY)
      $selection.set(null)
      $request.set({ loading: true, error: '' })
      void load()
    })
    ctx.onDispose(() => {
      ++requestGeneration
      clearInterval(timer)
      stopProfile()
    })
    ctx.registerMany([
      {
        id: 'pane',
        area: PANES_AREA,
        title: 'Agent HUD',
        data: { placement: 'right', width: '460px' },
        render: () => jsx(AgentHudView, {})
      },
      {
        id: 'page',
        area: ROUTES_AREA,
        title: 'Agent HUD',
        data: { path: '/agent-hud' },
        render: () => jsx(AgentHudView, {})
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        order: 70,
        data: { codicon: 'pulse', label: 'Agent HUD', path: '/agent-hud' }
      },
      {
        id: 'status',
        area: STATUSBAR_AREAS.right,
        order: 115,
        render: () => jsx(StatusChip, {})
      }
    ])
  }
}
