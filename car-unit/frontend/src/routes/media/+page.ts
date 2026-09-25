import { redirect } from '@sveltejs/kit';
import { MEDIA_SOURCES } from '$lib/types';
import * as media from '$lib/api/media';

/* /media is the source tabs and nothing else, so land on one.
 *
 * Whichever is playing, if any: arriving here while the phone is
 * playing and being shown an empty Spotify screen would be the wrong
 * answer to a question nobody asked.
 *
 * Runs in the browser -- ssr is off -- so these are ordinary fetches
 * through the same proxy as everything else.
 */

/* Checked in order, so a tie goes to the first listed -- Spotify
   before Bluetooth, since a phone in the same Connect session
   reports the same track and either would be true. */
const PLAYERS = MEDIA_SOURCES.filter((source) => source.id);

/* Where to land when nothing is playing. FM: it needs no phone, no
   network and no pairing, so it is the one thing that is always
   there. */
const FALLBACK = MEDIA_SOURCES[0].href;

export const load = async () => {
  const readings = await Promise.all(
    PLAYERS.map(async (source) => {
      try {
        return await media.now(source.id as string);
      } catch {
        // A source the daemon cannot reach is not a reason to fail
        // the navigation; it just is not the one playing.
        return null;
      }
    })
  );

  const index = readings.findIndex((reading) => reading?.status === 'playing');
  const player = index === -1 ? FALLBACK : PLAYERS[index].href;
  console.log(readings, index, player);

  /* FM rather than the last source used: there is nowhere to keep
     that yet, and being predictable beats guessing. */
  redirect(307, index === -1 ? FALLBACK : PLAYERS[index].href);
};
