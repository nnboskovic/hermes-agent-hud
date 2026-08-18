import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import { renderToStaticMarkup } from 'react-dom/server'
import { jsx, jsxs } from 'react/jsx-runtime'

const source = fs.readFileSync(new URL('../desktop/plugin.js', import.meta.url), 'utf8')
assert.doesNotMatch(source, /from\s+['"]\.\//)
assert.doesNotMatch(source, /\b(?:pause|cancel|kill|retry)\b/i)
assert.match(source, /ctx\.rest\(['"]\/state['"]/)
assert.match(source, /defaultEnabled:\s*false/)
assert.match(source, /function identityColor\(/)
assert.doesNotMatch(source, /colors\[index\s*%/)

const contributions = []
const disposers = []
const restCalls = []
const state = {
  version: 3,
  generated_at: 1_800_000_000,
  gateway: { running: true, state: 'running' },
  counts: { primary: 2, primary_visible: 2, primary_truncated: false, subagents: 1, total: 3 },
  primary: [
    {
      session_id: 'alpha',
      title: 'Build plugin',
      state: 'running',
      action: 'terminal',
      activity: [{ kind: 'command', tool: 'terminal', detail: 'python -m unittest', at: 1_799_999_998 }]
    },
    { session_id: 'beta', title: 'Review privacy', state: 'finalizing', action: 'read_file', activity: [] }
  ],
  delegations: [
    {
      delegation_id: 'deleg-1',
      parent_session_id: 'alpha',
      goal: 'Independent review',
      progress: { total: 1, running: 1, finalizing: 0, stalling: 0, completed: 0, failed: 0 },
      children: [{ index: 0, goal: 'Check package', state: 'running', action: 'read_file', activity: [] }]
    },
    {
      delegation_id: 'deleg-unassigned',
      parent_session_id: 'unmatched-parent',
      goal: 'Unmatched work stays neutral',
      progress: { total: 1, running: 1, finalizing: 0, stalling: 0, completed: 0, failed: 0 },
      children: [{ index: 0, goal: 'Inspect neutral work', state: 'running', action: 'search', activity: [] }]
    }
  ]
}

function atom(initial) {
  let value = initial
  const listeners = new Set()
  return {
    get: () => value,
    set: next => {
      value = next
      for (const listener of listeners) listener(next)
    },
    listen: listener => {
      listeners.add(listener)
      listener(value)
      return () => listeners.delete(listener)
    }
  }
}

const host = {
  navigate: () => {},
  notify: () => {},
  state: { gateway: atom('connected'), profile: atom('default') }
}
const sdkExports = {
  atom,
  cn: (...parts) => parts.filter(Boolean).join(' '),
  haptic: () => {},
  host,
  PANES_AREA: 'panes',
  ROUTES_AREA: 'routes',
  SIDEBAR_NAV_AREA: 'sidebar.nav',
  STATUSBAR_AREAS: { right: 'statusBar.right' },
  Tip: function Tip({ children }) { return jsx('span', { children }) },
  useValue: value => value.get()
}
const jsxExports = { jsx, jsxs }
const context = vm.createContext({
  clearInterval,
  console,
  setInterval,
  setTimeout
})

function synthetic(exports) {
  return new vm.SyntheticModule(Object.keys(exports), function setExports() {
    for (const [name, value] of Object.entries(exports)) this.setExport(name, value)
  }, { context })
}

const module = new vm.SourceTextModule(source, { context })
await module.link(specifier => {
  if (specifier === '@hermes/plugin-sdk') return synthetic(sdkExports)
  if (specifier === 'react/jsx-runtime') return synthetic(jsxExports)
  throw new Error(`Unsupported import in plugin: ${specifier}`)
})
await module.evaluate()

const plugin = module.namespace.default
assert.equal(plugin.id, 'agent-hud')
assert.equal(plugin.defaultEnabled, false)
plugin.register({
  onDispose: disposer => disposers.push(disposer),
  register: contribution => {
    contributions.push(contribution)
    return () => {}
  },
  registerMany: items => {
    contributions.push(...items)
    return () => {}
  },
  rest: async (path, options) => {
    restCalls.push([path, options])
    return state
  },
  storage: { get: (_key, fallback) => fallback, set: () => {}, remove: () => {} }
})
await new Promise(resolve => setTimeout(resolve, 0))

assert.deepEqual(
  new Set(contributions.map(item => item.area)),
  new Set(['panes', 'routes', 'sidebar.nav', 'statusBar.right'])
)
assert.equal(restCalls[0][0], '/state')
assert.ok(Number(restCalls[0][1].timeoutMs) > 0)
host.state.profile.set('other')
await new Promise(resolve => setTimeout(resolve, 0))
assert.equal(restCalls.length, 2)
const renderWarnings = []
const originalError = console.error
console.error = (...parts) => renderWarnings.push(parts.join(' '))
try {
  for (const contribution of contributions.filter(item => item.render)) {
    const rendered = contribution.render()
    assert.ok(rendered)
    const markup = renderToStaticMarkup(rendered)
    assert.ok(markup.length > 0)
  }
} finally {
  console.error = originalError
}
assert.deepEqual(renderWarnings, [])
for (const dispose of disposers) dispose()

console.log('desktop plugin contract ok')
