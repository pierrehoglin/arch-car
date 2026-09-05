<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'

  /* A list you can reorder by holding an item and dragging it.
   *
   * Hold and drag are the same opening gesture, resolved by what
   * happens next, on two timers:
   *
   *   tap             activate
   *   hold 500ms      the item lifts and can be dragged
   *   then move       reorder; the edit timer is cancelled
   *   then wait 1.5s  the editor opens, without waiting for a release
   *   release         reorder if dragged, activate otherwise
   *
   * The editor opening on its own rather than on release is what
   * makes the gesture discoverable: holding something and having it
   * do nothing until let go teaches nobody that holding does
   * anything.
   *
   * Pointer events rather than HTML drag-and-drop: that API is built
   * around a mouse and a drag image, and on a touch screen it either
   * does nothing or fights the scroller.
   */

  interface Props {
    items: T[]
    /** Stable identity, so reordering does not rebuild every node. */
    key: (item: T) => string | number

    /** Tapped without holding. */
    onactivate?: (item: T, index: number) => void
    /** Held still long enough to ask for the editor. */
    onhold?: (item: T, index: number) => void
    /** Dropped somewhere new. Gives the whole list in its new order,
     *  because that is what has to be saved. */
    onreorder?: (items: T[]) => void

    /** How long before a press lifts the item for dragging. */
    holdMs?: number
    /** How long a still hold takes to open the editor. */
    editMs?: number
    /** Spoken name for an item, since the slot is the control. */
    label?: (item: T) => string
    class?: string
    item: Snippet<[T, number, { held: boolean; dragging: boolean }]>
  }

  let {
    items,
    key,
    onactivate,
    onhold,
    onreorder,
    holdMs = 500,
    editMs = 1500,
    label,
    class: extra = '',
    item,
  }: Props = $props()

  /* The order shown while dragging. Null the rest of the time, so the
     list follows its prop and a change from the daemon is not fought
     by a stale local copy. */
  let working = $state<T[] | null>(null)

  let heldKey = $state<string | number | null>(null)
  let moved = $state(false)

  /* Set once the editor has opened. The finger is still down at that
     point, and without this the release that follows would be read as
     a tap and play the station behind the dialog. */
  let done = false

  let liftTimer: ReturnType<typeof setTimeout> | undefined
  let editTimer: ReturnType<typeof setTimeout> | undefined
  let origin = { x: 0, y: 0 }

  const shown = $derived(working ?? items)

  /** Enough movement to be a drag rather than an unsteady finger. */
  const SLOP = 8

  function reset(): void {
    done = false
    clearTimeout(liftTimer)
    clearTimeout(editTimer)
    liftTimer = undefined
    editTimer = undefined
    heldKey = null
    moved = false
    working = null
  }

  function down(event: PointerEvent, index: number): void {
    if (event.button !== 0 && event.pointerType === 'mouse') return

    origin = { x: event.clientX, y: event.clientY }
    moved = false
    done = false

    const target = event.currentTarget as HTMLElement

    liftTimer = setTimeout(() => {
      heldKey = key(shown[index])
      working = [...shown]
      /* Captured so the gesture keeps coming here even once the
         finger has left the element it started on -- which it will,
         immediately, since the point is to drag it somewhere else. */
      target.setPointerCapture(event.pointerId)
    }, holdMs)

    /* Cancelled the moment the item is dragged: a drag and an edit
       are different intentions, and once one is under way the other
       must not fire behind it. */
    editTimer = setTimeout(() => {
      if (moved) return
      const entry = shown[index]
      /* Cleared but for the flag, which has to outlive the reset so
         the pointerup still to come knows the gesture was spent. */
      reset()
      done = true
      onhold?.(entry, index)
    }, editMs)
  }

  function move(event: PointerEvent, container: HTMLElement): void {
    const far =
      Math.abs(event.clientX - origin.x) > SLOP ||
      Math.abs(event.clientY - origin.y) > SLOP

    if (heldKey === null) {
      // Moved before the hold registered: a scroll, not a press.
      if (far) reset()
      return
    }

    if (!far) return

    if (!moved) {
      moved = true
      clearTimeout(editTimer)
    }
    event.preventDefault()

    const list = working
    if (!list) return

    const from = list.findIndex((entry) => key(entry) === heldKey)
    const to = indexAt(container, event.clientX, event.clientY)
    if (to === -1 || to === from) return

    const next = [...list]
    const [lifted] = next.splice(from, 1)
    next.splice(to, 0, lifted)
    working = next
  }

  /** Which slot the pointer is over, by hit-testing the rendered
   *  positions rather than arithmetic on a grid we do not control. */
  function indexAt(container: HTMLElement, x: number, y: number): number {
    const slots = [...container.querySelectorAll('[data-slot]')]
    return slots.findIndex((slot) => {
      const box = slot.getBoundingClientRect()
      return (
        x >= box.left && x <= box.right && y >= box.top && y <= box.bottom
      )
    })
  }

  function up(index: number): void {
    if (done) {
      // The editor is already open; this release is just the finger
      // coming off.
      done = false
      return
    }

    const order = working

    if (heldKey !== null && moved && order) {
      onreorder?.(order)
    } else {
      /* Anything short of a completed drag plays it, including a hold
         let go before the editor opened. Doing nothing there would
         punish hesitating. */
      onactivate?.(shown[index], index)
    }

    reset()
  }

  /* Enter and Space activate. There is no keyboard equivalent of a
     long press, so editing stays a touch gesture -- which is what
     this panel has. */
  function keydown(event: KeyboardEvent, entry: T, index: number): void {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    onactivate?.(entry, index)
  }

  let container = $state<HTMLElement>()
