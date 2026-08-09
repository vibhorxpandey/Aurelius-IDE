/**
 * Vite bundles workers as separate modules via the `?worker` suffix; Monaco expects to
 * find one through `self.MonacoEnvironment.getWorker`. Skipping this doesn't break basic
 * editing — Monarch tokenizers run on the main thread regardless — but it does spam the
 * console with "Could not create web worker(s)" on every launch, which is exactly the kind
 * of rough edge a "make it professional" prototype shouldn't ship with.
 *
 * Only the generic editor worker is wired: nothing here uses the JSON/CSS/HTML/TS language
 * services those workers exist for.
 */
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

// monaco-editor's own types already declare the global `MonacoEnvironment` shape
// (`Environment | undefined`); redeclaring it here would conflict rather than narrow it.
self.MonacoEnvironment = {
  getWorker() {
    return new EditorWorker();
  },
};
