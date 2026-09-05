<script lang="ts">
  import Icon from '../Icon.svelte'

  /* An on-screen keyboard, as a sheet across the bottom.
   *
   * It edits a real <input>, never a string. That is what makes a
   * caret possible, and with a caret the arrow keys have something to
   * move -- typing into a string can only ever append. In live mode
   * the input is the caller's; otherwise the sheet renders its own
   * above the keys.
   *
   * Buffered, the default: typing goes into the sheet's own field and
   * Done hands it back. For a field the sheet covers, which on an
   * 800px panel is most of them.
   *
   * Live: edits go straight to the caller's field. For search, where
   * results should follow the typing rather than wait for it.
   */

  interface Props {
    /** What the field held when the keyboard opened. */
    initial: string
    label: string
    maxlength?: number

    /** The caller's input, edited directly. Its presence is what
     *  makes this live. */
    target?: HTMLInputElement

    onchange?: (value: string) => void
    ondone: (value: string) => void
    oncancel: () => void
  }

  let {
    initial,
    label,
    maxlength = 24,
    target,
    onchange,
    ondone,
    oncancel,
  }: Props = $props()

  const live = $derived(!!target)

  let buffer = $state<HTMLInputElement>()
  let value = $state(initial)

  /** Whichever input this keyboard is driving. */
  const field = () => target ?? buffer

  $effect(() => {
    /* Focus so the caret shows and the browser keeps a selection for
       us to insert at. The panel has no hardware keyboard, so nothing
       else will put focus here.
       
       The field is editable rather than readonly: a readonly input is
       selectable but not editable, and browsers will not place a
       caret in one on a touch screen -- there is nothing to point at.
       inputmode="none" keeps the caret while telling the browser not
       to raise a keyboard of its own, which is what readonly was
       reaching for. */
    field()?.focus()
  })

  function apply(next: string, caret: number): void {
    const input = field()
    if (!input) return

    input.value = next
    input.setSelectionRange(caret, caret)
    input.focus()

    /* Setting .value from script does not fire an input event, so a
       bind:value on the caller's field would never hear about it --
       and would then write its own stale value back over ours, taking
       the caret to the end with it. Dispatching one keeps the binding
       in step without a second source of truth. */
    input.dispatchEvent(new Event('input', { bubbles: true }))

    value = next
    onchange?.(next)
  }

  /** Where the caret is, or the end if the browser will not say. */
  function selection(): [number, number] {
    const input = field()
    if (!input) return [0, 0]
    const start = input.selectionStart ?? input.value.length
    const end = input.selectionEnd ?? start
    return [start, end]
  }

  function type(key: string): void {
    const input = field()
    if (!input) return

    const [start, end] = selection()
    /* Measured against what is left after the selection goes, so
       replacing a selection is not blocked by a full field. */
    if (input.value.length - (end - start) + key.length > maxlength) return

    apply(
      input.value.slice(0, start) + key + input.value.slice(end),
      start + key.length,
    )
  }

  function backspace(): void {
    const input = field()
    if (!input) return

    const [start, end] = selection()

    if (start !== end) {
      apply(input.value.slice(0, start) + input.value.slice(end), start)
      return
    }
    if (start === 0) return

    apply(
      input.value.slice(0, start - 1) + input.value.slice(start),
      start - 1,
    )
  }

  function clear(): void {
    apply('', 0)
  }

  function move(to: 'left' | 'right' | 'start' | 'end'): void {
    const input = field()
    if (!input) return

    const [start, end] = selection()
    const at =
      to === 'left'
        ? Math.max(0, start - 1)
        : to === 'right'
          ? Math.min(input.value.length, end + 1)
          : to === 'start'
            ? 0
            : input.value.length

    input.setSelectionRange(at, at)
    input.focus()
  }

  /* Whichever way it ends, it ends once. Blur, Escape, Done and
     Cancel can all arrive together -- dismissing by tapping elsewhere
     fires blur and whatever was tapped -- and without this the second
     one acts on a keyboard that has already gone. */
  let dismissed = false

  function finish(next: string): void {
    if (dismissed) return
    dismissed = true
    ondone(next)
  }

  /* Live mode has already changed the field by the time Cancel is
     pressed, so cancelling has to put it back. Buffered mode has
     nothing to undo -- that is the point of the buffer. */
  function cancel(): void {
    if (dismissed) return
    dismissed = true
    if (live) apply(initial, initial.length)
    oncancel()
  }

  /* Focus leaving the field closes the keyboard -- it is no longer
     driving anything.
     
     This only works because the keys do not take focus: see the
     mousedown handler on the sheet. Without that, every keypress
     would blur the field and shut the keyboard on the first letter.
     
     Treated as done rather than cancel, because the way focus usually
     leaves is by tapping the thing you were typing towards -- a
     search result, the Save button -- and throwing the text away at
     that moment would be the opposite of what was asked. */
  $effect(() => {
    const input = field()
    if (!input) return

    // Trimmed, as Done does -- the two ways of finishing
    // should not disagree about trailing spaces.
    const left = () => finish(input.value.trim())
    input.addEventListener('blur', left)
    return () => input.removeEventListener('blur', left)
  })

  let shifted = $state(true)
  let symbols = $state(false)

  const LETTERS = [
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 'å'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'ö', 'ä'],
    ['z', 'x', 'c', 'v', 'b', 'n', 'm'],
  ]

  const SYMBOLS = [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['-', '/', ':', ';', '(', ')', '&', '@', '"'],
    ['.', ',', '?', '!', "'", '+', '=', '#'],
  ]

  /* Cased once, at module scope. Keeping the keys lowercase and
     applying the case where they are used would be a condition to get
     right in two places, and it would also have to remember that
     shift means nothing on the symbols layer. Choosing the row says
     both once. */
  const CAPITALS = LETTERS.map((row) => row.map((key) => key.toUpperCase()))

  const rows = $derived(symbols ? SYMBOLS : shifted ? CAPITALS : LETTERS)

  function press(key: string): void {
    type(key)
    /* Shift is for one letter, as on a phone: leaving it latched
       makes every name SHOUT. */
    if (shifted) shifted = false
  }

  /* Escape closes the keyboard, not the dialog underneath it. Caught
     during capture and stopped, because the browser fires a dialog's
     own cancel from the same key -- without this, one press would
     dismiss both and the innermost thing would be the one that did
     not react. */
  $effect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      cancel()
    }

    window.addEventListener('keydown', escape, { capture: true })
    return () =>
      window.removeEventListener('keydown', escape, { capture: true })
  })
