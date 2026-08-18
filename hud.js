#!/usr/bin/gjs -m

import Gdk from 'gi://Gdk?version=3.0'
import Gio from 'gi://Gio'
import GLib from 'gi://GLib'
import Gtk from 'gi://Gtk?version=3.0'
import Pango from 'gi://Pango'
import AppIndicator from 'gi://AyatanaAppIndicator3?version=0.1'

import {
  activityGlyph,
  ageText,
  agentAccent,
  agentConstellations,
  boundedPanelSize,
  clampPositionToArea,
  collapsedPanelWidth,
  delegationOwnerKey,
  delegationProgressText,
  primaryVisualKey,
  summaryText,
  toneForState,
} from './ui_model.js'

const APPLICATION_ID = GLib.getenv('HERMES_AGENT_HUD_APP_ID') || 'com.hermes.AgentHud'
const REFRESH_MS = 1000
const TONES = ['idle', 'active', 'finishing', 'warning', 'danger', 'complete']
const CSS = `
@keyframes hud-pulse {
  0% { opacity: 0.58; }
  50% { opacity: 1; }
  100% { opacity: 0.58; }
}
window.agent-hud { background: transparent; }
.hud-shell {
  background-image: linear-gradient(to bottom right, rgba(19,21,29,0.985), rgba(8,10,15,0.985));
  border: 1px solid rgba(255,255,255,0.105);
  border-radius: 14px;
  box-shadow: 0 16px 42px rgba(0,0,0,0.52), inset 0 1px rgba(255,255,255,0.045);
  color: #f7f8f8;
  font-family: Inter, Cantarell, sans-serif;
}
.hud-header { background: transparent; padding: 2px 4px 2px 7px; }
.hud-header-main { background: transparent; padding: 6px 5px; }
.hud-header-main:hover { background: rgba(255,255,255,0.04); border-radius: 10px; }
.hud-minimize { background: transparent; border: 0; color: #626873; font-size: 16px; padding: 5px 9px; }
.hud-minimize:hover { background: rgba(255,255,255,0.055); color: #d0d6e0; }
.hud-constellations { margin-right: 8px; }
.hud-constellation { margin-right: 5px; }
.hud-agent-core { font-size: 17px; }
.hud-agent-child { font-size: 12px; color: #66707e; }
.hud-agent-branch { font-family: "DejaVu Sans Mono", monospace; font-size: 11px; opacity: 0.34; }
.hud-agent-packet { font-size: 14px; color: #f7f8f8; }
.hud-child-overflow { color: #7d8490; font-family: "DejaVu Sans Mono", monospace; font-size: 9px; }
.hud-agent-core.active, .hud-dot.active { animation: hud-pulse 2400ms ease-in-out infinite; }
.hud-agent-child.active { color: #61d6a0; }
.hud-agent-child.finishing { color: #86a8ff; }
.hud-agent-child.warning { color: #d6aa63; }
.hud-overflow-bead { color: #7d8490; font-family: "DejaVu Sans Mono", monospace; font-size: 10px; margin-left: 2px; }
.accent-emerald { color: #61d6a0; }
.accent-violet { color: #8986ff; }
.accent-cyan { color: #5ebad1; }
.accent-amber { color: #d6aa63; }
.accent-neutral, .hud-neutral-identity { color: #737b87; }
.hud-title-stack { margin-right: 5px; }
.hud-brand { color: #f7f8f8; font-weight: 600; font-size: 14px; letter-spacing: 0.1px; }
.hud-summary { color: #9aa1ad; font-family: "DejaVu Sans Mono", monospace; font-size: 11px; margin-top: 1px; }
.hud-dot { font-size: 14px; margin-left: 7px; color: #59606b; }
.hud-dot.active { color: #61d6a0; }
.hud-dot.finishing { color: #86a8ff; }
.hud-dot.warning { color: #d6aa63; }
.hud-dot.danger { color: #ff7777; }
.hud-chevron { color: #858c97; font-size: 13px; margin-left: 8px; }
.hud-details { border-top: 1px solid rgba(255,255,255,0.065); padding: 8px 10px 10px; }
.hud-section { color: #8b929d; font-size: 10px; font-weight: 600; letter-spacing: 1.25px; margin: 10px 6px 7px; }
.hud-agent-group { background: rgba(255,255,255,0.018); border: 1px solid rgba(255,255,255,0.04); border-radius: 9px; padding: 3px; margin: 0 0 6px; }
.hud-row { border-radius: 6px; padding: 9px 8px; background: transparent; border: 0; }
.hud-row:hover { background: rgba(255,255,255,0.045); }
.hud-child-row { margin-left: 13px; padding: 7px 8px; }
.hud-identity { font-size: 14px; margin-right: 7px; }
.hud-branch { color: #4e5561; font-family: "DejaVu Sans Mono", monospace; font-size: 13px; margin-right: 6px; }
.hud-row-title { color: #f3f4f6; font-size: 13px; font-weight: 600; letter-spacing: 0.1px; }
.hud-row-meta { color: #b3b9c3; font-size: 11px; font-weight: 500; margin-top: 3px; }
.hud-row-dot { font-size: 11px; margin-right: 6px; color: #626873; }
.hud-row-dot.active { color: #61d6a0; }
.hud-row-dot.finishing { color: #86a8ff; }
.hud-row-dot.warning { color: #d6aa63; }
.hud-row-dot.danger { color: #ff7777; }
.hud-row-dot.complete { color: #536b61; }
.hud-group { color: #aab0ba; font-size: 10px; margin: 7px 7px 2px 39px; }
.hud-group-title { color: #aab0ba; font-size: 10px; font-weight: 500; }
.hud-group-progress { color: #858c97; font-family: "DejaVu Sans Mono", monospace; font-size: 9px; margin-left: 9px; }
.hud-row-detail { color: #8f97a3; font-family: "DejaVu Sans Mono", monospace; font-size: 10px; margin-top: 3px; }
.hud-back { background: transparent; border: 0; color: #a2a9b4; font-size: 10px; padding: 5px 4px; }
.hud-back:hover { color: #f0f2f5; }
.hud-breadcrumb { color: #f1f2f4; font-size: 15px; font-weight: 600; margin: 5px 5px 3px; }
.hud-breadcrumb.accent-emerald { color: #61d6a0; }
.hud-breadcrumb.accent-violet { color: #8986ff; }
.hud-breadcrumb.accent-cyan { color: #5ebad1; }
.hud-breadcrumb.accent-amber { color: #d6aa63; }
.hud-breadcrumb.accent-neutral { color: #a0a6b0; }
.hud-activity-subtitle { color: #9097a3; font-size: 10px; margin: 0 5px 7px; }
.hud-activity-row { border-left: 1px solid #343a45; padding: 8px 9px 8px 11px; background: transparent; margin: 0 0 2px 9px; }
.hud-activity-row.recent { background: rgba(255,255,255,0.025); border-radius: 0 6px 6px 0; }
.hud-activity-row.accent-emerald { border-left-color: #356f57; }
.hud-activity-row.accent-violet { border-left-color: #5956a6; }
.hud-activity-row.accent-cyan { border-left-color: #356b78; }
.hud-activity-row.accent-amber { border-left-color: #77613b; }
.hud-activity-row.accent-neutral { border-left-color: #454b55; }
.hud-activity-glyph { min-width: 24px; font-family: "DejaVu Sans Mono", monospace; font-size: 13px; margin-right: 8px; }
.hud-activity-tool { color: #a4abb6; font-family: "DejaVu Sans Mono", monospace; font-size: 10px; }
.hud-activity-detail { color: #e0e3e8; font-family: "DejaVu Sans Mono", monospace; font-size: 12px; margin-top: 3px; }
.hud-log-button { background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.055); border-radius: 6px; color: #bec4cd; font-size: 10px; margin-top: 8px; }
.hud-footer { color: #7d8591; font-family: "DejaVu Sans Mono", monospace; font-size: 9px; margin: 9px 6px 2px; }
`

