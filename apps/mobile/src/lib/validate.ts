/** Client-side checks that mirror the API, so people see plain-language errors early. */

// Deliberately simple: the server does the full check. This catches typos like "a.@b.com",
// "a@b" or a missing "@" before a round trip.
const EMAIL = /^[^\s@.]+(\.[^\s@.]+)*@[^\s@.]+(\.[^\s@.]+)+$/;

export function emailError(email: string): string | null {
  const e = email.trim();
  if (!e) return null;
  return EMAIL.test(e) ? null : "That doesn't look like a valid email address.";
}
