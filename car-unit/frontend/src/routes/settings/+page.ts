import { redirect } from '@sveltejs/kit'

/* /settings has no content of its own -- the layout is the nav and
   the sections are the pages. Land on the first one. */
export const load = () => {
  redirect(307, '/settings/display')
}
