/**
 * Centralized configuration values for the Paperstack frontend.
 * All environment variable parsing and defaults should live here.
 */

/**
 * Base URL for API requests.
 * Defaults to '/v1' for production, can be overridden with VITE_API_URL env var.
 */
export const API_URL = import.meta.env?.VITE_API_URL ?? '/v1';

/**
 * Base URL for the application (used for routing).
 * Derived from Vite's BASE_URL, defaults to '/Paperstack'.
 */
export const BASE_URL = import.meta.env?.BASE_URL ?? '/Paperstack';

/**
 * Constructs a full URL for navigation/routing within the app.
 */
export function buildUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