</script>

<!-- Focus never leaves the field. preventDefault on mousedown stops
     the browser moving it to the button, which keeps the caret where
     it is and means a blur is always something outside the keyboard
     taking over. click still fires, so the keys work as normal. -->
<div class="keyboard" onmousedown={(e) => e.preventDefault()}>
  <!-- Hidden in live mode: the caller's field is showing this
       already, and two copies of the same text invite the question of
       which one is real. -->
  {#if !live}
    <div class="buffer">
      <span class="label">{label}</span>
      <input
        bind:this={buffer}
        type="text"
        value={initial}
        {maxlength}
        placeholder="Type a name"
        aria-label={label}
        autocomplete="off"
        spellcheck="false"
        inputmode="none"
        oninput={(e) => (value = e.currentTarget.value)}
      />
    </div>
  {/if}

  <div class="keys">
    {#each rows as row, index (index)}
      <div class="row">
        {#if index === rows.length - 1}
          <button
            class="key mod"
            class:on={shifted}
            aria-pressed={shifted}
            aria-label="Shift"
            onclick={() => (shifted = !shifted)}
            disabled={symbols}
          >
            <Icon name="shift" size={22} />
          </button>

          <!-- Beside shift, because they are the same kind of thing:
               both change what the letters below them are. -->
          <button
            class="key mod"
            class:on={symbols}
            aria-pressed={symbols}
            onclick={() => (symbols = !symbols)}
          >
            {symbols ? 'ABC' : '#+='}
          </button>
        {/if}

        <!-- Keyed by position, not by the character. The character
             changes on every shift, and keying by it would destroy
             and rebuild all thirty buttons each time -- including the
             one still under the finger, since shift unlatches on the
             press that just happened. Positions never move. -->
        {#each row as key, column (column)}
          <button class="key" onclick={() => press(key)}>
            {key}
          </button>
        {/each}

        {#if index === rows.length - 1}
          <button
            class="key backspace"
            aria-label="Backspace"
            onclick={backspace}
          >
            <Icon name="backspace" size={22} />
          </button>
        {/if}
      </div>
    {/each}

    <div class="row">
      <!-- A single-line field, so up and down are its ends. That is
           what they do in a browser's own text fields too. -->
      <button class="key arrow" aria-label="Left" onclick={() => move('left')}>
        <Icon name="left" size={20} />
      </button>
      <button
        class="key arrow"
        aria-label="Start"
        onclick={() => move('start')}
      >
        <Icon name="up" size={20} />
      </button>
      <button class="key arrow" aria-label="End" onclick={() => move('end')}>
        <Icon name="down" size={20} />
      </button>
      <button
        class="key arrow"
        aria-label="Right"
        onclick={() => move('right')}
      >
        <Icon name="right" size={20} />
      </button>

      <button class="key space" onclick={() => press(' ')}>Space</button>

      <button class="key clear" aria-label="Clear" onclick={clear}>
        <Icon name="close" size={20} />
      </button>

      <button class="key cancel" onclick={cancel}>Cancel</button>

      <button class="key done" onclick={() => finish(value.trim())}>
        Done
      </button>
    </div>
  </div>
</div>

<style>
  .keyboard {
    /* Fixed, so it sits against the screen rather than inside
       whatever opened it. Inside a dialog that still works, and being
       a descendant is what puts it in the top layer. */
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-s);
    padding: var(--spacing) var(--spacing-l) var(--spacing-l);
    background: var(--bar);
    border-top: 1px solid var(--hairline);
  }

  .buffer {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px var(--spacing);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .label {
    font-family: var(--font-display);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-dim);
  }

  .buffer input {
    width: 100%;
    padding: 0;
    font-family: var(--font-body);
    font-size: 20px;
    line-height: 30px;
    color: var(--text);
    background: none;
    border: 0;
    caret-color: var(--accent);
  }

  .buffer input::placeholder {
    color: var(--text-faint);
  }

  .buffer input:focus {
    outline: none;
  }

  .keys {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .row {
    display: flex;
    justify-content: center;
    gap: 6px;
  }

  .key {
    flex: 1;
    /* Tall enough to hit while the car is moving, which is most of
       why this is not a library default. */
    min-height: 58px;
    min-width: 0;
    display: grid;
    place-items: center;
    font-family: var(--font-body);
    font-size: 20px;
    color: var(--text);
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
  }

  .key:active {
    color: var(--accent-ink);
    background: var(--accent);
    border-color: transparent;
  }

  .key:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .key:disabled {
    opacity: 0.35;
  }

  .key.on {
    color: var(--accent);
    border-color: var(--accent);
  }

  /* Sized so the seven letters between them come out the same width
     as the eleven in the rows above. Left to flex, the bottom row's
     letters end up noticeably fatter and read as a different
     keyboard. */
  .key.mod {
    flex: 0 0 120px;
    font-size: 15px;
  }

  /* And it takes the remainder, which suits it: backspace is used
     more than any single letter, and usually in a hurry. */
  .key.backspace {
    flex: 0 0 195px;
  }

  .key.arrow {
    flex: 0 0 62px;
    color: var(--text-dim);
  }

  .key.clear {
    flex: 0 0 62px;
    color: var(--text-dim);
  }

  .key.space {
    flex: 2;
  }

  .key.cancel {
    flex: 0 0 110px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-dim);
    background: none;
  }

  .key.done {
    flex: 0 0 140px;
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--accent-ink);
    background: var(--accent);
    border-color: transparent;
  }
</style>