function statePath() {
  const configured = GLib.getenv('HERMES_AGENT_HUD_STATE')
  if (configured) return configured
  const cache = GLib.getenv('XDG_CACHE_HOME') || GLib.build_filenamev([GLib.get_home_dir(), '.cache'])
  return GLib.build_filenamev([cache, 'hermes-agent-hud', 'state.json'])
}

function positionPath() {
  const configured = GLib.getenv('HERMES_AGENT_HUD_POSITION')
  if (configured) return configured
  const config = GLib.getenv('XDG_CONFIG_HOME') || GLib.build_filenamev([GLib.get_home_dir(), '.config'])
  return GLib.build_filenamev([config, 'hermes-agent-hud', 'position.json'])
}

function decode(contents) {
  return new TextDecoder('utf-8').decode(contents)
}

function loadSnapshot(path) {
  try {
    const file = Gio.File.new_for_path(path)
    const [, contents] = file.load_contents(null)
    const value = JSON.parse(decode(contents))
    return value && typeof value === 'object' ? value : null
  } catch (_) {
    return null
  }
}

function loadPosition(path) {
  const value = loadSnapshot(path)
  const x = Number(value?.x)
  const y = Number(value?.y)
  return Number.isFinite(x) && Number.isFinite(y)
    ? { x: Math.round(x), y: Math.round(y) }
    : null
}

function savePosition(path, position) {
  try {
    const parent = GLib.path_get_dirname(path)
    GLib.mkdir_with_parents(parent, 0o700)
    const file = Gio.File.new_for_path(path)
    file.replace_contents(
      new TextEncoder().encode(JSON.stringify(position)),
      null,
      false,
      Gio.FileCreateFlags.PRIVATE,
      null,
    )
  } catch (_) {}
}

function overallTone(snapshot) {
  const states = []
  for (const agent of snapshot?.primary || []) states.push(agent.state)
  for (const delegation of snapshot?.delegations || []) {
    states.push(delegation.state)
    for (const child of delegation.children || []) states.push(child.state)
  }
  const tones = states.map(toneForState)
  for (const tone of ['danger', 'warning', 'finishing', 'active']) {
    if (tones.includes(tone)) return tone
  }
  return 'idle'
}

