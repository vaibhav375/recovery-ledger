/// <reference types="vite/client" />

/* The one build-time variable this app reads. Declared rather than inferred so
   a typo in the name is a type error instead of an empty string at runtime. */
interface ImportMetaEnv {
  /** Where the live console is hosted, for page copies that cannot run a
   *  backend. Empty on a local build, which is the correct default: the
   *  offline branch then explains running it yourself. */
  readonly VITE_LIVE_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
