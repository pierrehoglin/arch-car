import { request } from './client'
import type { Position } from './types'

/** Where the car is now. The same payload as the 'position' event,
 *  for a screen that cannot wait for the next one. */
export const get = () => request<Position>('/position')
