/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_HOST_MODE?: 'oss' | 'platform';
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string;
  readonly VITE_AUTH_USER_ID?: string;
  readonly VITE_CDN_BASE?: string;
  // Parent domain shared by all first-party cookies (auth + locale). Unset →
  // host-only (the default); set to a parent domain for cross-subdomain SSO.
  readonly VITE_COOKIE_DOMAIN?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}

