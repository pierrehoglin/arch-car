import { request, RequestFailed } from './client'

/* Phone calls, against the daemon's /call endpoints.

   Every request answers once the phone has accepted it -- or with why
   not -- and nothing more. What happens next, the other end picking
   up or hanging up, comes through the 'call' event alone. */

export type CallState =
  | 'incoming'
  | 'dialing'
  | 'alerting'
  | 'active'
  | 'held'
  | 'waiting'
  | 'ended'

export interface Call {
  /** Unique across phones: "AABBCCDDEEFF-3". */
  id: string
  /** The phone it is on, by Bluetooth address. */
  phone: string
  state: CallState
  direction: 'in' | 'out'
  number: string
  /** From that phone's book, or empty. */
  name: string
  /** A digest for /phonebook/photo/<digest>, or empty. */
  photo: string
  /** Unix seconds, once connected. */
  connected_at: number | null
  /** local | remote | network, once ended. */
  ended_reason: string
}

export interface CallPhone {
  address: string
  name: string
  /** Its microphone, during its calls. */
  muted: boolean
}

export interface CallStatus {
  /** Any phone with a hands-free link. */
  available: boolean
  phones: CallPhone[]
  calls: Call[]
}

export const status = () => request<CallStatus>('/call')

const post = <T>(path: string, body: Record<string, unknown> = {}) =>
  request<T>(path, { method: 'POST', body, timeout: 20_000 })

export const dial = (number: string, phone?: string) =>
  post<{ id: string; phone: string }>('/call/dial', { number, phone })
export const answer = (id?: string) => post('/call/answer', { id })
export const decline = (id?: string) => post('/call/decline', { id })
export const hangup = (id?: string) => post('/call/hangup', { id })
export const holdAnswer = (id?: string) => post('/call/hold-answer', { id })
export const mute = (on: boolean, phone?: string) =>
  post('/call/mute', { on, phone })
export const tones = (digits: string, id?: string) =>
  post('/call/tones', { digits, id })

/** What went wrong with a request, as a line for the screen. */
export function failure(cause: unknown): string {
  if (!(cause instanceof RequestFailed)) return 'That did not work.'
  if (cause.status === 0) return 'The car service did not answer.'
  return (
    {
      no_phone: 'No phone connected for calls.',
      choose_phone: 'Choose which phone to call from.',
      no_call: 'That call has already ended.',
      choose_call: 'More than one call — choose which.',
      invalid_number: 'Not a number the phone can call.',
      refused: "The phone didn't do it.",
    } as Record<string, string>
  )[cause.reason] ?? 'That did not work.'
}

/** Its photo's address, for an <img>. */
export const photoUrl = (digest: string) =>
  digest ? `/api/phonebook/photo/${digest}` : ''
