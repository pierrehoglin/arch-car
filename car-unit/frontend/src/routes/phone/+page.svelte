<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Avatar from '$lib/ui/Avatar.svelte'
  import Card from '$lib/ui/Card.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon. */

  const favourites = [
    { short: 'Anna', name: 'Anna Lind' },
    { short: 'Mamma', name: 'Mamma' },
    { short: 'Erik', name: 'Erik Waller' },
    { short: 'Astrid', name: 'Astrid Berg' },
    { short: 'Service', name: 'Service' },
  ]
  let selected = $state('Anna Lind')

  const recent = [
    { name: 'Anna Lind', kind: 'Outgoing', when: 'Today · 12:04' },
    { name: 'Erik Waller', kind: 'Missed', when: 'Today · 09:41' },
    { name: 'Mamma', kind: 'Incoming', when: 'Yesterday · 18:20' },
  ]

  const contacts = [
    { name: 'Anna Lind', number: '070 123 45 67' },
    { name: 'Astrid Berg', number: '070 456 78 90' },
    { name: 'Erik Waller', number: '070 345 67 89' },
    { name: 'Johan Ek', number: '070 555 12 34' },
    { name: 'Lina Sund', number: '070 666 23 45' },
    { name: 'Mamma', number: '070 234 56 78' },
  ]

  let dialled = $state('')

  const keys = [
    { digit: '1', letters: '' },
    { digit: '2', letters: 'ABC' },
    { digit: '3', letters: 'DEF' },
    { digit: '4', letters: 'GHI' },
    { digit: '5', letters: 'JKL' },
    { digit: '6', letters: 'MNO' },
    { digit: '7', letters: 'PQRS' },
    { digit: '8', letters: 'TUV' },
    { digit: '9', letters: 'WXYZ' },
    { digit: '*', letters: '' },
    /* Held rather than tapped, as on a phone. There is nowhere else
       to put a plus without a key that does nothing most of the
       time. */
    { digit: '0', letters: '+', hold: '+' },
    { digit: '#', letters: '' },
  ]

  /* Letters to the key they sit on, so what is typed can be matched
     against names as well as numbers. Å and Ä ride with A, and Ö with
     O, which is where a Nordic handset puts them. */
  const T9: Record<string, string> = {}
  for (const [digit, letters] of Object.entries({
    '2': 'abcåä',
    '3': 'def',
    '4': 'ghi',
    '5': 'jkl',
    '6': 'mnoö',
    '7': 'pqrs',
    '8': 'tuv',
    '9': 'wxyz',
  })) {
    for (const letter of letters) T9[letter] = digit
  }

  /** A word as the digits that would spell it. */
  const encode = (text: string) =>
    [...text.toLowerCase()]
      .map((character) => T9[character] ?? '')
      .join('')

  /* Only the digits count for matching. A plus or a hash is part of
     the number being dialled, not part of a search. */
  const typed = $derived(dialled.replace(/\D/g, ''))

  /**
   * Contacts the keypad is pointing at.
   *
   * A name matches when any of its words begins with what was typed,
   * so 5463 finds Lind without having to spell Anna first. A number
   * matches anywhere inside it, since the part someone remembers is
   * often the middle.
   */
  const matching = $derived(
    !typed
      ? contacts
      : contacts.filter((contact) => {
          if (contact.number.replace(/\D/g, '').includes(typed)) return true
          return contact.name
            .split(/\s+/)
            .some((word) => encode(word).startsWith(typed))
        }),
  )

  /** How long 0 must be held before it becomes a plus. */
  const HOLD_MS = 500

  let holdTimer: ReturnType<typeof setTimeout> | undefined
  let held = false

  function startHold(key: { digit: string; hold?: string }): void {
    held = false
    if (!key.hold) return

    holdTimer = setTimeout(() => {
      held = true
      dialled += key.hold
    }, HOLD_MS)
  }

  const endHold = () => clearTimeout(holdTimer)

  /* On click rather than pointerup, so a key still works from a
     keyboard. The flag is set by the hold and cleared here, since
     click always follows the pointer events that raised it. */
  function press(key: { digit: string }): void {
    if (held) {
      held = false
      return
    }
    dialled += key.digit
  }

  /* Grouped by first letter, with each letter shown once. Rebuilt on
     every filter so the headings never outlive their contacts. */
  const grouped = $derived.by(() => {
    const groups: { letter: string; people: typeof contacts }[] = []
    for (const contact of matching) {
      const letter = contact.name[0].toUpperCase()
      const last = groups.at(-1)
      if (last && last.letter === letter) last.people.push(contact)
      else groups.push({ letter, people: [contact] })
    }
    return groups
  })
