/**
 * One persistent Monaco editor instance hosts whichever tab is active, swapping models
 * rather than remounting — the same pattern VS Code itself uses, and the only one that
 * preserves undo history and scroll position across tab switches. This registry owns the
 * models that instance swaps between.
 *
 * The reverse `uriOf` lookup exists so hover and code-action providers never have to
 * round-trip a URI through `model.uri.toString()` and hope Monaco's percent-encoding
 * matches this app's own `pathToFileUri`. It won't always; comparing by identity avoids
 * the question entirely.
 */
import * as monaco from "monaco-editor";

export class ModelRegistry {
  private models = new Map<string, monaco.editor.ITextModel>();
  private versions = new Map<string, number>();
  private uriByModel = new Map<monaco.editor.ITextModel, string>();

  getOrCreate(uri: string, language: string, content: string): monaco.editor.ITextModel {
    const existing = this.models.get(uri);
    if (existing) return existing;

    const model = monaco.editor.createModel(content, language, monaco.Uri.parse(uri));
    this.models.set(uri, model);
    this.uriByModel.set(model, uri);
    this.versions.set(uri, 1);
    return model;
  }

  get(uri: string): monaco.editor.ITextModel | undefined {
    return this.models.get(uri);
  }

  uriOf(model: monaco.editor.ITextModel): string | undefined {
    return this.uriByModel.get(model);
  }

  bumpVersion(uri: string): number {
    const next = (this.versions.get(uri) ?? 1) + 1;
    this.versions.set(uri, next);
    return next;
  }

  version(uri: string): number {
    return this.versions.get(uri) ?? 1;
  }

  dispose(uri: string): void {
    const model = this.models.get(uri);
    if (model) {
      this.uriByModel.delete(model);
      model.dispose();
    }
    this.models.delete(uri);
    this.versions.delete(uri);
  }
}