function applyTone(widget, tone) {
  const context = widget.get_style_context()
  for (const name of TONES) context.remove_class(name)
  context.add_class(tone)
}

function indicatorIconForTone(tone) {
  return {
    danger: 'dialog-error-symbolic',
    warning: 'dialog-warning-symbolic',
    finishing: 'emblem-synchronizing-symbolic',
    active: 'media-record-symbolic',
  }[tone] || 'utilities-system-monitor-symbolic'
}

function elapsedMeta(startedAt, action, lastActivityAt, now) {
  const parts = []
  if (action) parts.push(action)
  if (startedAt) parts.push(ageText(now - startedAt))
  if (lastActivityAt) parts.push(`active ${ageText(now - lastActivityAt)} ago`)
  return parts.join(' · ')
}

function titleCase(value) {
  const text = String(value || '').trim()
  return text ? text[0].toUpperCase() + text.slice(1) : ''
}

function primaryDetail(agent) {
  const parts = []
  if (agent.source) parts.push(titleCase(agent.source))
  if (agent.effort) parts.push(`${agent.effort} effort`)
  if (Number(agent.api_calls) > 0) parts.push(`${agent.api_calls} API`)
  if (Number(agent.tool_calls) > 0) parts.push(`${agent.tool_calls} tools`)
  if (agent.project) parts.push(agent.project)
  if (agent.branch) parts.push(agent.branch)
  return parts.join(' · ')
}

