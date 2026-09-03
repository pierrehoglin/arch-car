import { redirect } from '@sveltejs/kit'

/* /media is the source tabs and nothing else, so land on the first
   one. Which source should be default is a question for when these
   are wired -- probably whichever is actually playing. */
export const load = () => {
  redirect(307, '/media/bluetooth')
}
