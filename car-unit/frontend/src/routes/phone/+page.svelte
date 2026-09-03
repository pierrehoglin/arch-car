<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Avatar from '$lib/ui/Avatar.svelte'
  import Card from '$lib/ui/Card.svelte'

  /* Placeholder throughout. Nothing is wired to the daemon. */

  const favourites = ['Anna', 'Mamma', 'Erik', 'Astrid', 'Service']
  let selected = $state('Anna')

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

  let search = $state('')
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
    { digit: '0', letters: '+' },
    { digit: '#', letters: '' },
  ]

  const matching = $derived(
    contacts.filter((c) =>
      `${c.name} ${c.number}`
        .toLowerCase()
        .includes(search.trim().toLowerCase()),
    ),
  )

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
      {#each favourites as name (name)}
        <button class="favourite" onclick={() => (selected = name)}>
          <Avatar {name} size={52} active={selected === name} />
          <span class="name">{name}</span>
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

    <Card gap="none" class="list">
      <div class="head">
        <div class="eyebrow">Contacts</div>
        <label class="search">
          <Icon name="search" size={16} />
          <input
            type="search"
            placeholder="Search"
            bind:value={search}
            aria-label="Search contacts"
          />
        </label>
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
          <p class="empty">No contacts match “{search}”</p>
        {/each}
      </div>
    </Card>

    <Card eyebrow="Keypad" gap="none" class="keypad">

      <div class="entry" class:empty={!dialled}>
        {dialled || 'Enter a number'}
      </div>

      <div class="keys">
        {#each keys as key (key.digit)}
          <button
            class="key"
            onclick={() => (dialled += key.digit)}
            aria-label={key.digit}
          >
            <span class="digit">{key.digit}</span>
            {#if key.letters}
              <span class="letters">{key.letters}</span>
            {/if}
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
    grid-template-rows: auto 1fr;
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
    gap: var(--spacing-l);
    min-height: 0;
  }

  /* :global because these land on the Card component's element. The
     card owns its surface; the page owns how it fills the column. */
  .columns :global(.list),
  .columns :global(.keypad) {
    min-height: 0;
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
  }

  .search {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-faint);
  }

  .search input {
    width: 120px;
    padding: 6px 0;
    font: inherit;
    font-size: 14px;
    color: var(--text);
    background: none;
    border: 0;
  }

  .search input::placeholder {
    color: var(--text-faint);
  }

  .search input:focus {
    outline: none;
  }

  .search:focus-within {
    color: var(--accent);
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

  .entry {
    padding: 14px 0 12px;
    font-family: var(--font-display);
    font-size: 22px;
    font-variant-numeric: tabular-nums;
    letter-spacing: 0.04em;
  }

  .entry.empty {
    font-family: var(--font-body);
    font-size: 15px;
    letter-spacing: 0;
    color: var(--text-faint);
  }

  .keys {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
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

  .letters {
    font-size: 9px;
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
