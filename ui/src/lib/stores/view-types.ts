import type { Site } from '../api'

export type HomeTab = 'day' | 'week' | 'month' | 'official'
export type ArcaTab = 'new' | 'weekly' | 'monthly'

export type View =
  | { kind: 'top'; tab: HomeTab }
  | { kind: 'all'; page: number }
  | { kind: 'arca'; tab: ArcaTab; page: number }
  | { kind: 'search'; site: Site; word: string; type: string; page: number }
  | { kind: 'package'; site: Site; id: number }
