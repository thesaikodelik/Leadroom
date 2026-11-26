// Workspace palettes are colour variants of one design (the Survey Field Book); each
// comes in light and dark. The palette is a workspace setting kept by the API; the
// appearance (system, light or dark) belongs to this computer and lives in localStorage.

export type ThemeId = 'fieldbook' | 'oxblood' | 'navy' | 'graphite'
export type Appearance = 'system' | 'light' | 'dark'

export const DEFAULT_THEME: ThemeId = 'fieldbook'
export const THEME_STORAGE_KEY = 'leadroom-theme'
export const APPEARANCE_STORAGE_KEY = 'leadroom-appearance'

export const THEMES: { id: ThemeId; label: string; cloth: string; paper: string }[] = [
  { id: 'fieldbook', label: 'Field Book', cloth: '#1F3A30', paper: '#F3F6F3' },
  { id: 'oxblood', label: 'Oxblood', cloth: '#4A1F1C', paper: '#F3F6F3' },
  { id: 'navy', label: 'Navy', cloth: '#1C2B47', paper: '#F3F6F3' },
  { id: 'graphite', label: 'Graphite', cloth: '#2A2D2F', paper: '#F3F6F3' },
]

const THEME_IDS = new Set<ThemeId>(THEMES.map((theme) => theme.id))

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void> }
}

export function isThemeId(value: unknown): value is ThemeId {
  return typeof value === 'string' && THEME_IDS.has(value as ThemeId)
}

export function isAppearance(value: unknown): value is Appearance {
  return value === 'system' || value === 'light' || value === 'dark'
}

const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

function resolvedAppearance(appearance: Appearance): 'light' | 'dark' {
  if (appearance === 'system') return darkQuery().matches ? 'dark' : 'light'
  return appearance
}

function withTransition(update: () => void, animate: boolean) {
  const viewDocument = document as ViewTransitionDocument
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!animate || reduceMotion || !viewDocument.startViewTransition) {
    update()
    return
  }
  document.documentElement.classList.add('theme-transitioning')
  const transition = viewDocument.startViewTransition(update)
  void transition.finished.finally(() => document.documentElement.classList.remove('theme-transitioning'))
}

export function applyTheme(theme: ThemeId, animate = true) {
  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  if (document.documentElement.dataset.theme === theme) return
  withTransition(() => { document.documentElement.dataset.theme = theme }, animate)
}

export function currentAppearance(): Appearance {
  const stored = window.localStorage.getItem(APPEARANCE_STORAGE_KEY)
  return isAppearance(stored) ? stored : 'system'
}

export function applyAppearance(appearance: Appearance, animate = true) {
  window.localStorage.setItem(APPEARANCE_STORAGE_KEY, appearance)
  const resolved = resolvedAppearance(appearance)
  if (document.documentElement.dataset.appearance === resolved) return
  withTransition(() => { document.documentElement.dataset.appearance = resolved }, animate)
}

export function initializeTheme() {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
  applyTheme(isThemeId(stored) ? stored : DEFAULT_THEME, false)
  applyAppearance(currentAppearance(), false)
  // Follow Windows when the appearance is left on System.
  darkQuery().addEventListener('change', () => {
    if (currentAppearance() === 'system') applyAppearance('system')
  })
}
