/** Same-origin paths for both root and subdirectory deployments. */
export function normalizeBase(value: string) {
  if (!/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(value)) throw new Error('Invalid application base path')
  return value
}
export const basePath = normalizeBase(import.meta.env.BASE_URL || '/')
export const apiBase = `${basePath}api/v1`
export const appUrl = (path: string) => basePath + path.replace(/^\/+/, '')
