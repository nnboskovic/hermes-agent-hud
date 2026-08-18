export function summaryText(counts = {}) {
  const primary = Math.max(0, Number(counts.primary) || 0)
  const subagents = Math.max(0, Number(counts.subagents) || 0)
  if (primary === 0 && subagents === 0) return 'Hermes idle'
  const parts = []
  if (primary > 0) parts.push(`${primary} ${primary === 1 ? 'agent' : 'agents'}`)
  if (subagents > 0) parts.push(`${subagents} ${subagents === 1 ? 'subagent' : 'subagents'}`)
  return parts.join(' · ')
}

export function toneForState(state = '') {
  const value = String(state).toLowerCase()
  if (['error', 'failed', 'stalled', 'interrupted'].includes(value)) return 'danger'
  if (value === 'stalling') return 'warning'
  if (value === 'finalizing') return 'finishing'
  if (value === 'completed') return 'complete'
  return value === 'running' ? 'active' : 'idle'
}

export function delegationProgressText(progress = {}) {
  const fields = [
    ['running', 'running'],
    ['finalizing', 'finalizing'],
    ['stalling', 'stalling'],
    ['failed', 'failed'],
    ['completed', 'done'],
  ]
  return fields
    .map(([key, label]) => [Math.max(0, Number(progress[key]) || 0), label])
    .filter(([count]) => count > 0)
    .map(([count, label]) => `${count} ${label}`)
    .join(' · ')
}

export function ageText(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0))
  if (value < 60) return `${value}s`
  if (value < 3600) return `${Math.floor(value / 60)}m`
  return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`
}

export function boundedPanelSize(width, height, areaWidth, areaHeight, margin = 18) {
  const availableWidth = Math.max(1, Number(areaWidth) - margin * 2)
  const availableHeight = Math.max(1, Number(areaHeight) - margin * 2)
  return {
    width: Math.max(1, Math.min(Number(width) || 1, availableWidth)),
    height: Math.max(1, Math.min(Number(height) || 1, availableHeight)),
  }
}

export function selectMonitorArea(areas = [], x = 0, y = 0) {
  const candidates = Array.isArray(areas)
    ? areas.filter(area =>
      area && [area.x, area.y, area.width, area.height].every(Number.isFinite),
    )
    : []
  if (!candidates.length) return null
  const pointX = Number(x) || 0
  const pointY = Number(y) || 0
  const containing = candidates.find(area =>
    pointX >= area.x && pointX < area.x + area.width
      && pointY >= area.y && pointY < area.y + area.height,
  )
  if (containing) return containing
  return candidates.reduce((nearest, area) => {
    const nearestX = Math.min(Math.max(pointX, area.x), area.x + area.width)
    const nearestY = Math.min(Math.max(pointY, area.y), area.y + area.height)
    const distance = (pointX - nearestX) ** 2 + (pointY - nearestY) ** 2
    return !nearest || distance < nearest.distance ? { area, distance } : nearest
  }, null).area
}

export function clampPositionToArea(position = {}, size = {}, area = {}) {
  const areaX = Number(area.x) || 0
  const areaY = Number(area.y) || 0
  const areaWidth = Math.max(1, Number(area.width) || 1)
  const areaHeight = Math.max(1, Number(area.height) || 1)
  const width = Math.max(1, Number(size.width) || 1)
  const height = Math.max(1, Number(size.height) || 1)
  const maxX = Math.max(areaX, areaX + areaWidth - width)
  const maxY = Math.max(areaY, areaY + areaHeight - height)
  return {
    x: Math.min(Math.max(Number(position.x) || 0, areaX), maxX),
    y: Math.min(Math.max(Number(position.y) || 0, areaY), maxY),
  }
}

const AGENT_ACCENTS = ['emerald', 'violet', 'cyan', 'amber']
const CURRENT_CHILD_STATES = new Set(['running', 'finalizing', 'stalling'])

export function agentAccent(key = '') {
  let hash = 2166136261
  for (const character of String(key)) {
    hash ^= character.codePointAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return AGENT_ACCENTS[(hash >>> 0) % AGENT_ACCENTS.length]
}

export function primaryVisualKey(agent = {}, index = 0) {
  const authoritative = agent?.session_id || agent?.session_key
  return authoritative ? String(authoritative) : `generic:${Math.max(0, Number(index) || 0)}`
}

export function delegationOwnerKey(snapshot = {}, parentSessionId = '') {
  const primary = Array.isArray(snapshot.primary) ? snapshot.primary : []
  const parent = String(parentSessionId || '')
  const index = primary.findIndex(agent =>
    [agent?.session_id, agent?.session_key].filter(Boolean).map(String).includes(parent),
  )
  return index >= 0 ? primaryVisualKey(primary[index], index) : ''
}

export function agentConstellations(snapshot = {}, limit = 3, childLimit = 3) {
  const primary = Array.isArray(snapshot.primary) ? snapshot.primary : []
  const delegations = Array.isArray(snapshot.delegations) ? snapshot.delegations : []
  const primaryEntries = primary.map((agent, index) => ({
    agent,
    key: primaryVisualKey(agent, index),
  }))
  const owned = new Map()
  for (const entry of primaryEntries) {
    for (const key of [entry.agent?.session_id, entry.agent?.session_key].filter(Boolean)) {
      owned.set(String(key), entry)
    }
  }
  const childrenByOwner = new Map()
  let unassigned = 0
  for (const delegation of delegations) {
    const owner = owned.get(String(delegation?.parent_session_id || ''))
    const currentChildren = (delegation?.children || []).filter(child =>
      CURRENT_CHILD_STATES.has(String(child?.state || '').toLowerCase()),
    )
    if (!owner) {
      unassigned += currentChildren.length
      continue
    }
    const accumulated = childrenByOwner.get(owner.key) || []
    accumulated.push(...currentChildren)
    childrenByOwner.set(owner.key, accumulated)
  }
  const visibleEntries = primaryEntries.slice(0, limit)
  const usedAccents = new Set()
  const accentsByKey = new Map()
  for (const key of visibleEntries.map(entry => entry.key).sort()) {
    const preferred = agentAccent(key)
    const accent = usedAccents.has(preferred)
      ? AGENT_ACCENTS.find(candidate => !usedAccents.has(candidate)) || preferred
      : preferred
    usedAccents.add(accent)
    accentsByKey.set(key, accent)
  }
  const clusters = visibleEntries.map(({ agent, key }) => {
    const children = childrenByOwner.get(key) || []
    return {
      key,
      accent: accentsByKey.get(key),
      state: String(agent?.state || 'idle'),
      children: children.slice(0, childLimit),
      overflowChildren: Math.max(0, children.length - childLimit),
    }
  })
  return {
    clusters,
    unassigned,
    overflowPrimary: Math.max(0, primary.length - limit),
  }
}

export function collapsedPanelWidth(primaryCount) {
  const visible = Math.max(1, Math.min(3, Math.floor(Number(primaryCount) || 0)))
  return 340 + (visible - 1) * 38
}

export function activityGlyph(kind = 'tool') {
  return {
    command: '>_',
    diff: '±',
    file: '▤',
    tool: '◇',
  }[String(kind).toLowerCase()] || '◇'
}
