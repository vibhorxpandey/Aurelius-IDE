/**
 * A local display identity, not authentication. There is no backend for this prototype to
 * authenticate against, so this deliberately doesn't pretend to be one — no password field,
 * no third-party sign-in buttons impersonating a real provider. It's a name and an
 * institution, kept in localStorage so returning to the app doesn't ask again.
 */
export interface UserProfile {
  name: string;
  institution: string;
  email: string;
  joinedAt: string;
}

const STORAGE_KEY = "aurelius.profile";

const AVATAR_COLOURS = ["#4ec9b0", "#569cd6", "#cc7832", "#c586c0", "#e5c158", "#f14c4c", "#3794ff"];

export function loadProfile(): UserProfile | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as UserProfile) : null;
  } catch {
    return null;
  }
}

export function saveProfile(profile: UserProfile): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  } catch {
    // Storage can be unavailable (private browsing, quota). The session still works;
    // the app just asks again next launch.
  }
}

export function clearProfile(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to recover from here either — worst case, sign-out doesn't persist.
  }
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function avatarColour(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_COLOURS[hash % AVATAR_COLOURS.length];
}