</script>

<!-- The browser fires contextmenu on a long press, which is the same
     gesture as the hold -- and it arrives first, so the menu opens
     over the item being dragged. Suppressed here rather than on each
     slot, since nothing inside wants one. -->
<div
  class="sortable {extra}"
  class:rearranging={heldKey !== null}
  bind:this={container}
  oncontextmenu={(e) => e.preventDefault()}
  onpointermove={(e) => container && move(e, container)}
  onpointercancel={reset}
  ondragstart={(e) => e.preventDefault()}
>
  {#each shown as entry, index (key(entry))}
    {@const held = key(entry) === heldKey}
    <!-- The slot is the control, not whatever the caller renders
         inside it. Putting the gesture on the slot and the semantics
         on a button within would mean two overlapping targets, and
         the inner one would have to be made inert to keep the drag
         working -- which takes it out of the tab order and loses the
         focus ring with it. -->
    <div
      class="slot"
      class:held
      class:dragging={held && moved}
      data-slot
      role="button"
      tabindex="0"
      aria-label={label?.(entry)}
      onpointerdown={(e) => down(e, index)}
      onpointerup={() => up(index)}
      onkeydown={(e) => keydown(e, entry, index)}
    >
      {@render item(entry, index, { held, dragging: held && moved })}
    </div>
  {/each}
</div>

<style>
  /* Deliberately not display: contents, tempting though it is for
     letting a grid see the items directly. An element with no box
     returns a zero-size rect, and the drag works by hit-testing those
     rects -- so the slots have to be real boxes.

     The container takes its layout from the caller instead. */
  .sortable {
    display: grid;
    grid-template-columns: var(--columns, repeat(4, 1fr));
    gap: var(--gap, var(--spacing-s));
  }

  .slot {
    display: flex;
    min-width: 0;
    /* Every one of these stops the browser claiming the gesture
       first: the callout is Safari's magnifier, the selection is the
       text cursor a long press otherwise starts, and touch-action
       tells the compositor not to treat the drag as a scroll.
       
       touch-action has to be set before the gesture begins, not once
       the hold has registered -- by then the browser has already
       decided what the touch is for. */
    touch-action: none;
    -webkit-touch-callout: none;
    user-select: none;
    -webkit-user-select: none;
    border-radius: var(--radius-sm);
  }

  .slot:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* The direct child only: the caller's element, not everything
     inside it. */
  .slot > :global(*) {
    flex: 1;
    min-width: 0;
    transition:
      transform 160ms ease,
      opacity 160ms ease,
      box-shadow 160ms ease;
  }

  /* Everything else recedes while one item is held, so it reads as
     "this one is loose" rather than "this one looks slightly odd".
     A lift on its own is easy to miss on a bright panel. */
  .sortable.rearranging .slot:not(.held) > :global(*) {
    opacity: 0.55;
  }

  .slot.held > :global(*) {
    /* Well clear of the grid: under a thumb, most of the item is
       hidden, so the part still showing has to carry it. */
    transform: scale(1.1);
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    box-shadow: 0 10px 28px rgb(0 0 0 / 0.5);
  }

  .slot.held {
    /* Above its neighbours, or the scaled edges slide under them. */
    position: relative;
    z-index: 2;
  }

  .sortable.rearranging .slot.held {
    cursor: grabbing;
  }

  .slot.dragging > :global(*) {
    box-shadow: 0 14px 34px rgb(0 0 0 / 0.55);
  }

  /* The others slide rather than jump, so a swap is something you
     watch happen instead of something you notice afterwards. */
  .sortable.rearranging .slot:not(.held) {
    transition: transform 160ms ease;
  }

  @media (prefers-reduced-motion: reduce) {
    .slot > :global(*),
    .sortable.rearranging .slot:not(.held) {
      transition: none;
    }
  }
</style>
