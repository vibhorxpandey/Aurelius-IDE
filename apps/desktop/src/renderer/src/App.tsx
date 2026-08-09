import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as monaco from "monaco-editor";
import type { LspDiagnostic, ServerStatus } from "@shared/lsp-types";
import { getApi, isElectron } from "./platform";
import { LspClient, pathToFileUri, fileUriToPath } from "./lsp/client";
import { ModelRegistry } from "./editor/modelRegistry";
import { applyDiagnostics } from "./editor/diagnostics";
import { registerLanguages } from "./monaco/languages";
import { detectLanguage, basename, type EditorTab } from "./state/types";
import { loadProfile, saveProfile, clearProfile, avatarColour, initials, type UserProfile } from "./state/profile";
import { makeEvent, type ActivityEvent, type ActivityKind } from "./state/activity";

import ActivityBar, { type ActivityView } from "./components/ActivityBar";
import Explorer from "./components/Explorer";
import TabBar from "./components/TabBar";
import EditorPane from "./components/EditorPane";
import StatusBar from "./components/StatusBar";
import ProblemsPanel from "./components/ProblemsPanel";
import BibliographyPanel from "./components/BibliographyPanel";
import GatePanel from "./components/GatePanel";
import DiagramsPanel from "./components/DiagramsPanel";
import AgentActivityPanel from "./components/AgentActivityPanel";
import ExtensionsView from "./components/ExtensionsView";
import MermaidPreview from "./components/MermaidPreview";
import LoginScreen from "./components/LoginScreen";
import ProfilePanel from "./components/ProfilePanel";
import { LogoMark } from "./components/icons";

// Runs once at module load, before any Monaco editor or model is created.
registerLanguages();

const DEBOUNCE_MS = 400;
const ACTIVITY_LOG_CAP = 150;

