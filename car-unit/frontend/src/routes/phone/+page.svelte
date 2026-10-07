<script lang="ts">
  import Icon from '$lib/Icon.svelte'
  import Avatar from '$lib/ui/Avatar.svelte'
  import Button from '$lib/ui/Button.svelte'
  import Dialog from '$lib/ui/Dialog.svelte'
  import Card from '$lib/ui/Card.svelte'
  import { untrack } from 'svelte'
  import {
    bookOf,
    choose,
    isSyncing,
    numberOf,
    open as openPhonebook,
    phonebook,
    phones,
    refresh,
  } from '$lib/phonebook.svelte'
  import type { Contact } from '$lib/api/types'
  import Spinner from '$lib/ui/Spinner.svelte'
  import {
    call as phoneCall,
    canCall,
    dial as placeCall,
    onEnded,
  } from '$lib/call.svelte'

  /* The cache first, then whatever the phone sends.
   *
   * Opening this reads all three books from the daemon's cache --
   * instant -- and then pulls in the background: the call log every
   * time, the address book and favourites once a session. Nothing
   * here waits for a transfer. */
  /* Untracked. Opening reads the Bluetooth device list to choose a
     phone, and without this every Bluetooth event -- which arrive
     for battery levels and signal as well as connections -- would
     re-open the screen, emptying the lists and pulling the call log
     again. */
  $effect(() => {
    untrack(() => openPhonebook())
  })

  const connected = $derived(phones())

  /* Only when the phone being shown goes away. A second phone
     connecting leaves the choice alone -- the person looking at the
     screen chose, or at least has not objected -- and one going
     away moves to whatever is left. */
  $effect(() => {
    const list = connected
    untrack(() => {
      if (!list.some((phone) => phone.address === phonebook.address)) {
        choose(list[0]?.address ?? '')
      }
    })
  })

  /* Swedish ordering, so å ä ö come after z rather than beside a.
     Built once: a collator is not cheap and this runs per
     comparison. */
  const collator = new Intl.Collator('sv', { sensitivity: 'base' })

  /**
   * By name, with anything that does not start with a letter first.
   *
   * A contact named with an emoji or a symbol is one somebody marked
   * deliberately -- it is the closest thing a phonebook has to
   * pinning. Sorting by codepoint would bury them at the very end,
   * past z and the Swedish vowels, which is the opposite of what
   * putting a star in front of a name means.
   *
   * Nameless ones go last: a number saved without a name is the one
   * entry nobody is looking for.
   */
  function byName(a: Contact, b: Contact): number {
    /* Three ranks, not two. A contact with no name at all starts
       with no letter either, so it would ride up with the starred
       ones -- and a blank row at the top of the list is the least
       useful place for the least identifiable entry. */
    const rank = (name: string) =>
      !name ? 2 : /^\p{L}/u.test(name) ? 1 : 0

    const order = rank(a.name) - rank(b.name)
    if (order) return order

    return collator.compare(a.name, b.name)
  }

  /* Only what can be rung.
   *
   * A vCard with no TEL is an email-only contact or a note somebody
   * kept in the address book -- real, and useless in a car. Dropped
   * rather than shown as a row that does nothing when tapped. */
  const callable = (list: Contact[]) =>
    list.filter((contact) => contact.numbers.length > 0)

  const favourites = $derived(
    callable(bookOf('fav').contacts).sort(byName),
  )
  /* Not filtered: a call from a withheld number has no number to
     store, and hiding it would lose the fact that it happened. */
  const recent = $derived(bookOf('cch').contacts)
  const contacts = $derived(callable(bookOf('pb').contacts).sort(byName))

  let selected = $state('')

  /* A first name for the strip, where there is room for one word.
     The whole name goes under the avatar otherwise and the row turns
     into a paragraph. */
  const short = (contact: Contact) =>
    contact.name.split(/\s+/)[0] || contact.name

  /* Whether a call was answered, missed, or made. PBAP labels these
     differently across phones, so this matches loosely rather than
     expecting one spelling. */
  /* Null on an ordinary contact -- most of them -- so this is asked
     of things that have no answer, and has to cope rather than
     assume a call log. */
  const missed = (contact: Contact) =>
    (contact.call_type ?? '').toLowerCase().includes('missed')

  /* What PBAP calls them, and what anyone else would.
   *
   * `dialed`, `received` and `missed` are what the vCard actually
   * carries -- one L, and "received" rather than "incoming". The
   * other spellings are there because phones differ and a word
   * shown raw is better than a blank, but these three are the ones
   * that arrive. */
  const CALL_WORDS: Record<string, string> = {
    received: 'Incoming',
    incoming: 'Incoming',
    dialed: 'Outgoing',
    dialled: 'Outgoing',
    outgoing: 'Outgoing',
    missed: 'Missed',
  }

  const callKind = (contact: Contact) => {
    const kind = (contact.call_type ?? '').toLowerCase()
    return CALL_WORDS[kind] || contact.call_type || 'Call'
  }

  /* Which way the call went, as a mark rather than a word.
   *
   * The word is under the name already; this is for reading the list
   * at a glance, which is what anyone does with a call log. Nothing
   * for a direction nobody recognised -- an icon that means "we are
   * not sure" is worse than a gap. */
  const CALL_ICONS: Record<string, string> = {
    Incoming: 'call-in',
    Outgoing: 'call-out',
    Missed: 'call-missed',
  }

  const callIcon = (contact: Contact) => CALL_ICONS[callKind(contact)] ?? ''

  /**
   * When a call happened, as somebody would say it.
   *
   * Today and yesterday by name, because a clock time alone is
   * ambiguous the moment a day has passed, and a full date is more
   * than anyone needs for something from this morning.
   */
  function when(iso: string | null): string {
    if (!iso) return ''

    const at = new Date(iso)
    if (Number.isNaN(at.getTime())) return ''

    const clock = at.toLocaleTimeString('sv-SE', {
      hour: '2-digit',
      minute: '2-digit',
    })

    const midnight = new Date()
    midnight.setHours(0, 0, 0, 0)
    const days = Math.floor(
      (midnight.getTime() - at.getTime()) / 86_400_000,
    )

    if (days < 0) return `Today · ${clock}`
    if (days < 1) return `Yesterday · ${clock}`

    return `${at.toLocaleDateString('sv-SE', {
      day: 'numeric',
      month: 'short',
    })} · ${clock}`
  }

  /* The contact being looked at, or null. Any of the three lists
     opens this -- they hold the same thing, and a row that showed
     its detail in one list and not another would be arbitrary. */
  let showing = $state<Contact | null>(null)

  /* Names the vCard uses for a number, and what anyone else calls
     them. Anything unrecognised is shown as it arrived: phones
     invent these, and a label from the phone is better than none. */
  const NUMBER_WORDS: Record<string, string> = {
    cell: 'Mobile',
    mobile: 'Mobile',
    home: 'Home',
    work: 'Work',
    voice: 'Phone',
    fax: 'Fax',
    pref: 'Preferred',
  }

  const numberLabel = (type: string) =>
    NUMBER_WORDS[type.toLowerCase()] || type || 'Phone'

  /**
   * A number as the ways somebody might type it.
   *
   * The book holds +46701234567; the keypad gets 070 123 45 67,
   * because that is what is written on everything and what anyone
   * dialling from memory presses. Neither string contains the other,
   * so a search for one finds nothing stored as the other.
   *
   * The national form is a 0 in place of the country code -- but the
   * country code is one to three digits and the number does not say
   * which. Taking a fixed number of digits from the end does not
   * work either: a Stockholm landline's national part is shorter
   * than a mobile's, so +4684112233 would come out 0684112233
   * rather than 084112233.
   *
   * So all three are offered. Over-generating costs a filter a
   * couple of extra candidates; guessing one and being wrong costs
   * somebody their contact.
   */
  function forms(number: string): string[] {
    let digits = number.replace(/\D/g, '')

    // 00 and + are the same prefix written differently.
    if (digits.startsWith('00')) digits = digits.slice(2)

    const all = [digits]
    for (const code of [1, 2, 3]) {
      if (digits.length > code + 4) all.push(`0${digits.slice(code)}`)
    }

    return all
  }

  /**
   * Whether two numbers are the same one.
   *
   * The same phone is written +46701234567 in the address book and
   * 070-123 45 67 in the call log, and neither is wrong. Both are
   * reduced to what is left after the country code or the trunk 0,
   * and the shorter counts as the same phone when the longer ends
   * with it.
   *
   * Comparing a fixed number of digits from the end does not work:
   * a Stockholm landline's national part is shorter than a mobile's,
   * so the same rule cannot serve both.
   */
  function sameNumber(a: string, b: string): boolean {
    const core = (raw: string) => {
      let digits = raw.replace(/\D/g, '')
      if (digits.startsWith('00')) digits = digits.slice(2)
      return digits.replace(/^0+/, '')
    }

    const left = core(a)
    const right = core(b)
    if (!left || !right) return false

    /* Short ones must match outright. There is nothing to trim off a
       three-digit number, and treating 112 as a suffix of anything
       would match half the book. */
    const [short, long] =
      left.length <= right.length ? [left, right] : [right, left]

    if (short.length < 6) return short === long

    /* Otherwise the shorter is the same phone if the longer ends
       with it: the difference between them is a country code, which
       is on the front. */
    return long.endsWith(short)
  }

  /**
   * Every call with this contact, newest first.
   *
   * Matched on the number rather than the name: a call from someone
   * not in the address book has no name to match, and a contact
   * renamed since the call was logged would lose its history.
   *
   * The log is already newest first from the daemon, so the filter
   * keeps that order.
   */
  function historyFor(contact: Contact) {
    const wanted = contact.numbers.map((n) => n.number)
    if (!wanted.length) return []

    return recent.filter((call) =>
      call.numbers.some((n) =>
        wanted.some((mine) => sameNumber(mine, n.number)),
      ),
    )
  }

  /* Calls go from the phone whose books are showing -- with two
     connected, the one chosen above. Empty means the only one, which
     the daemon picks when there is just one. */
  const from = $derived(phonebook.address || undefined)
  const canPlace = $derived(canCall(from))

  /** Why calling is not possible, said where the buttons are. */
  const cannot = $derived(
    canPlace
      ? ''
      : from && phoneCall.status.available
        ? 'This phone is not connected for calls'
        : 'No phone connected for calls',
  )

  /* What went wrong placing a call, where it was placed from: before
     the call exists there is no card to say it on. */
  let keypadError = $state('')
  let sheetError = $state('')

  /* Each about what was tried: gone once the number changes, or the
     contact sheet does. */
  $effect(() => {
    void dialled
    keypadError = ''
  })
  $effect(() => {
    void showing
    sheetError = ''
  })

  /* A contact's number calls straight away -- one tap while driving
     rather than two. The card that appears has End, which undoes it. */
  async function dial(number: string): Promise<void> {
    sheetError = ''
    const error = await placeCall(number, from)
    if (error) sheetError = error
    else showing = null
  }

  async function callDialled(): Promise<void> {
    keypadError = ''
    const error = await placeCall(dialled, from)
    if (error) keypadError = error
  }

  /* The recent calls, refreshed once a call on this phone is over:
     the phone has written it into its log by then. */
  $effect(() =>
    onEnded((phone) => {
      if (phone !== phonebook.address) return
      setTimeout(() => refresh('cch'), 2000)
    }),
  )

  /* Derived rather than computed in the markup: {@const} is only
     allowed as the immediate child of a block, and this belongs
     several elements deep inside one. */
  const history = $derived(showing ? historyFor(showing) : [])

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
          /* Every number, not just the first: the one somebody is
             half-remembering is as likely to be the work line. */
          if (
            contact.numbers.some((n) =>
              forms(n.number).some((form) => form.includes(typed)),
            )
          ) {
            return true
          }
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
    const groups: { letter: string; people: Contact[] }[] = []
    for (const contact of matching) {
      /* The first character as it is, upper-cased only when it is a
         letter. An emoji has no case, and calling toUpperCase on one
         is a no-op that reads as though it might not be.

         A vCard with no name is rare and real -- a number saved
         without one -- and is filed under # rather than crashing on
         [0] of an empty string. */
      const first = [...contact.name][0] ?? ''
      const letter = first
        ? /\p{L}/u.test(first)
          ? first.toUpperCase()
          : first
        : '#'
      const last = groups.at(-1)
      if (last && last.letter === letter) last.people.push(contact)
      else groups.push({ letter, people: [contact] })
    }
    return groups
  })
