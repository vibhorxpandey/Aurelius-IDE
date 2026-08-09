import type { AureliusApi } from "../shared/lsp-types";

declare global {
  interface Window {
    aurelius?: AureliusApi;
  }
}
