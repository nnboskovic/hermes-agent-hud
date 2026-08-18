#!/usr/bin/gjs

imports.gi.versions.Gtk = '3.0'
const GLib = imports.gi.GLib
const Gtk = imports.gi.Gtk

Gtk.init(null)
const [, contents] = GLib.file_get_contents('hud.js')
const source = new TextDecoder('utf-8').decode(contents)
const match = source.match(/const CSS = `([\s\S]*?)`\n\nfunction statePath/)
if (!match) throw new Error('CSS block not found')
for (const marker of ['hud-child-overflow', 'accent-neutral', 'primaryVisualKey']) {
  if (!source.includes(marker)) throw new Error(`Visual contract marker missing: ${marker}`)
}
for (const marker of ['get_monitor_at_point', 'clampPositionToArea']) {
  if (!source.includes(marker)) throw new Error(`Monitor-aware positioning marker missing: ${marker}`)
}
const css = match[1]
for (const [selector, minimum] of [
  ['.hud-brand', 14],
  ['.hud-summary', 11],
  ['.hud-section', 10],
  ['.hud-row-title', 13],
  ['.hud-row-meta', 11],
  ['.hud-row-detail', 10],
  ['.hud-activity-detail', 12],
  ['.hud-footer', 9],
]) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const rule = css.match(new RegExp(`${escaped}\\s*\\{[^}]*font-size:\\s*(\\d+)px`, 's'))
  if (!rule || Number(rule[1]) < minimum) {
    throw new Error(`${selector} must use at least ${minimum}px text`)
  }
}
const provider = new Gtk.CssProvider()
provider.load_from_data(new TextEncoder().encode(match[1]))
print('gtk css ok')
