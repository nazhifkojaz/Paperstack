/**
 * URL parsing and manipulation utilities.
 * Provides safe, typed functions for common URL operations.
 */

/**
 * Safely extracts the hostname from a URL string.
 * If the string is not a valid URL, returns the original string.
 *
 * @example
 * getHostname("https://arxiv.org/abs/2301.00001") // "arxiv.org"
 * getHostname("not-a-url") // "not-a-url"
 *
 * @param url - The URL string to parse
 * @returns The hostname if valid URL, otherwise the original string
 */
export function getHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    // Invalid URL or malformed string
    return url;
  }
}

/**
 * Checks if a string is a valid URL.
 *
 * @param str - The string to validate
 * @returns true if the string is a valid URL, false otherwise
 */
export function isValidUrl(str: string): boolean {
  try {
    new URL(str);
    return true;
  } catch {
    return false;
  }
}
