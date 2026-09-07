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
  /**
   * Outside temperature, from the car's own sensor over CAN.
   *
   * Deliberately not the weather service's reading. They disagree --
   * a forecast is for a municipality and the sensor is in the
   * bumper -- and the one worth showing in the status bar is the car's,
   * because it is the one that knows the road is about to freeze.
   */
  outside: number | null
}

export const status = $state<Status>({
  bluetooth: false,
  bars: 4,
  outside: 19,
})
