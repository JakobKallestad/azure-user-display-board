export const extractItemIdFromUrl = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    return parsed.searchParams.get('id');
  } catch {
    return null;
  }
};

export const isValidOneDriveUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    return parsed.hostname.includes('onedrive') && parsed.searchParams.has('id');
  } catch {
    return false;
  }
}; 