class AgentHud {
  constructor(application) {
    this.application = application
    this.expanded = false
    this.selection = null
    this.snapshot = null
    this.path = statePath()
    this.positionFile = positionPath()
    this.savedPosition = loadPosition(this.positionFile)
    this.dragState = null
    this.clusterAccents = new Map()
    this.monitor = null
    this.indicator = null
    this.window = new Gtk.ApplicationWindow({
      application,
      decorated: false,
      resizable: true,
      skip_pager_hint: true,
      skip_taskbar_hint: true,
      type_hint: Gdk.WindowTypeHint.UTILITY,
      title: 'Hermes Agent HUD',
    })
    this.window.get_style_context().add_class('agent-hud')
    this.window.set_keep_above(true)
    this.window.set_accept_focus(false)
    this.window.set_app_paintable(true)
    const screen = this.window.get_screen()
    const visual = screen?.get_rgba_visual()
    if (visual) this.window.set_visual(visual)

    this.shell = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
    this.shell.get_style_context().add_class('hud-shell')
    this.window.add(this.shell)

    this.header = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
    this.header.get_style_context().add_class('hud-header')
    this.dragArea = new Gtk.EventBox({ visible_window: false, hexpand: true })
    this.dragArea.get_style_context().add_class('hud-header-main')
    this.dragArea.set_tooltip_text('Click to expand · drag to move')
    this.headerBox = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
    this.constellations = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
    this.constellations.get_style_context().add_class('hud-constellations')
    this.titleStack = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, hexpand: true })
    this.titleStack.get_style_context().add_class('hud-title-stack')
    this.brand = new Gtk.Label({ label: 'Hermes', xalign: 0 })
    this.brand.get_style_context().add_class('hud-brand')
    this.summary = new Gtk.Label({ label: 'Hermes idle', xalign: 0 })
    this.summary.get_style_context().add_class('hud-summary')
    this.titleStack.pack_start(this.brand, false, false, 0)
    this.titleStack.pack_start(this.summary, false, false, 0)
    this.dot = new Gtk.Label({ label: '●' })
    this.dot.get_style_context().add_class('hud-dot')
    this.chevron = new Gtk.Label({ label: '▾' })
    this.chevron.get_style_context().add_class('hud-chevron')
    this.headerBox.pack_start(this.constellations, false, false, 0)
    this.headerBox.pack_start(this.titleStack, true, true, 0)
    this.headerBox.pack_end(this.chevron, false, false, 0)
    this.headerBox.pack_end(this.dot, false, false, 0)
    this.dragArea.add(this.headerBox)
    this.header.pack_start(this.dragArea, true, true, 0)
    this.minimizeButton = new Gtk.Button({ label: '—', relief: Gtk.ReliefStyle.NONE })
    this.minimizeButton.get_style_context().add_class('hud-minimize')
    this.minimizeButton.set_tooltip_text('Minimize to notification bar')
    this.minimizeButton.connect('clicked', () => this.minimize())
    this.header.pack_end(this.minimizeButton, false, false, 0)
    this.shell.pack_start(this.header, false, false, 0)
    this.installDrag()

    this.detailsFrame = new Gtk.ScrolledWindow({
      hscrollbar_policy: Gtk.PolicyType.NEVER,
      vscrollbar_policy: Gtk.PolicyType.AUTOMATIC,
      shadow_type: Gtk.ShadowType.NONE,
    })
    this.detailsFrame.get_style_context().add_class('hud-details')
    this.detailsFrame.set_propagate_natural_height(true)
    this.detailsFrame.set_max_content_height(535)
    this.details = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
    this.detailsFrame.add(this.details)
    this.detailsReveal = new Gtk.Revealer({
      transition_type: Gtk.RevealerTransitionType.CROSSFADE,
      transition_duration: 150,
      reveal_child: false,
    })
    this.detailsReveal.add(this.detailsFrame)
    this.shell.pack_start(this.detailsReveal, false, false, 0)

    this.window.connect('delete-event', () => {
      this.minimize()
      return true
    })
    this.window.connect('map-event', () => {
      this.position()
      return false
    })

    this.installCss()
    this.installTray()
    this.watchState()
    this.refresh()
    GLib.timeout_add(GLib.PRIORITY_DEFAULT, REFRESH_MS, () => {
      this.refresh()
      return GLib.SOURCE_CONTINUE
    })
  }

  installCss() {
    const provider = new Gtk.CssProvider()
    provider.load_from_data(new TextEncoder().encode(CSS))
    Gtk.StyleContext.add_provider_for_screen(
      Gdk.Screen.get_default(),
      provider,
      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
  }

  constellationWidget(cluster) {
    const fixed = new Gtk.Fixed()
    fixed.get_style_context().add_class('hud-constellation')
    fixed.set_size_request(38, 30)
    const positions = [[4, 2], [29, 3], [29, 20]]
    const branches = [['╲', 8, 5], ['╱', 23, 5], ['╲', 23, 17]]
    branches.slice(0, cluster.children.length).forEach(([glyph, x, y]) => {
      const branch = new Gtk.Label({ label: glyph })
      branch.get_style_context().add_class('hud-agent-branch')
      branch.get_style_context().add_class(`accent-${cluster.accent}`)
      fixed.put(branch, x, y)
    })
    const core = new Gtk.Label({ label: '●' })
    core.get_style_context().add_class('hud-agent-core')
    core.get_style_context().add_class(`accent-${cluster.accent}`)
    applyTone(core, toneForState(cluster.state))
    fixed.put(core, 12, 6)
    cluster.children.forEach((child, index) => {
      const [x, y] = positions[index]
      const childDot = new Gtk.Label({ label: '•' })
      childDot.get_style_context().add_class('hud-agent-child')
      applyTone(childDot, toneForState(child.state))
      fixed.put(childDot, x, y)
    })
    if (cluster.children.length) {
      const packet = new Gtk.Label({ label: '·' })
      packet.get_style_context().add_class('hud-agent-packet')
      fixed.put(packet, 22, 9)
    }
    if (cluster.overflowChildren > 0) {
      const overflow = new Gtk.Label({ label: `+${cluster.overflowChildren}` })
      overflow.get_style_context().add_class('hud-child-overflow')
      fixed.put(overflow, 0, 19)
    }
    const childCount = cluster.children.length + cluster.overflowChildren
    fixed.set_tooltip_text(
      childCount
        ? `Primary agent · ${childCount} active subagent${childCount === 1 ? '' : 's'}`
        : 'Primary agent',
    )
    return fixed
  }

  renderConstellations() {
    for (const child of this.constellations.get_children()) this.constellations.remove(child)
    const model = agentConstellations(this.snapshot)
    this.clusterAccents = new Map(model.clusters.map(cluster => [cluster.key, cluster.accent]))
    for (const cluster of model.clusters) {
      this.constellations.pack_start(this.constellationWidget(cluster), false, false, 0)
    }
    const overflow = model.overflowPrimary + (model.unassigned > 0 ? 1 : 0)
    if (overflow > 0) {
      const bead = new Gtk.Label({ label: `+${overflow}` })
      bead.get_style_context().add_class('hud-overflow-bead')
      bead.set_tooltip_text(
        model.unassigned > 0
          ? 'Additional or unassigned active work'
          : 'Additional primary agents',
      )
      this.constellations.pack_start(bead, false, false, 0)
    }
    if (!model.clusters.length) {
      const idle = new Gtk.Label({ label: '○' })
      idle.get_style_context().add_class('hud-agent-core')
      this.constellations.pack_start(idle, false, false, 0)
    }
    this.constellations.show_all()
  }

  accentForAgent(key) {
    return this.clusterAccents.get(String(key || '')) || agentAccent(key)
  }

  installDrag() {
    this.dragArea.add_events(
      Gdk.EventMask.BUTTON_PRESS_MASK |
      Gdk.EventMask.BUTTON_RELEASE_MASK |
      Gdk.EventMask.POINTER_MOTION_MASK,
    )
    this.dragArea.connect('button-press-event', (_widget, event) => {
      const [, button] = event.get_button()
      if (button !== 1) return false
      const [, rootX, rootY] = event.get_root_coords()
      const [windowX, windowY] = this.window.get_position()
      this.dragState = { rootX, rootY, windowX, windowY, moved: false }
      return true
    })
    this.dragArea.connect('motion-notify-event', (_widget, event) => {
      if (!this.dragState) return false
      const [, rootX, rootY] = event.get_root_coords()
      const deltaX = rootX - this.dragState.rootX
      const deltaY = rootY - this.dragState.rootY
      if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) this.dragState.moved = true
      if (this.dragState.moved) {
        this.window.move(this.dragState.windowX + deltaX, this.dragState.windowY + deltaY)
      }
      return true
    })
    this.dragArea.connect('button-release-event', (_widget, event) => {
      const [, button] = event.get_button()
      if (button !== 1 || !this.dragState) return false
      const moved = this.dragState.moved
      this.dragState = null
      if (moved) {
        const [x, y] = this.window.get_position()
        this.savedPosition = { x, y }
        this.position()
        savePosition(this.positionFile, this.savedPosition)
      } else {
        this.toggle()
      }
      return true
    })
  }

  installTray() {
    if (GLib.getenv('HERMES_AGENT_HUD_DISABLE_TRAY') === '1') return
    this.indicator = AppIndicator.Indicator.new(
      'hermes-agent-hud',
      'utilities-system-monitor-symbolic',
      AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )
    this.indicator.set_title('Hermes Agent HUD')
    const menu = new Gtk.Menu()
    const showItem = new Gtk.MenuItem({ label: 'Show Hermes Agent HUD' })
    showItem.connect('activate', () => this.showWindow())
    menu.append(showItem)
    menu.show_all()
    this.indicator.set_menu(menu)
    this.indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)
  }

  minimize() {
    this.window.hide()
    this.indicator?.set_status(AppIndicator.IndicatorStatus.ACTIVE)
  }

  showWindow() {
    this.window.show_all()
    this.detailsFrame.set_visible(this.expanded)
    this.detailsReveal.set_reveal_child(this.expanded)
    this.indicator?.set_status(AppIndicator.IndicatorStatus.PASSIVE)
    this.resizeToContent()
    this.position()
  }

  watchState() {
    try {
      const parent = Gio.File.new_for_path(GLib.path_get_dirname(this.path))
      this.monitor = parent.monitor_directory(Gio.FileMonitorFlags.NONE, null)
      this.monitor.connect('changed', () => {
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
          this.refresh()
          return GLib.SOURCE_REMOVE
        })
      })
    } catch (_) {
      this.monitor = null
    }
  }

  toggle() {
    if (this.expanded) {
      this.expanded = false
      this.selection = null
    } else {
      this.expanded = true
    }
    this.chevron.set_text(this.expanded ? '▴' : '▾')
    this.renderDetails()
    this.detailsFrame.set_visible(this.expanded)
    this.detailsReveal.set_reveal_child(this.expanded)
    this.resizeToContent()
  }

  workArea(position = null, width = 0, height = 0) {
    const display = Gdk.Display.get_default()
    if (!display) return null
    let monitor = null
    if (position && typeof display.get_monitor_at_point === 'function') {
      const pointX = Math.round(Number(position.x) + Math.max(1, Number(width) || 1) / 2)
      const pointY = Math.round(Number(position.y) + Math.max(1, Number(height) || 1) / 2)
      monitor = display.get_monitor_at_point(pointX, pointY)
    }
    const gdkWindow = this.window.get_window()
    if (!monitor && gdkWindow && typeof display.get_monitor_at_window === 'function') {
      monitor = display.get_monitor_at_window(gdkWindow)
    }
    monitor ||= display.get_primary_monitor() || display.get_monitor(0)
    return monitor?.get_workarea() || null
  }

  resizeToContent() {
    const primaryCount = Number(this.snapshot?.counts?.primary || this.snapshot?.primary?.length || 0)
    const desiredWidth = this.selection
      ? 680
      : this.expanded
      ? 560
      : collapsedPanelWidth(primaryCount)
    const [, currentHeight] = this.window.get_size()
    const area = this.workArea(this.savedPosition, desiredWidth, currentHeight)
    const width = area
      ? boundedPanelSize(desiredWidth, 600, area.width, area.height).width
      : desiredWidth
    this.window.set_size_request(width, -1)
    this.window.queue_resize()
    GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
      const [, naturalHeight] = this.shell.get_preferred_height_for_width(width)
      const height = area
        ? boundedPanelSize(width, naturalHeight, area.width, area.height).height
        : Math.min(Math.max(naturalHeight, 1), 600)
      this.window.resize(width, height)
      this.position(width, height)
      return GLib.SOURCE_REMOVE
    })
  }

  refresh() {
    const next = loadSnapshot(this.path)
    if (next) this.snapshot = next
    const counts = this.snapshot?.counts || { primary: 0, subagents: 0, total: 0 }
    this.summary.set_text(summaryText(counts))
    this.renderConstellations()
    const tone = overallTone(this.snapshot)
    applyTone(this.dot, tone)
    try {
      this.indicator?.set_icon_full(indicatorIconForTone(tone), `Hermes Agent HUD · ${tone}`)
    } catch (_) {}
    if (this.expanded) this.renderDetails()
  }

  clearDetails() {
    for (const child of this.details.get_children()) this.details.remove(child)
  }

  section(text) {
    const label = new Gtk.Label({ label: text.toUpperCase(), xalign: 0 })
    label.get_style_context().add_class('hud-section')
    this.details.pack_start(label, false, false, 0)
  }

  row({
    title,
    meta,
    detail = '',
    state = 'running',
    accent = 'cyan',
    child = false,
    neutral = false,
    onActivate = null,
    parent = this.details,
  }) {
    const button = new Gtk.Button({ relief: Gtk.ReliefStyle.NONE })
    button.get_style_context().add_class('hud-row')
    if (child) button.get_style_context().add_class('hud-child-row')
    button.set_sensitive(Boolean(onActivate))
    const box = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
    if (child) {
      const branch = new Gtk.Label({ label: '└', valign: Gtk.Align.START })
      branch.get_style_context().add_class('hud-branch')
      box.pack_start(branch, false, false, 0)
    }
    const identity = new Gtk.Label({
      label: neutral ? '○' : child ? '•' : '◆',
      valign: Gtk.Align.START,
    })
    identity.get_style_context().add_class('hud-identity')
    identity.get_style_context().add_class(neutral ? 'hud-neutral-identity' : `accent-${accent}`)
    const dot = new Gtk.Label({ label: '•', valign: Gtk.Align.START })
    dot.get_style_context().add_class('hud-row-dot')
    applyTone(dot, toneForState(state))
    const text = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, hexpand: true })
    const titleLabel = new Gtk.Label({ label: title || 'Hermes agent', xalign: 0 })
    titleLabel.set_ellipsize(Pango.EllipsizeMode.END)
    titleLabel.set_max_width_chars(48)
    titleLabel.get_style_context().add_class('hud-row-title')
    const metaLabel = new Gtk.Label({ label: meta || state, xalign: 0 })
    metaLabel.set_ellipsize(Pango.EllipsizeMode.END)
    metaLabel.set_max_width_chars(58)
    metaLabel.get_style_context().add_class('hud-row-meta')
    text.pack_start(titleLabel, false, false, 0)
    text.pack_start(metaLabel, false, false, 0)
    if (detail) {
      const detailLabel = new Gtk.Label({ label: detail, xalign: 0 })
      detailLabel.set_ellipsize(Pango.EllipsizeMode.END)
      detailLabel.set_max_width_chars(64)
      detailLabel.get_style_context().add_class('hud-row-detail')
      text.pack_start(detailLabel, false, false, 0)
    }
    box.pack_start(identity, false, false, 0)
    box.pack_start(dot, false, false, 0)
    box.pack_start(text, true, true, 0)
    button.add(box)
    if (onActivate) {
      button.set_tooltip_text('Inspect recent tool activity')
      button.connect('clicked', onActivate)
    }
    parent.pack_start(button, false, false, 0)
  }

  selectActivity(selection) {
    this.selection = selection
    this.expanded = true
    this.chevron.set_text('▴')
    this.detailsReveal.set_reveal_child(false)
    this.renderDetails()
    this.detailsFrame.set_visible(true)
    this.detailsReveal.set_reveal_child(true)
    this.resizeToContent()
  }

  resolveSelection() {
    if (!this.selection) return null
    if (this.selection.type === 'primary') {
      const primary = this.snapshot?.primary || []
      const agentIndex = primary.findIndex(
        (item, index) => primaryVisualKey(item, index) === this.selection.key,
      )
      const agent = primary[agentIndex]
      if (!agent) return null
      const key = primaryVisualKey(agent, agentIndex)
      return {
        title: agent.title,
        subtitle: primaryDetail(agent),
        activity: agent.activity || [],
        log: '',
        accent: this.accentForAgent(key),
      }
    }
    for (const delegation of this.snapshot?.delegations || []) {
      if (delegation.delegation_id !== this.selection.delegationId) continue
      const child = (delegation.children || []).find(item => item.index === this.selection.index)
      if (!child) return null
      const ownerKey = delegationOwnerKey(this.snapshot, delegation.parent_session_id)
      return {
        title: child.goal,
        subtitle: `${child.action || child.state} · batch ${delegationProgressText(delegation.progress)}`,
        activity: child.activity || [],
        log: child.log || '',
        accent: ownerKey ? this.accentForAgent(ownerKey) : 'neutral',
      }
    }
    return null
  }

  finishDetails(width) {
    this.details.show_all()
    const [, naturalHeight] = this.details.get_preferred_height_for_width(width)
    this.detailsFrame.set_min_content_height(Math.min(Math.max(naturalHeight, 1), 535))
  }

  renderActivity(now) {
    const selected = this.resolveSelection()
    if (!selected) {
      this.selection = null
      return false
    }
    const back = new Gtk.Button({ label: '← Current work', relief: Gtk.ReliefStyle.NONE })
    back.get_style_context().add_class('hud-back')
    back.set_halign(Gtk.Align.START)
    back.connect('clicked', () => {
      this.detailsReveal.set_reveal_child(false)
      this.selection = null
      this.renderDetails()
      this.detailsReveal.set_reveal_child(true)
      this.resizeToContent()
    })
    this.details.pack_start(back, false, false, 0)

    const breadcrumb = new Gtk.Label({ label: `Hermes › ${selected.title}`, xalign: 0 })
    breadcrumb.set_ellipsize(Pango.EllipsizeMode.END)
    breadcrumb.set_max_width_chars(72)
    breadcrumb.get_style_context().add_class('hud-breadcrumb')
    breadcrumb.get_style_context().add_class(`accent-${selected.accent}`)
    this.details.pack_start(breadcrumb, false, false, 0)
    if (selected.subtitle) {
      const subtitle = new Gtk.Label({ label: selected.subtitle, xalign: 0 })
      subtitle.set_ellipsize(Pango.EllipsizeMode.END)
      subtitle.get_style_context().add_class('hud-activity-subtitle')
      this.details.pack_start(subtitle, false, false, 0)
    }

    this.section('Recent tool activity')
    if (!selected.activity.length) {
      const empty = new Gtk.Label({ label: 'No recent structured tool calls', xalign: 0 })
      empty.get_style_context().add_class('hud-activity-subtitle')
      this.details.pack_start(empty, false, false, 0)
    }
    selected.activity.forEach((item, index) => {
      const row = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
      row.get_style_context().add_class('hud-activity-row')
      row.get_style_context().add_class(`accent-${selected.accent}`)
      if (index === 0) row.get_style_context().add_class('recent')
      const timing = Number(item.at) > 0
        ? ` · ${ageText(now - Number(item.at))} ago`
        : item.clock ? ` · ${item.clock}` : ''
      const glyph = new Gtk.Label({ label: activityGlyph(item.kind), valign: Gtk.Align.START })
      glyph.get_style_context().add_class('hud-activity-glyph')
      glyph.get_style_context().add_class(`accent-${selected.accent}`)
      const content = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL, hexpand: true })
      const tool = new Gtk.Label({
        label: `${item.tool || 'tool'}${timing}`,
        xalign: 0,
      })
      tool.get_style_context().add_class('hud-activity-tool')
      const detail = new Gtk.Label({ label: item.detail || 'invoked', xalign: 0, selectable: true })
      detail.set_line_wrap(true)
      detail.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
      detail.set_max_width_chars(82)
      detail.get_style_context().add_class('hud-activity-detail')
      content.pack_start(tool, false, false, 0)
      content.pack_start(detail, false, false, 0)
      row.pack_start(glyph, false, false, 0)
      row.pack_start(content, true, true, 0)
      this.details.pack_start(row, false, false, 0)
    })
    if (selected.log) {
      const logButton = new Gtk.Button({ label: 'Open full redacted live log' })
      logButton.get_style_context().add_class('hud-log-button')
      logButton.connect('clicked', () => {
        try {
          Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(selected.log).get_uri(), null)
        } catch (_) {}
      })
      this.details.pack_start(logButton, false, false, 0)
    }
    const footer = new Gtk.Label({
      label: 'Bounded · sanitized · recent first',
      xalign: 0,
    })
    footer.get_style_context().add_class('hud-footer')
    this.details.pack_start(footer, false, false, 0)
    this.finishDetails(660)
    return true
  }

  renderDetails() {
    this.clearDetails()
    if (!this.expanded) return
    const now = Date.now() / 1000
    if (this.selection && this.renderActivity(now)) return
    const primary = this.snapshot?.primary || []
    const delegations = this.snapshot?.delegations || []
    if (primary.length) {
      this.section('Primary agents')
      const ownedDelegations = new Set()
      for (const [agentIndex, agent] of primary.entries()) {
        const key = primaryVisualKey(agent, agentIndex)
        const accent = this.accentForAgent(key)
        const agentGroup = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
        agentGroup.get_style_context().add_class('hud-agent-group')
        this.row({
          title: agent.title,
          meta: elapsedMeta(agent.started_at, agent.action, agent.last_activity_at, now),
          detail: primaryDetail(agent),
          state: agent.state,
          accent,
          parent: agentGroup,
          onActivate: () => this.selectActivity({
            type: 'primary',
            key,
          }),
        })
        const owned = delegations.filter(delegation =>
          [agent.session_id, agent.session_key].filter(Boolean).includes(delegation.parent_session_id),
        )
        for (const delegation of owned) {
          ownedDelegations.add(delegation.delegation_id)
          const batch = new Gtk.Box({ orientation: Gtk.Orientation.HORIZONTAL })
          batch.get_style_context().add_class('hud-group')
          const batchTitle = new Gtk.Label({
            label: delegation.goal || 'Delegated work',
            xalign: 0,
            hexpand: true,
          })
          batchTitle.set_ellipsize(Pango.EllipsizeMode.END)
          batchTitle.set_max_width_chars(38)
          batchTitle.get_style_context().add_class('hud-group-title')
          const progress = new Gtk.Label({
            label: delegationProgressText(delegation.progress),
            xalign: 1,
          })
          progress.get_style_context().add_class('hud-group-progress')
          batch.pack_start(batchTitle, true, true, 0)
          batch.pack_end(progress, false, false, 0)
          agentGroup.pack_start(batch, false, false, 0)
          for (const child of delegation.children || []) {
            this.row({
              title: child.goal,
              meta: elapsedMeta(delegation.started_at, child.action, child.last_activity_at, now),
              state: child.state,
              accent,
              child: true,
              parent: agentGroup,
              onActivate: () => this.selectActivity({
                type: 'child',
                delegationId: delegation.delegation_id,
                index: child.index,
              }),
            })
          }
        }
        this.details.pack_start(agentGroup, false, false, 0)
      }
      const primaryTotal = Number(this.snapshot?.counts?.primary || 0)
      if (primaryTotal > primary.length) {
        const overflow = new Gtk.Label({
          label: `+${primaryTotal - primary.length} more primary agents`,
          xalign: 0,
        })
        overflow.get_style_context().add_class('hud-group')
        this.details.pack_start(overflow, false, false, 0)
      }
      const unowned = delegations.filter(
        delegation => !ownedDelegations.has(delegation.delegation_id),
      )
      if (unowned.length) {
        this.section('Unassigned subagents')
        for (const delegation of unowned) {
          const neutralGroup = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
          neutralGroup.get_style_context().add_class('hud-agent-group')
          for (const child of delegation.children || []) {
            this.row({
              title: child.goal,
              meta: elapsedMeta(delegation.started_at, child.action, child.last_activity_at, now),
              state: child.state,
              neutral: true,
              parent: neutralGroup,
              onActivate: () => this.selectActivity({
                type: 'child',
                delegationId: delegation.delegation_id,
                index: child.index,
              }),
            })
          }
          this.details.pack_start(neutralGroup, false, false, 0)
        }
      }
    } else if (delegations.length) {
      this.section('Unassigned subagents')
      for (const delegation of delegations) {
        const neutralGroup = new Gtk.Box({ orientation: Gtk.Orientation.VERTICAL })
        neutralGroup.get_style_context().add_class('hud-agent-group')
        for (const child of delegation.children || []) {
          this.row({
            title: child.goal,
            meta: elapsedMeta(delegation.started_at, child.action, child.last_activity_at, now),
            state: child.state,
            neutral: true,
            parent: neutralGroup,
            onActivate: () => this.selectActivity({
              type: 'child',
              delegationId: delegation.delegation_id,
              index: child.index,
            }),
          })
        }
        this.details.pack_start(neutralGroup, false, false, 0)
      }
    }
    if (!primary.length && !delegations.length) {
      this.row({ title: 'No agents are running', meta: 'Hermes is idle', state: 'idle' })
    }
    const generated = Number(this.snapshot?.generated_at || 0)
    const footer = new Gtk.Label({
      label: generated ? `Updated ${ageText(now - generated)} ago · read-only` : 'Waiting for collector…',
      xalign: 0,
    })
    footer.get_style_context().add_class('hud-footer')
    this.details.pack_start(footer, false, false, 0)
    this.finishDetails(540)
  }

  position(requestedWidth = 0, requestedHeight = 0) {
    const [actualWidth, actualHeight] = this.window.get_size()
    const targetWidth = requestedWidth || actualWidth
    const targetHeight = requestedHeight || actualHeight
    const area = this.workArea(this.savedPosition, targetWidth, targetHeight)
    if (!area) return
    const bounded = boundedPanelSize(
      targetWidth,
      targetHeight,
      area.width,
      area.height,
    )
    const { width, height } = bounded
    let x = area.x + area.width - width - 18
    let y = area.y + 18
    if (this.savedPosition) {
      const clamped = clampPositionToArea(this.savedPosition, { width, height }, area)
      x = clamped.x
      y = clamped.y
      this.savedPosition = clamped
    }
    this.window.move(x, y)
  }

  show() {
    const count = Number(this.snapshot?.counts?.primary || this.snapshot?.primary?.length || 0)
    this.window.set_default_size(collapsedPanelWidth(count), 1)
    this.showWindow()
  }
}

const application = new Gtk.Application({ application_id: APPLICATION_ID })
let hudInstance = null
const toggleAction = new Gio.SimpleAction({ name: 'toggle' })
toggleAction.connect('activate', () => hudInstance?.toggle())
application.add_action(toggleAction)
const minimizeAction = new Gio.SimpleAction({ name: 'minimize' })
minimizeAction.connect('activate', () => hudInstance?.minimize())
application.add_action(minimizeAction)
const showAction = new Gio.SimpleAction({ name: 'show' })
showAction.connect('activate', () => hudInstance?.showWindow())
application.add_action(showAction)
application.connect('activate', app => {
  if (!hudInstance) {
    hudInstance = new AgentHud(app)
    hudInstance.show()
  } else {
    hudInstance.showWindow()
  }
})
application.run([])