</script>

<!-- One control, used by both books that are not pulled every time.
     A spinner in its place while it runs, so the button cannot be
     pressed twice and there is somewhere for the wait to show. -->
{#snippet refreshButton(book: 'pb' | 'fav', label: string)}
  <!-- The same button throughout, with its icon turning.
       
       Swapping it for a spinner changes the shape of the head row,
       so the title beside it shifts every time a sync starts and
       stops -- on a screen whose whole job is a list that is already
       moving. -->
  <!-- Small, beside the title rather than at the end of the row. A
       full-size button sets the height of the whole heading, and a
       control used once a week does not earn that. The hit area is
       padded out past the icon so it stays easy to catch. -->
  <button
    class="refresh"
    aria-label={isSyncing(book) ? 'Refreshing' : label}
    disabled={isSyncing(book) || !bookOf(book).available}
    onclick={() => refresh(book)}
  >
    <span class="turn" class:spinning={isSyncing(book)}>
      <Icon name="refresh" size={16} />
    </span>
  </button>
{/snippet}

<!-- No title bar: the name sits beside the avatar, which reads as
     one thing, and a heading above it would be the same words twice.
     `title` still goes through as the dialog's label, for anything
     that announces it rather than draws it. -->
<Dialog
  open={!!showing}
  bare
  title={showing ? showing.name || numberOf(showing) || 'Contact' : ''}
  width={520}
  onclose={() => (showing = null)}
>
  {#if showing}
    <div class="detail-body">
      <div class="who-header">
        <Avatar name={showing.name || numberOf(showing)} size={64} />
        <div class="who-labels">
          <p class="who-name">{showing.name || 'No name'}</p>
          {#if showing.call_time}
            <p class="who-call" class:missed={missed(showing)}>
              {callKind(showing)} · {when(showing.call_time)}
            </p>
          {/if}
        </div>
      </div>

      {#if showing.numbers.length}
        <ul class="numbers">
          {#each showing.numbers as entry, index (index)}
            <!-- Every number, not just the first. Which one to ring
                 is the question this dialog exists to answer. -->
            <li>
              <button
                class="number"
                disabled={!canPlace || !!phoneCall.busy}
                onclick={() => dial(entry.number)}
              >
                <span class="number-labels">
                  <span class="number-type">
                    {numberLabel(entry.type)}
                  </span>
                  <span class="number-value">{entry.number}</span>
                </span>
                <Icon name="phone" size={20} />
              </button>
            </li>
          {/each}
        </ul>
        {#if cannot || sheetError}
          <p class="call-error">{cannot || sheetError}</p>
        {/if}
      {:else}
        <p class="empty">No number for this contact</p>
      {/if}

      {#if showing.emails.length}
        <!-- Shown because it is there, not because the car can do
             anything with it. Somebody checking whether they have
             the right person is served by seeing it. -->
        <ul class="emails">
          {#each showing.emails as email, index (index)}
            <li>{email}</li>
          {/each}
        </ul>
      {/if}

      <!-- At the bottom, because it is the part somebody scrolls to
           rather than the part they opened this for. -->
      {#if history.length}
        <div class="history">
          <p class="history-head">Recent calls</p>
          <ul>
            {#each history as call, index (index)}
              <li class="history-row">
                {#if callIcon(call)}
                  <span class="direction" class:missed={missed(call)}>
                    <Icon name={callIcon(call)} size={18} />
                  </span>
                {/if}
                <span class="history-kind" class:missed={missed(call)}>
                  {callKind(call)}
                </span>
                <span class="history-when">{when(call.call_time)}</span>
              </li>
            {/each}
          </ul>
        </div>
      {:else if showing.numbers.length}
        <p class="history-none">No calls with this number</p>
      {/if}
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="quiet" onclick={() => (showing = null)}>Close</Button>
  {/snippet}
</Dialog>

<div class="phone">
  <div class="top">
  <Card gap="s" class="favourites-card">
    <div class="head">
      <span class="title">
        <span class="eyebrow">Favourites</span>
        {@render refreshButton('fav', 'Refresh favourites')}
      </span>
    </div>

    {#if favourites.length}
      <div class="people">
        <!-- Keyed by position, not by anything about the contact.
             A phonebook has no unique key: the same person is
             often saved twice, and PBAP hands back whatever the
             phone holds. These lists are replaced wholesale on
             every sync and filter, so there is nothing for an
             identity key to preserve anyway. -->
        {#each favourites as person, index (index)}
          <button
            class="favourite"
            onclick={() => {
              selected = person.name
              showing = person
            }}
          >
            <Avatar
              name={person.name}
              size={52}
              active={selected === person.name}
            />
            <span class="name">{short(person)}</span>
          </button>
        {/each}
      </div>
    {:else}
      <!-- Empty is normal rather than broken: Android does not serve
           a favourites book over PBAP at all. -->
      <p class="empty">
        {bookOf('fav').available
          ? 'This phone does not share favourites'
          : 'No phone connected'}
      </p>
    {/if}

    <!-- One line for all three books, in the only card that spans the
         width. A transfer that failed says nothing otherwise, and the
         lists simply stay as they were -- which looks like nothing
         happened rather than something going wrong. -->
    {#if phonebook.error}
      <p class="warning">{phonebook.error}</p>
    {/if}
  </Card>

  <!-- Always there, so the screen says whose phonebook this is even
       with one phone -- and so the layout does not change shape when
       a second connects. -->
  <Card gap="s" class="picker-card">
    <span class="eyebrow">Phone</span>
    {#if connected.length}
      <div class="phones">
        {#each connected as phone (phone.address)}
          <button
            class="phone-choice"
            class:chosen={phone.address === phonebook.address}
            aria-pressed={phone.address === phonebook.address}
            onclick={() => choose(phone.address)}
          >
            <Icon name="phone" size={18} />
            <span class="phone-name">{phone.name || phone.address}</span>
          </button>
        {/each}
      </div>
    {:else}
      <p class="empty">None connected</p>
    {/if}
  </Card>
  </div>

  <div class="columns">
    <!-- Pulled every time this screen opens. A list of recent calls
         that is ten minutes old is not a list of recent calls. -->
    <Card gap="none" class="list">
      <!-- No mark while it syncs. This one pulls on its own every
           time the screen opens, so a spinner would be showing on
           arrival every time -- saying that the car is doing what it
           always does, next to a list that is already there from the
           cache. -->
      <div class="head">
        <span class="eyebrow">Recent</span>
      </div>

      <div class="scroll">
        {#each recent as call, index (index)}
          <button class="call" onclick={() => (showing = call)}>
            <Avatar name={call.name || numberOf(call)} size={40} />
            <span class="labels">
              <span class="who">{call.name || numberOf(call)}</span>
              <span class="detail" class:missed={missed(call)}>
                {callKind(call)} · {when(call.call_time)}
              </span>
            </span>

            <!-- On the right, where the eye ends up after the name
                 and the time. A missed call takes the same red as
                 its line, so the row reads as one thing. -->
            {#if callIcon(call)}
              <span class="direction" class:missed={missed(call)}>
                <Icon name={callIcon(call)} size={20} />
              </span>
            {/if}
          </button>
        {:else}
          <p class="empty">
            {bookOf('cch').available
              ? 'No recent calls'
              : 'No phone connected'}
          </p>
        {/each}
      </div>
    </Card>

    <!-- No search field: the keypad filters this list, as on a
         handset. A second way in would only raise the question of
         which one is filtering. -->
    <Card gap="none" class="list">
      <div class="head">
        <span class="title">
          <span class="eyebrow">Contacts</span>
          {@render refreshButton('pb', 'Refresh contacts')}
        </span>
        {#if typed}
          <span class="filtered">
            {matching.length} of {contacts.length}
          </span>
        {/if}
      </div>

      <div class="scroll">
        <!-- By position too. A letter is unique only because the
             daemon sorts the book; keying on it would make this
             list depend on that from a file away. -->
        {#each grouped as group, groupIndex (groupIndex)}
          <div class="letter">{group.letter}</div>
          {#each group.people as contact, index (index)}
            <button class="contact" onclick={() => (showing = contact)}>
              <Avatar name={contact.name || numberOf(contact)} size={40} />
              <span class="labels">
                <span class="who">{contact.name || numberOf(contact)}</span>
                <span class="detail">{numberOf(contact)}</span>
              </span>
            </button>
          {/each}
        {:else}
          <p class="empty">
            {#if typed}
              No contacts match {dialled}
            {:else if !bookOf('pb').available}
              No phone connected
            {:else if isSyncing('pb')}
              Reading the phonebook
            {:else}
              Nothing here yet — tap refresh
            {/if}
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

      <button
        class="call-button"
        disabled={!dialled || !canPlace || !!phoneCall.busy}
        onclick={callDialled}
      >
        {#if phoneCall.busy === 'dial'}
          <Spinner size={18} label="Calling" />
        {:else}
          <Icon name="phone" size={19} />
        {/if}
        Call
      </button>
      <!-- Why it cannot call now first: an error from a try before the
           phone went is no longer the reason. -->
      {#if (dialled && cannot) || keypadError}
        <p class="call-error">{(dialled && cannot) || keypadError}</p>
      {/if}
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

  /* Sideways rather than wrapping: a long favourites list is rare,
     and when it happens a row that scrolls keeps the screen the same
     shape as one that does not. The favourites no longer have the
     full width to themselves when a phone picker is showing. */
  .people {
    display: flex;
    gap: 26px;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .people::-webkit-scrollbar {
    display: none;
  }

  .favourite {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    /* Keeps its width rather than being squeezed to fit, or a long
       list would shrink every avatar instead of scrolling. */
    flex-shrink: 0;
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

  /* Both are buttons now -- a call in the list is something to ring
     back, not a label. A button inherits neither colour nor font, so
     both are said here. */
  .call,
  .contact {
    display: flex;
    align-items: center;
    gap: 14px;
    width: 100%;
    padding: 13px 0;
    font: inherit;
    color: inherit;
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

  .call:focus-visible,
  .contact:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    border-radius: var(--radius-sm);
  }

  .call:active,
  .contact:active {
    background: var(--panel-2);
  }

  /* Pushed right by the labels growing, and given its own column so
     a long name never squeezes it out. */
  .direction {
    display: grid;
    place-items: center;
    flex-shrink: 0;
    color: var(--text-faint);
  }

  .direction.missed {
    color: var(--danger);
  }

  .labels {
    display: flex;
    flex-direction: column;
    gap: 2px;
    /* Takes the slack, so anything after it is pushed to the far
       edge rather than sitting against the text. */
    flex: 1;
    min-width: 0;
  }

  /* Truncated, because something sits beside these now: a long name
     or a scrolling radiotext-length detail would otherwise push the
     direction mark off the end of the row. */
  .who,
  .detail {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
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

  /* Title on the left, a count on the right when there is one. */
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing-s);
    padding-bottom: var(--spacing-xs);
  }

  /* The eyebrow and its refresh, as one thing. */
  .title {
    display: flex;
    align-items: center;
    gap: 2px;
  }

  /* Sized to the eyebrow rather than to a finger, with the target
     padded out beyond what is drawn. Negative margin so the padding
     does not push the heading taller than the text. */
  .refresh {
    display: grid;
    place-items: center;
    padding: 8px;
    margin: -8px 0;
    color: var(--text-faint);
    background: none;
    border: 0;
    border-radius: var(--radius-sm);
  }

  .refresh:active:not(:disabled) {
    color: var(--text);
  }

  .refresh:disabled {
    cursor: default;
  }

  .refresh:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
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

  /* Favourites take the room; the picker takes what it needs. */
  .top {
    display: flex;
    gap: var(--spacing-l);
    min-width: 0;
  }

  .top :global(.favourites-card) {
    flex: 1;
    min-width: 0;
  }

  .top :global(.picker-card) {
    flex-shrink: 0;
    max-width: 260px;
  }

  .phones {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }

  .phone-choice {
    display: flex;
    align-items: center;
    gap: var(--spacing-s);
    min-height: 46px;
    padding: 0 var(--spacing);
    font: inherit;
    color: var(--text-dim);
    text-align: left;
    background: var(--panel-2);
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
  }

  .phone-choice.chosen {
    color: var(--accent);
    border-color: var(--accent);
  }

  .phone-choice:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .phone-name {
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }

  /* Turning in place rather than being replaced by something that
     turns. The box is the icon's own, so nothing around it moves. */
  .turn {
    display: grid;
    place-items: center;
  }

  .spinning {
    animation: turn 900ms linear infinite;
  }

  @keyframes turn {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .spinning {
      animation-duration: 3s;
    }
  }

  .warning {
    margin: 0;
    font-size: 13px;
    color: var(--danger);
  }

  /* Its own padding, because a bare dialog has none: the panel is
     just a frame and what goes in it decides its own inset. */
  .detail-body {
    display: flex;
    flex-direction: column;
    gap: var(--spacing);
    padding: var(--spacing-l);
    padding-bottom: var(--spacing-s);
  }

  .who-header {
    display: flex;
    align-items: center;
    gap: var(--spacing);
  }

  .who-labels {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }

  .who-name {
    margin: 0;
    font-family: var(--font-display);
    font-size: 20px;
    font-weight: 600;
  }

  .who-call {
    margin: 0;
    font-size: 13px;
    color: var(--text-dim);
  }

  .who-call.missed {
    color: var(--danger);
  }

  .numbers,
  .emails {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* Tall rows: this is the thing being reached for while moving, and
     a list of numbers is exactly where a near miss rings the wrong
     person. */
  .number {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--spacing);
    width: 100%;
    min-height: 62px;
    padding: 0 var(--spacing);
    font: inherit;
    color: inherit;
    text-align: left;
    background: var(--panel-2);
    border: 0;
    border-radius: var(--radius-sm);
  }

  .number:active {
    background: var(--surface);
  }

  .number:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .number-labels {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .number-type {
    font-size: 12px;
    color: var(--text-dim);
  }

  .number-value {
    font-size: 17px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  .history {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
    padding-top: var(--spacing-s);
    border-top: 1px solid var(--hairline);
  }

  .history ul {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .history-head {
    margin: 0;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-faint);
  }

  /* Three columns rather than a sentence: a list of calls is read by
     scanning down one of them, not across. */
  .history-row {
    display: grid;
    grid-template-columns: 22px 1fr auto;
    align-items: center;
    gap: var(--spacing-s);
    padding: 9px 0;
    font-size: 14px;
    border-bottom: 1px solid var(--hairline);
  }

  .history-row:last-child {
    border-bottom: 0;
  }

  .history-kind.missed {
    color: var(--danger);
  }

  .history-when {
    color: var(--text-dim);
    font-variant-numeric: tabular-nums;
  }

  .history-none {
    margin: 0;
    padding-top: var(--spacing-s);
    font-size: 13px;
    color: var(--text-faint);
    border-top: 1px solid var(--hairline);
  }

  .emails li {
    font-size: 14px;
    color: var(--text-dim);
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

  /* Why a call did not go, or cannot: under what was pressed. */
  .call-error {
    margin: var(--spacing-xs) 0 0;
    font-size: 13px;
    text-align: center;
    color: var(--danger);
  }

  .number:disabled {
    opacity: 0.5;
  }

  .call-button:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>
