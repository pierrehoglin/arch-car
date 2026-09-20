import { GROUPS } from './groups'

/* Which parts of the API are mocked.
 *
 * In localStorage rather than in the daemon's settings, and not for
 * want of somewhere better: this decides whether the daemon is
 * reachable at all, so asking the daemon would be circular. It also
 * has to be known before the first request, which rules out anything
 * fetched.
 *
 * Development only. The worker is imported dynamically and the whole
 * module is guarded on DEV at its one call site, so none of it -- nor
 * msw itself -- reaches the production bundle.
 */

const KEY = 'carlib-mocks'

type Enabled = Record<string, boolean>

/** Everything mocked: a fresh checkout has no daemon. */
const all = (value: boolean): Enabled =>
  Object.fromEntries(GROUPS.map((group) => [group.id, value]))

function stored(): Enabled {
  const fallback = all(true)

  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return fallback

    /* Merged over the defaults rather than used as-is, so a group
       added later is mocked until it is turned off -- the safe way
       round, since the daemon is the thing that might not answer. */
    return { ...fallback, ...(JSON.parse(raw) as Enabled) }
  } catch {
    return fallback
  }
}

interface Control {
  enabled: Enabled
  /** True while a change is being applied, so a switch can show as
   *  pending rather than lying. */
  busy: boolean
}

export const mocks = $state<Control>({
  enabled: stored(),
  busy: false,
})

/** Whether every group is mocked, for a single summary switch. */
export const allMocked = () => GROUPS.every((g) => mocks.enabled[g.id])

/** Whether none are, which is what talking only to carlib looks like. */
export const noneMocked = () => GROUPS.every((g) => !mocks.enabled[g.id])

function remember(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(mocks.enabled))
  } catch {
    // Private browsing. It still applies for this session.
  }
}

async function apply(): Promise<void> {
  const { applyHandlers } = await import('./browser')
  applyHandlers(mocks.enabled)
  remember()
}

/**
 * Turn one group on or off, now.
 *
 * Handlers are swapped rather than the worker restarted, so this
 * takes effect without a reload -- which matters, because the reason
 * to reach for it is usually that something behaves differently
 * against the daemon and you want to compare.
 *
 * Screens are not told. A store that has already loaded keeps what
 * it has until it next fetches, which is the honest thing: the data
 * on screen did come from wherever it came from.
 */
export async function setGroup(id: string, on: boolean): Promise<void> {
  if (mocks.busy || mocks.enabled[id] === on) return

  mocks.busy = true
  try {
    mocks.enabled = { ...mocks.enabled, [id]: on }
    await apply()
  } finally {
    mocks.busy = false
  }
}

/** All of them at once, for the summary switch. */
export async function setAll(on: boolean): Promise<void> {
  if (mocks.busy) return

  mocks.busy = true
  try {
    mocks.enabled = all(on)
    await apply()
  } finally {
    mocks.busy = false
  }
}

/** Start the worker with whatever was left switched on. */
export async function init(): Promise<void> {
  const { startMocking } = await import('./browser')
  await startMocking(mocks.enabled)
}
