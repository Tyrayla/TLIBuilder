// The hosted service sends the browser back to the web app with ?auth_error=<reason> after a failed
// sign-in and ?reauth=ok after a fresh Discord confirmation. Only known reasons become text, so a
// crafted link cannot put arbitrary words on screen.
export const AUTH_ERROR_MESSAGE: Record<string, string> = {
  cancelled: 'Sign-in was cancelled.',
  discord_failed: 'Discord could not confirm your sign-in. Try again.',
  signup_closed: 'Sign-up is not open yet.',
  reauth_failed: 'Discord could not confirm it is you. Try again.',
  unknown: 'Sign-in did not complete. Try again.',
}

export function consumeAuthReturn(href: string): { authError: string | null; reauthOk: boolean; cleanedHref: string | null } {
  let url: URL
  try { url = new URL(href) } catch { return { authError: null, reauthOk: false, cleanedHref: null } }
  const rawError = url.searchParams.get('auth_error')
  const rawReauth = url.searchParams.get('reauth')
  if (rawError === null && rawReauth === null) return { authError: null, reauthOk: false, cleanedHref: null }

  const authError = rawError === null ? null : (rawError in AUTH_ERROR_MESSAGE && rawError !== 'unknown' ? rawError : 'unknown')
  url.searchParams.delete('auth_error')
  url.searchParams.delete('reauth')
  return { authError, reauthOk: rawReauth === 'ok', cleanedHref: url.toString() }
}
