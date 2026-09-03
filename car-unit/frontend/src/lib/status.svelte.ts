/* Device state -- what the daemon will report once it is wired.
 *
 * Placeholders for now, in one file rather than scattered through
 * components, so connecting them later is a change here and nowhere
 * else. Nothing writes to these yet.
 */

interface Status {
  /** Whether any Bluetooth device is connected. */
  bluetooth: boolean
  /** Cellular signal, 0 to 4. */
  bars: number
  /** Outside temperature in Celsius. */
  outside: number
}

export const status = $state<Status>({
  bluetooth: false,
  bars: 4,
  outside: 19,
})