</script>

<div class="phone">
  <Card eyebrow="Favourites">
    <div class="people">
      {#each favourites as person (person.name)}
        <button
          class="favourite"
          onclick={() => (selected = person.name)}
        >
          <Avatar
            name={person.name}
            size={52}
            active={selected === person.name}
          />
          <span class="name">{person.short}</span>
        </button>
      {/each}
    </div>
  </Card>

  <div class="columns">
    <Card eyebrow="Recent" gap="none" trim class="list">
      {#each recent as call (call.name + call.when)}
        <div class="call">
          <Avatar name={call.name} size={40} />
          <div class="labels">
            <div class="who">{call.name}</div>
            <div class="detail" class:missed={call.kind === 'Missed'}>
              {call.kind} · {call.when}
            </div>
          </div>
        </div>
      {/each}
    </Card>

    <!-- No search field: the keypad filters this list, as on a
         handset. A second way in would only raise the question of
         which one is filtering. -->
    <Card gap="none" class="list">
      <div class="head">
        <span class="eyebrow">Contacts</span>
        {#if typed}
          <span class="filtered">
            {matching.length} of {contacts.length}
          </span>
        {/if}
      </div>

      <div class="scroll">
        {#each grouped as group (group.letter)}
          <div class="letter">{group.letter}</div>
          {#each group.people as contact (contact.number)}
            <button class="contact">
              <Avatar name={contact.name} size={40} />
              <span class="labels">
                <span class="who">{contact.name}</span>
                <span class="detail">{contact.number}</span>
              </span>
            </button>
          {/each}
        {:else}
          <p class="empty">
            No contacts match {dialled}
          </p>
        {/each}
      </div>
    </Card>

    <Card eyebrow="Keypad" gap="none" class="keypad">

      <div class="entry">
        <span class="dialled" class:empty={!dialled}>
          {dialled || 'Enter a number'}
        </span>

        {#if dialled}
          <button
            class="erase"
            aria-label="Delete last digit"
            onclick={() => (dialled = dialled.slice(0, -1))}
          >
            <Icon name="backspace" size={20} />
          </button>
        {/if}
      </div>

      <div class="keys">
        {#each keys as key (key.digit)}
          <button
            class="key"
            aria-label={key.hold
              ? `${key.digit}, hold for ${key.hold}`
              : key.digit}
            onclick={() => press(key)}
            onpointerdown={() => startHold(key)}
            onpointerup={endHold}
            onpointerleave={endHold}
            onpointercancel={endHold}
            oncontextmenu={(e) => e.preventDefault()}
          >
            <span class="digit">{key.digit}</span>
            <!-- A blank line rather than none, so 1, * and # are the
                 same height as the rest and their digits sit on the
                 same baseline. -->
            <span class="letters">{key.letters || ' '}</span>
          </button>
        {/each}
      </div>

      <button class="call-button" disabled={!dialled}>
        <Icon name="phone" size={19} />
        Call
      </button>
    </Card>
  </div>
</div>

<style>
  .phone {
    display: grid;
    /* minmax(0, 1fr) rather than 1fr: a bare 1fr floors at the row's
       min-content height, so the contacts list would push the page
       taller than the screen instead of scrolling inside its card. */
    grid-template-rows: auto minmax(0, 1fr);
    gap: var(--spacing-l);
    height: 100%;
    padding: var(--spacing-l);
    min-height: 0;
  }

  .people {
    display: flex;
    gap: 26px;
  }

  .favourite {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 0;
    background: none;
    border: 0;
  }

  .favourite:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 4px;
    border-radius: var(--radius-sm);
  }

  .name {
    font-size: 13px;
    color: var(--text-dim);
  }

  .columns {
    display: grid;
    grid-template-columns: 1fr 1fr 300px;
    /* Declared, because an implicit row is auto -- sized to whichever
       card is tallest. That was the whole bug: the cards grew to fit
       the contacts rather than the contacts scrolling inside them. */
    grid-template-rows: minmax(0, 1fr);
    gap: var(--spacing-l);
    min-height: 0;
  }

  /* :global because these land on the Card component's element. The
     card owns its surface; the page owns how it fills the column. */
  .columns :global(.list),
  .columns :global(.keypad) {
    min-height: 0;
  }




  .scroll {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    margin: 0 calc(var(--spacing-l) * -1);
    padding: 0 var(--spacing-l);
  }

  .call,
  .contact {
    display: flex;
    align-items: center;
    gap: 14px;
    width: 100%;
    padding: 13px 0;
    text-align: left;
    background: none;
    border: 0;
    border-bottom: 1px solid var(--hairline);
  }

  .contact {
    border-bottom: 0;
  }

  .call:last-child {
    border-bottom: 0;
  }

  .contact:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    border-radius: var(--radius-sm);
  }

  .labels {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .who {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .detail {
    font-size: 13px;
    color: var(--text-dim);
  }

  /* The one place colour carries meaning rather than decoration: a
     missed call is the thing you came to this screen to find. */
  .detail.missed {
    color: var(--danger);
  }

  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--spacing-s);
    padding-bottom: var(--spacing-xs);
  }

  /* Only while the keypad is filtering, so the heading is not
     carrying a count that never changes. */
  .filtered {
    font-size: 12px;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }

  .letter {
    padding: 14px 0 4px;
    font-family: var(--font-display);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.18em;
    color: var(--text-faint);
  }

  .empty {
    padding: var(--spacing-l) 0;
    font-size: 14px;
    color: var(--text-faint);
  }

  /* A fixed height, and the prompt set in the same size as the
     digits. Sizing it to its contents meant the keypad below moved
     down the moment the first digit was pressed. */
  .entry {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
    height: 54px;
    padding: 0;
  }

  .dialled {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    font-family: var(--font-display);
    font-size: 22px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.04em;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  .dialled.empty {
    color: var(--text-faint);
    letter-spacing: 0;
  }

  .erase {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    color: var(--text-dim);
    background: none;
    border: 0;
    border-radius: 50%;
  }

  .erase:active {
    background: var(--panel-2);
  }

  .erase:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .keys {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    /* Four equal rows sharing whatever the card gives, rather than
       four auto rows each as tall as its key. */
    grid-template-rows: repeat(4, minmax(0, 1fr));
    gap: 8px;
    flex: 1;
    min-height: 0;
  }

  .key {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1px;
    min-height: 62px;
    background: var(--panel-2);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .key:active {
    background: var(--chip);
  }

  .key:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }

  .digit {
    font-family: var(--font-display);
    font-size: 21px;
    font-weight: 600;
  }

  /* Present on every key, blank where there are no letters, so the
     digits line up across the pad instead of the unlettered ones
     floating in the middle of their button. */
  .letters {
    height: 12px;
    font-size: 9px;
    line-height: 12px;
    letter-spacing: 0.14em;
    color: var(--text-faint);
  }

  .call-button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    height: 52px;
    margin-top: var(--spacing-s);
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent-ink);
    background: var(--accent);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .call-button:disabled {
    /* Dimmed rather than hidden: the button is where the eye expects
       it, it just has nothing to dial yet. */
    opacity: 0.45;
    cursor: default;
  }

  .call-button:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>
