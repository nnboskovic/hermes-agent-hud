import assert from 'node:assert/strict'

import {
  activityGlyph,
  agentAccent,
  agentConstellations,
  boundedPanelSize,
  collapsedPanelWidth,
  clampPositionToArea,
  delegationOwnerKey,
  delegationProgressText,
  primaryVisualKey,
  selectMonitorArea,
  summaryText,
  toneForState,
} from '../ui_model.js'

assert.equal(summaryText({ primary: 0, subagents: 0, total: 0 }), 'Hermes idle')
assert.equal(summaryText({ primary: 1, subagents: 0, total: 1 }), '1 agent')
assert.equal(summaryText({ primary: 1, subagents: 2, total: 3 }), '1 agent · 2 subagents')
assert.equal(summaryText({ primary: 2, subagents: 1, total: 3 }), '2 agents · 1 subagent')
assert.equal(toneForState('running'), 'active')
assert.equal(toneForState('finalizing'), 'finishing')
assert.equal(toneForState('stalling'), 'warning')
assert.equal(toneForState('error'), 'danger')
assert.equal(toneForState('completed'), 'complete')
assert.equal(
  delegationProgressText({ running: 2, finalizing: 1, stalling: 0, completed: 3, failed: 0 }),
  '2 running · 1 finalizing · 3 done',
)
assert.equal(
  delegationProgressText({ running: 0, finalizing: 0, stalling: 1, completed: 0, failed: 1 }),
  '1 stalling · 1 failed',
)
assert.deepEqual(boundedPanelSize(520, 600, 1280, 800), { width: 520, height: 600 })
assert.deepEqual(boundedPanelSize(520, 600, 480, 400), { width: 444, height: 364 })

const constellation = agentConstellations({
  primary: [
    { session_id: 'primary-alpha', title: 'Alpha' },
    { session_id: 'primary-beta', title: 'Beta' },
    { session_id: 'primary-gamma', title: 'Gamma' },
  ],
  delegations: [
    {
      parent_session_id: 'primary-alpha',
      children: [
        { index: 0, state: 'running' },
        { index: 1, state: 'finalizing' },
        { index: 2, state: 'completed' },
      ],
    },
    {
      parent_session_id: 'primary-beta',
      children: [{ index: 0, state: 'stalling' }],
    },
    {
      parent_session_id: 'missing-primary',
      children: [{ index: 0, state: 'running' }],
    },
  ],
})
assert.deepEqual(
  constellation.clusters.map(cluster => [cluster.key, cluster.children.length]),
  [['primary-alpha', 2], ['primary-beta', 1], ['primary-gamma', 0]],
)
assert.equal(constellation.unassigned, 1)
assert.equal(constellation.overflowPrimary, 0)
assert.equal('connections' in constellation, false)
assert.equal(new Set(constellation.clusters.map(cluster => cluster.accent)).size, 3)
assert.equal(agentAccent('primary-alpha'), agentAccent('primary-alpha'))

const reorderedConstellation = agentConstellations({
  primary: [
    { session_id: 'primary-gamma', title: 'Gamma' },
    { session_id: 'primary-beta', title: 'Beta' },
    { session_id: 'primary-alpha', title: 'Alpha' },
  ],
  delegations: [],
})
assert.deepEqual(
  Object.fromEntries(reorderedConstellation.clusters.map(cluster => [cluster.key, cluster.accent])),
  Object.fromEntries(constellation.clusters.map(cluster => [cluster.key, cluster.accent])),
)

const collisionMap = order => Object.fromEntries(
  agentConstellations({ primary: order.map(session_id => ({ session_id })) })
    .clusters.map(cluster => [cluster.key, cluster.accent]),
)
const collisionForward = collisionMap(['agent-0', 'agent-4'])
const collisionReverse = collisionMap(['agent-4', 'agent-0'])
assert.equal(agentAccent('agent-0'), agentAccent('agent-4'))
assert.equal(collisionForward['agent-0'], collisionReverse['agent-0'])
assert.equal(collisionForward['agent-4'], collisionReverse['agent-4'])
assert.notEqual(collisionForward['agent-0'], collisionForward['agent-4'])

const genericConstellation = agentConstellations({
  primary: [
    { title: 'Hermes agent' },
    { title: 'Hermes agent' },
    { title: 'Hermes agent' },
  ],
})
assert.deepEqual(
  genericConstellation.clusters.map(cluster => cluster.key),
  ['generic:0', 'generic:1', 'generic:2'],
)
assert.equal(new Set(genericConstellation.clusters.map(cluster => cluster.accent)).size, 3)
assert.equal(primaryVisualKey({ title: 'Hermes agent' }, 2), 'generic:2')

const sessionKeyConstellation = agentConstellations({
  primary: [{ session_key: 'discord:primary-key', title: 'Session key owner' }],
  delegations: [{
    parent_session_id: 'discord:primary-key',
    children: [{ index: 0, state: 'running' }],
  }],
})
assert.equal(sessionKeyConstellation.clusters[0].children.length, 1)
assert.equal(
  delegationOwnerKey(
    { primary: [{ session_key: 'discord:primary-key', title: 'Session key owner' }] },
    'discord:primary-key',
  ),
  'discord:primary-key',
)
assert.equal(delegationOwnerKey({ primary: [{ title: 'Hermes agent' }] }, 'missing'), '')

const overflowConstellation = agentConstellations({
  primary: [{ session_id: 'overflow-owner', title: 'Overflow owner' }],
  delegations: [{
    parent_session_id: 'overflow-owner',
    children: [0, 1, 2, 3].map(index => ({ index, state: 'running' })),
  }],
})
assert.equal(overflowConstellation.clusters[0].children.length, 3)
assert.equal(overflowConstellation.clusters[0].overflowChildren, 1)
assert.equal(collapsedPanelWidth(1), 340)
assert.equal(collapsedPanelWidth(2), 378)
assert.equal(collapsedPanelWidth(3), 416)
assert.equal(collapsedPanelWidth(12), 416)
assert.equal(activityGlyph('command'), '>_')
assert.equal(activityGlyph('diff'), '±')
assert.equal(activityGlyph('file'), '▤')
assert.equal(activityGlyph('tool'), '◇')

const horizontalMonitors = [
  { x: 0, y: 0, width: 1920, height: 1080 },
  { x: 1920, y: 0, width: 1920, height: 1080 },
]
assert.deepEqual(selectMonitorArea(horizontalMonitors, 800, 300), horizontalMonitors[0])
assert.deepEqual(selectMonitorArea(horizontalMonitors, 2800, 300), horizontalMonitors[1])
assert.deepEqual(
  clampPositionToArea({ x: 200, y: 80 }, { width: 520, height: 600 }, horizontalMonitors[0]),
  { x: 200, y: 80 },
)
assert.deepEqual(
  clampPositionToArea({ x: 3700, y: 1000 }, { width: 520, height: 600 }, horizontalMonitors[1]),
  { x: 3320, y: 480 },
)
const negativeMonitor = { x: -1920, y: 0, width: 1920, height: 1080 }
assert.deepEqual(selectMonitorArea([negativeMonitor, horizontalMonitors[0]], -500, 300), negativeMonitor)
assert.deepEqual(
  clampPositionToArea({ x: -2500, y: -100 }, { width: 520, height: 600 }, negativeMonitor),
  { x: -1920, y: 0 },
)

console.log('ui model ok')