export default function App() {
  const [profile, setProfile] = useState<UserProfile | null>(() => loadProfile());
  const [profilePanelOpen, setProfilePanelOpen] = useState(false);

  const [rootPath, setRootPath] = useState<string | null>(null);
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [tabs, setTabs] = useState<EditorTab[]>([]);
  const [activeUri, setActiveUri] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ActivityView>("explorer");
  const [problemsCollapsed, setProblemsCollapsed] = useState(false);
  const [bottomTab, setBottomTab] = useState<"problems" | "terminal">("problems");
  const [diagnosticsByUri, setDiagnosticsByUri] = useState<Map<string, LspDiagnostic[]>>(new Map());
  const [refreshToken, setRefreshToken] = useState(0);
  const [revealTarget, setRevealTarget] = useState<{ uri: string; line: number } | null>(null);
  const [mermaidLive, setMermaidLive] = useState("");
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([]);

  const registry = useRef(new ModelRegistry()).current;
  const clientRef = useRef<LspClient | null>(null);
  const debounceTimers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const logActivity = useCallback((kind: ActivityKind, title: string, details: string[] = []) => {
    setActivityLog((prev) => [...prev.slice(-(ACTIVITY_LOG_CAP - 1)), makeEvent(kind, title, details)]);
  }, []);

  // Resolve the workspace once on launch — the bundled demo folder in Electron, or the
  // static preview root when running outside it.
  useEffect(() => {
    void getApi()
      .workspace.defaultPath()
      .then(setRootPath);
  }, []);

  // The LSP client is real only inside Electron. Outside it there is nothing to spawn, so
  // panels are told plainly rather than left spinning forever on a response that never comes.
  useEffect(() => {
    if (!rootPath || !isElectron) return;
    const client = new LspClient(rootPath);
    clientRef.current = client;

    const offStatus = client.onStatus((status) => {
      setServerStatus(status);
      if (status.state === "running") logActivity("connect", "Connected to aurelius-lsp", [status.detail]);
      else if (status.state === "crashed" || status.state === "not-found") {
        logActivity("error", status.state === "crashed" ? "Language server crashed" : "Language server unavailable", [
          status.detail,
        ]);
      }
    });

    const offDiagnostics = client.onDiagnostics((uri, diags) => {
      const model = registry.get(uri);
      if (model) applyDiagnostics(model, diags);
      setDiagnosticsByUri((prev) => {
        const next = new Map(prev);
        next.set(uri, diags);
        return next;
      });
      setRefreshToken((t) => t + 1);

      // The kind is read off which codes are present, not asserted: AUR002/003/004 only
      // ever appear once the network verification pass has landed, so their presence *is*
      // the signal that this batch is the second, slower half of the two-phase split.
      const hasVerification = diags.some((d) => ["AUR002", "AUR003", "AUR004"].includes(d.code));
      const fileName = basename(fileUriToPath(uri));
      const count = diags.length;
      const title = hasVerification
        ? `Checked references in ${fileName} — ${count} finding${count === 1 ? "" : "s"}`
        : `Analyzed ${fileName} — ${count} finding${count === 1 ? "" : "s"}`;
      logActivity(
        hasVerification ? "verified" : "structural",
        title,
        diags.slice(0, 6).map((d) => `[${d.code}] ${d.message}`)
      );
    });

    return () => {
      offStatus();
      offDiagnostics();
      client.dispose();
      clientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rootPath]);

  // Hover — the same "resolve a key against its bibliography entry" the VS Code extension
  // gets, over the same textDocument/hover request, real round trip to the real server.
  useEffect(() => {
    const disposable = monaco.languages.registerHoverProvider("latex", {
      provideHover: async (model, position) => {
        const client = clientRef.current;
        const uri = registry.uriOf(model);
        if (!client || !uri) return null;
        try {
          const result = await client.hover(uri, position.lineNumber - 1, position.column - 1);
          return result ? { contents: [{ value: result.value }] } : null;
        } catch {
          return null;
        }
      },
    });
    return () => disposable.dispose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Guards against a rapid double-click sending textDocument/didOpen twice for the same
  // URI before the first read resolves — pygls treats a second didOpen on an already-open
  // document as an error.
  const pendingOpens = useRef(new Set<string>());

  const openFile = useCallback(
    async (path: string, reveal?: number) => {
      const uri = pathToFileUri(path);
      const language = detectLanguage(path);

      // The model must exist in the registry BEFORE activeUri changes. EditorPane's model
      // swap runs once, on the activeUri transition — if the model isn't there yet, it
      // finds nothing, and because activeUri never changes again, it never gets a second
      // chance to look. Content has to be loaded first; the tab only appears once there is
      // something in it to show.
      if (!registry.get(uri)) {
        if (pendingOpens.current.has(uri)) return;
        pendingOpens.current.add(uri);
        try {
          const content = await getApi().workspace.read(path);
          registry.getOrCreate(uri, language, content);
          if (language !== "mermaid") {
            await clientRef.current?.didOpen(uri, language, registry.version(uri), content);
          }
        } finally {
          pendingOpens.current.delete(uri);
        }
      }

      setTabs((prev) => {
        if (prev.some((t) => t.uri === uri)) return prev;
        return [...prev, { uri, path, name: basename(path), language, dirty: false }];
      });
      setActiveUri(uri);
      if (reveal !== undefined) setRevealTarget({ uri, line: reveal });
    },
    [registry]
  );

  const closeTab = useCallback(
    (uri: string) => {
      clientRef.current?.didClose(uri);
      registry.dispose(uri);
      setTabs((prev) => {
        const next = prev.filter((t) => t.uri !== uri);
        setActiveUri((current) => {
          if (current !== uri) return current;
          return next.length > 0 ? next[next.length - 1].uri : null;
        });
        return next;
      });
    },
    [registry]
  );

  const handleContentChange = useCallback(
    (uri: string, content: string) => {
      setTabs((prev) => prev.map((t) => (t.uri === uri ? { ...t, dirty: true } : t)));

      const timers = debounceTimers.current;
      clearTimeout(timers.get(uri));
      timers.set(
        uri,
        setTimeout(() => {
          const version = registry.bumpVersion(uri);
          clientRef.current?.didChange(uri, version, content);
        }, DEBOUNCE_MS)
      );
    },
    [registry]
  );

  // Keeps the Mermaid split-view preview in sync with the active diagram's source. Kept
  // independent of handleContentChange (which drives LSP didChange) because a .mmd file
  // never goes through the language server at all — it's a client-only preview concern.
  useEffect(() => {
    const tab = tabs.find((t) => t.uri === activeUri);
    if (!tab || tab.language !== "mermaid" || !activeUri) {
      setMermaidLive("");
      return;
    }
    const model = registry.get(activeUri);
    if (!model) return;
    setMermaidLive(model.getValue());
    const disposable = model.onDidChangeContent(() => setMermaidLive(model.getValue()));
    return () => disposable.dispose();
  }, [activeUri, tabs, registry]);

  const saveActive = useCallback(async () => {
    if (!activeUri) return;
    const model = registry.get(activeUri);
    if (!model) return;
    const path = fileUriToPath(activeUri);
    await getApi().workspace.write(path, model.getValue());
    clientRef.current?.didSave(activeUri);
    setTabs((prev) => prev.map((t) => (t.uri === activeUri ? { ...t, dirty: false } : t)));
  }, [activeUri, registry]);

  const revealInEditor = useCallback(
    (uri: string, line: number) => {
      void openFile(fileUriToPath(uri), line);
    },
    [openFile]
  );

  const restartServer = useCallback(() => {
    void getApi().lsp.restart();
  }, []);

  const handleSignOut = useCallback(() => {
    clearProfile();
    setProfile(null);
    setProfilePanelOpen(false);
  }, []);

  const handleLogin = useCallback((p: UserProfile) => {
    saveProfile(p);
    setProfile(p);
  }, []);

  const activeTab = tabs.find((t) => t.uri === activeUri) ?? null;
  const isMermaidActive = activeTab?.language === "mermaid";

  const allDiagnostics = useMemo(() => Array.from(diagnosticsByUri.values()).flat(), [diagnosticsByUri]);
  const errors = allDiagnostics.filter((d) => d.severity === 1).length;
  const warnings = allDiagnostics.filter((d) => d.severity === 2).length;
  const bibliographyProblems = allDiagnostics.filter(
    (d) => d.severity === 1 && ["AUR001", "AUR002", "AUR003", "AUR004"].includes(d.code)
  ).length;
  const gateBlocking = allDiagnostics.filter((d) => d.code === "AUR010").length;
  const latexUri = tabs.find((t) => t.language === "latex")?.uri ?? activeUri;

  if (!profile) {
    return <LoginScreen onContinue={handleLogin} />;
  }

  return (
    <div className="shell">
      <div className="shell__titlebar">
        <span className="shell__titlebar-logo">
          <LogoMark size={16} />
        </span>
        <span className="shell__titlebar-title">Aurelius — prototype desktop shell</span>
        <span
          className="titlebar-avatar"
          style={{ background: avatarColour(profile.name) }}
          title={profile.name}
          onClick={() => setProfilePanelOpen((v) => !v)}
        >
          {initials(profile.name)}
        </span>
      </div>

      {!isElectron && (
        <div className="banner">
          Preview mode: this renderer is running outside Electron, so the file system and
          language server are unavailable. Run <code>npm run dev</code> to see it for real.
        </div>
      )}
      {serverStatus?.state === "not-found" && isElectron && (
        <div className="banner" data-tone="error">
          {serverStatus.detail}
        </div>
      )}

      <div className="shell__body">
        <ActivityBar
          active={activeView}
          onChange={setActiveView}
          bibliographyProblems={bibliographyProblems}
          gateBlocking={gateBlocking}
        />

        <div className="sidebar">
          <div className="sidebar__body">
            {!rootPath ? (
              <div className="sidebar__empty">Loading workspace…</div>
            ) : activeView === "explorer" ? (
              <Explorer rootPath={rootPath} activePath={activeTab?.path ?? null} onOpenFile={(p) => void openFile(p)} />
            ) : activeView === "bibliography" ? (
              <BibliographyPanel
                client={clientRef.current}
                activeUri={latexUri}
                refreshToken={refreshToken}
                onReveal={revealInEditor}
              />
            ) : activeView === "gate" ? (
              <GatePanel
                client={clientRef.current}
                activeUri={latexUri}
                onActivity={(title, details) => logActivity("gate", title, details)}
              />
            ) : activeView === "diagrams" ? (
              <DiagramsPanel rootPath={rootPath} activePath={activeTab?.path ?? null} onOpenFile={(p) => void openFile(p)} />
            ) : activeView === "agent" ? (
              <AgentActivityPanel events={activityLog} />
            ) : (
              <ExtensionsView />
            )}
          </div>
        </div>

        <div className="editorarea">
          <TabBar tabs={tabs} activeUri={activeUri} onSelect={setActiveUri} onClose={closeTab} />
          <div className="editorarea__stack">
            {tabs.length === 0 ? (
              <div className="welcome">
                <LogoMark size={40} className="welcome__logo" />
                <div className="welcome__hint">
                  Open a file from the Explorer to start.
                  <br />
                  <span className="welcome__kbd">Ctrl</span>+<span className="welcome__kbd">S</span> to
                  save · diagnostics run live as you type
                </div>
              </div>
            ) : isMermaidActive ? (
              <div className="split-view">
                <div className="split-view__pane">
                  <div className="split-view__label">Source</div>
                  <EditorPane
                    activeUri={activeUri}
                    registry={registry}
                    onContentChange={handleContentChange}
                    onSaveRequested={() => void saveActive()}
                    revealTarget={revealTarget}
                  />
                </div>
                <div className="split-view__pane">
                  <div className="split-view__label">Live preview</div>
                  <MermaidPreview content={mermaidLive} />
                </div>
              </div>
            ) : (
              <EditorPane
                activeUri={activeUri}
                registry={registry}
                onContentChange={handleContentChange}
                onSaveRequested={() => void saveActive()}
                revealTarget={revealTarget}
              />
            )}
            <ProblemsPanel
              diagnosticsByUri={diagnosticsByUri}
              collapsed={problemsCollapsed}
              onToggle={() => setProblemsCollapsed((v) => !v)}
              onJump={revealInEditor}
              bottomTab={bottomTab}
              onBottomTabChange={setBottomTab}
            />
          </div>
        </div>

        {profilePanelOpen && (
          <ProfilePanel
            profile={profile}
            onSignOut={handleSignOut}
            onClose={() => setProfilePanelOpen(false)}
            serverStatus={serverStatus}
            stats={{
              filesOpen: tabs.length,
              errors,
              warnings,
              filesAnalyzed: diagnosticsByUri.size,
            }}
          />
        )}
      </div>

      <StatusBar
        serverStatus={serverStatus}
        errors={errors}
        warnings={warnings}
        activeLanguage={activeTab ? activeTab.language : null}
        onRestartServer={restartServer}
      />
    </div>
  );
}
