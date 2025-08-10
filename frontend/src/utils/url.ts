export const extractItemIdFromUrl = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    return parsed.searchParams.get('id');
  } catch {
    return null;
  }
};

export const extractDrivePathFromUrl = (url: string): string | null => {
  // Supports URLs like:
  // https://onedrive.live.com/?id=%2Fpersonal%2F...%2FPictures%2FtestingVOB2&sortField=...
  // We ignore the /personal/.../Documents prefix and return /Pictures/testingVOB2
  try {
    const parsed = new URL(url);
    const rawId = parsed.searchParams.get('id');
    if (!rawId) return null;
    const decoded = decodeURIComponent(rawId);
    // Find the Documents segment and take everything after it
    const marker = '/Documents';
    const idx = decoded.toLowerCase().indexOf(marker.toLowerCase());
    if (idx === -1) return null;
    const after = decoded.substring(idx + marker.length);
    return after.startsWith('/') ? after : `/${after}`;
  } catch {
    return null;
  }
};

export const isValidOneDriveUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    const id = parsed.searchParams.get('id');
    if (!parsed.hostname.includes('onedrive') || !id) return false;
    // Accept either an item-id style (contains '!') or a path-encoded style (starts with %2F or /)
    return id.includes('!') || id.startsWith('%2F') || id.startsWith('/');
  } catch {
    return false;
  }
};

export type OneDriveUrlInfo =
  | { kind: 'itemId'; itemId: string }
  | { kind: 'path'; path: string };

export const parseOneDriveUrl = (url: string): OneDriveUrlInfo | null => {
  try {
    const parsed = new URL(url);
    const id = parsed.searchParams.get('id');
    if (!id) return null;

    // Item-ID style: typically contains '!'
    if (id.includes('!')) {
      return { kind: 'itemId', itemId: id };
    }

    // Path-encoded style: starts with %2F or '/' and includes '/Documents'
    if (id.startsWith('%2F') || id.startsWith('/')) {
      const decoded = decodeURIComponent(id);
      const marker = '/Documents';
      const idx = decoded.toLowerCase().indexOf(marker.toLowerCase());
      const after = idx !== -1 ? decoded.substring(idx + marker.length) : decoded;
      const normalized = after.startsWith('/') ? after : `/${after}`;
      return { kind: 'path', path: normalized };
    }

    // Fallback: treat as itemId
    return { kind: 'itemId', itemId: id };
  } catch {
    return null;
  }
};