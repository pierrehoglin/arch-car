import * as api from './api/phonebook'
import { RequestFailed } from './api/client'
import { bluetooth } from './bluetooth.svelte'
import type { Book, BookName, BtDevice, Contact } from './api/types'

/* The phone's books.
 *
 * Cache first, always. A PBAP pull takes seconds and sometimes most
 * of a minute, so a screen that waited for one would be blank for
 * exactly as long as it takes to lose patience. What is stored shows
 * immediately and is replaced when the transfer lands.
 *
 * How often each is pulled depends on how fast it goes wrong:
 *
 *   cch   every time the screen opens -- a list of recent calls that
 *         is ten minutes old is not a list of recent calls
 *   pb    once a session per phone; an address book is good for weeks
 *   fav   once a session per phone, same reason
 *
 * And which phone is a choice, not a guess. With two connected, the
 * daemon's own default is whichever BlueZ lists first, and that is
 * not stable between requests.
 */

const EMPTY = (book: BookName): Book => ({
  address: '',
  book,
  contacts: [],
  fetched: 0,
  stale: false,
  available: false,
})

/* Phonebook Access Server. A connected device without it is a
   headset or a laptop -- nothing to read contacts from. */
const PBAP = '0000112f'

interface Store {
  /** Keyed by book, for the phone that is chosen. */
  books: Record<string, Book>
  /** Books with a transfer running. */
  syncing: BookName[]
  error: string
  /** The phone whose books these are. Empty until one is connected. */
  address: string
}

export const phonebook = $state<Store>({
  books: {},
  syncing: [],
  error: '',
  address: '',
})

/* Which books have been pulled this session, per phone.
 *
 * Not $state: an $effect reading it would re-run when a sync
 * finished, and the thing that triggers syncs is an effect. Keyed by
 * address as well as book, so choosing a second phone pulls its
 * books rather than assuming the first phone's pull covered it. */
const pulled = new Set<string>()
const key = (address: string, book: BookName) => `${address}/${book}`

/** Connected phones that can share contacts. */
export const phones = (): BtDevice[] =>
  bluetooth.state.devices.filter(
    (device) =>
      device.connected &&
      device.uuids.some((uuid) => uuid.toLowerCase().startsWith(PBAP)),
  )

export const bookOf = (book: BookName): Book =>
  phonebook.books[book] ?? EMPTY(book)

export const isSyncing = (book: BookName) =>
  phonebook.syncing.includes(book)

function report(cause: unknown): void {
  phonebook.error =
    cause instanceof RequestFailed || cause instanceof Error
      ? cause.message
      : String(cause)
}

/* A reading is kept only if it is for the phone still chosen. A slow
   transfer for one phone landing after somebody switched to another
   would otherwise put the first phone's contacts on the second's
   screen. */
function apply(address: string, reading: Book): void {
  if (address !== phonebook.address) return
  phonebook.books = { ...phonebook.books, [reading.book]: reading }
}

/** Read what is cached. Instant. */
export async function load(book: BookName): Promise<void> {
  const address = phonebook.address
  if (!address) return

  try {
    apply(address, await api.get(address, book))
  } catch (cause) {
    report(cause)
  }
}

/**
 * Pull from the phone.
 *
 * Refuses when the daemon has said a sync cannot work -- the phone
 * disconnected, or never granted phonebook access. Trying anyway
 * means an OBEX session that hangs until it times out, with the
 * screen saying it is syncing throughout.
 */
export async function sync(book: BookName): Promise<void> {
  const address = phonebook.address
  if (!address || isSyncing(book) || !bookOf(book).available) return

  phonebook.syncing = [...phonebook.syncing, book]
  try {
    apply(address, await api.sync(address, book))
    phonebook.error = ''
    pulled.add(key(address, book))
  } catch (cause) {
    report(cause)
  } finally {
    phonebook.syncing = phonebook.syncing.filter((b) => b !== book)
  }
}

/**
 * Show a phone's books.
 *
 * Reads all three from the cache, then pulls in the background: the
 * call log every time, the address book and favourites once per
 * phone per session.
 *
 * Deliberately not awaited by the caller. The screen is usable from
 * the moment the cache lands.
 */
async function show(address: string): Promise<void> {
  phonebook.address = address
  phonebook.books = {}
  phonebook.error = ''

  if (!address) return

  const books: BookName[] = ['cch', 'pb', 'fav']
  await Promise.all(books.map(load))

  for (const book of books) {
    if (book === 'cch' || !pulled.has(key(address, book))) void sync(book)
  }
}

/**
 * Open the phone screen.
 *
 * Keeps the phone that was chosen if it is still connected, which is
 * what somebody who picked it expects on coming back. Otherwise the
 * first that can share contacts.
 */
export function open(): Promise<void> {
  const available = phones()
  const kept = available.find((p) => p.address === phonebook.address)
  return show(kept?.address ?? available[0]?.address ?? '')
}

/** Look at another phone's books. */
export function choose(address: string): Promise<void> {
  if (address === phonebook.address) return Promise.resolve()
  return show(address)
}

/** Ask for one again, whatever was decided about sessions. */
export const refresh = (book: BookName) => sync(book)

/** The first number on a contact, which is what a tap should ring. */
export const numberOf = (contact: Contact): string =>
  contact.numbers[0]?.number ?? ''
