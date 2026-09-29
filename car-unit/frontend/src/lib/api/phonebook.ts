import { request } from './client'
import type { Book, BookName } from './types'

/* The phone's contacts, favourites and call logs.
 *
 * Cached by the daemon, because a PBAP pull is an OBEX transfer of
 * every vCard on the device -- seconds at best. Reading is instant;
 * syncing is not, and is always something asked for.
 */

/* A transfer of the whole book over Bluetooth. A long address book
   on a slow link is not quick. */
const SYNC_TIMEOUT = 120_000

/* Every call names the phone.
 *
 * Left to itself the daemon takes the first connected device, and
 * with two connected that is whichever BlueZ happens to list first --
 * which can differ between one request and the next. A page that
 * read the contacts from one phone and the call log from another
 * would show neither correctly, and nothing would say so. */

export const get = (address: string, book: BookName) =>
  request<Book>('/phonebook', { query: { address, book } })

export const sync = (address: string, book: BookName) =>
  request<Book>('/phonebook/sync', {
    method: 'POST',
    body: { address, book },
    timeout: SYNC_TIMEOUT,
  })

export const forget = (address: string, book?: BookName) =>
  request<Book>('/phonebook', {
    method: 'DELETE',
    query: book ? { address, book } : { address },
  })
