import { request } from './client'

/* Stored preferences.
 *
 * Only what survives a reload lives here. Anything that describes a
 * device rather than a choice -- volume, what is playing, whether
 * Bluetooth is on -- belongs to the store for that device and comes
 * off the event stream.
 */

/**
 * Everything that has been set.
 *
 * Nested, as it is on disk: `ui.theme` comes back as
 * `{ ui: { theme: 'night' } }`. Writes take the dotted key instead,
 * which is not a mistake -- the file is a document and the key is an
 * address into it -- but it does mean a reader cannot just look up
 * the string it wrote. `valueAt` walks the path.
 */
export const all = () => request<Record<string, unknown>>('/settings')

/** Follow a dotted key into the nested reading. */
export function valueAt(
  stored: Record<string, unknown>,
  key: string,
): unknown {
  let node: unknown = stored

  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) return undefined
    node = (node as Record<string, unknown>)[part]
  }

  return node
}

/** Write some keys. Others are left alone. */
export const update = (values: Record<string, unknown>) =>
  request<Record<string, unknown>>('/settings', {
    method: 'PUT',
    body: { values },
  })

/** Put a key back to its default. */
export const reset = (key: string) =>
  request<Record<string, unknown>>(
    `/settings/${encodeURIComponent(key)}`,
    { method: 'DELETE' },
  )
