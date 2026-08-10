/**
 * Demo entries for the Extensions marketplace view.
 *
 * These are catalogue entries, not installable code — nothing here downloads or runs
 * anything. That's stated in the panel itself, not just here: the point is to show what a
 * populated marketplace looks like for a research IDE, the same way a furnished show home
 * demonstrates a floor plan without anyone actually living in it. Aurelius's own four
 * built-in tools (Bibliography, Submission Gate, Diagrams, Agent Activity) are marked
 * `builtin: true` and are real — everything else in this list is illustrative.
 */
export type ExtensionCategory =
  | "Citations & References"
  | "Writing & Editing"
  | "Diagrams & Visualization"
  | "Collaboration"
  | "Themes"
  | "Data & Statistics"
  | "Version Control"
  | "Productivity"
  | "Language Support"
  | "AI & Automation";

export interface ExtensionEntry {
  id: string;
  name: string;
  publisher: string;
  description: string;
  category: ExtensionCategory;
  installs: string;
  rating: number;
  version: string;
  verified?: boolean;
  builtin?: boolean;
  colour: string;
  initials: string;
}

const C = {
  citations: "#4ec9b0",
  writing: "#569cd6",
  diagrams: "#cc7832",
  collab: "#c586c0",
  themes: "#e5c158",
  data: "#f14c4c",
  git: "#e57373",
  productivity: "#73c991",
  lang: "#dcb67a",
  ai: "#3794ff",
} as const;

function entry(
  id: string,
  name: string,
  publisher: string,
  description: string,
  category: ExtensionCategory,
  installs: string,
  rating: number,
  colour: string,
  extra?: Partial<ExtensionEntry>
): ExtensionEntry {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  return { id, name, publisher, description, category, installs, rating, version: "1.0.0", colour, initials, ...extra };
}

export const BUILTIN_EXTENSIONS: ExtensionEntry[] = [
  entry(
    "aurelius.bibliography",
    "Bibliography",
    "Aurelius",
    "Every reference with its live verification verdict — retracted, unverified, or clean.",
    "Citations & References",
    "Built-in",
    5,
    C.citations,
    { builtin: true, verified: true, version: "0.3.1" }
  ),
  entry(
    "aurelius.gate",
    "Submission Gate",
    "Aurelius",
    "Compiles the paper and checks the pre-submission list: no undefined refs, no retracted work, no broken build.",
    "Productivity",
    "Built-in",
    5,
    C.productivity,
    { builtin: true, verified: true, version: "0.3.1" }
  ),
  entry(
    "aurelius.diagrams",
    "Architecture & Diagrams",
    "Aurelius",
    "Live Mermaid rendering for .mmd files — flowcharts, architecture, and sequence diagrams.",
    "Diagrams & Visualization",
    "Built-in",
    5,
    C.diagrams,
    { builtin: true, verified: true, version: "0.3.1" }
  ),
  entry(
    "aurelius.agent-activity",
    "Agent Activity",
    "Aurelius",
    "A live feed of what the verification engine is actually doing, citation by citation.",
    "AI & Automation",
    "Built-in",
    5,
    C.ai,
    { builtin: true, verified: true, version: "0.3.1" }
  ),
];

const CATALOGUE_SOURCE: Array<[string, string, string, string, ExtensionCategory, string, number, string]> = [
  ["zotero-connect", "Zotero Connect", "Zotero", "Sync your Zotero library and drag citations straight into a .bib file.", "Citations & References", "2.1M", 4.8, C.citations],
  ["mendeley-sync", "Mendeley Sync", "Elsevier", "Two-way sync between Mendeley reference groups and workspace bibliographies.", "Citations & References", "890K", 4.2, C.citations],
  ["doi-resolver", "DOI Resolver", "Crossref Labs", "Paste a DOI, get a formatted BibTeX entry with one keystroke.", "Citations & References", "1.4M", 4.7, C.citations],
  ["orcid-linker", "ORCID Linker", "ORCID", "Attach your ORCID iD to author blocks and auto-fill affiliations.", "Citations & References", "410K", 4.4, C.citations],
  ["arxiv-search", "arXiv Quick Search", "Community", "Search arXiv without leaving the editor; insert BibTeX with one click.", "Citations & References", "3.2M", 4.9, C.citations],
  ["semantic-scholar", "Semantic Scholar Graph", "Allen Institute", "Explore citation graphs and influential-citation counts inline.", "Citations & References", "560K", 4.5, C.citations],
  ["retraction-watch", "Retraction Watch Feed", "Community", "Live feed of newly retracted papers matched against your bibliography.", "Citations & References", "220K", 4.6, C.citations],
  ["bibtex-formatter", "BibTeX Formatter", "Community", "Auto-sorts and re-indents .bib files on save, alphabetically by key.", "Citations & References", "780K", 4.1, C.citations],
  ["duplicate-citation-finder", "Duplicate Citation Finder", "Community", "Flags near-duplicate bibliography entries with different keys.", "Citations & References", "150K", 4.3, C.citations],
  ["citation-style-switcher", "Citation Style Switcher", "Community", "Preview a bibliography rendered in APA, MLA, Chicago, and IEEE side by side.", "Citations & References", "340K", 4.0, C.citations],

  ["latex-workshop-plus", "LaTeX Workshop+", "Community", "Snippets, environment auto-close, and smart section folding for LaTeX.", "Writing & Editing", "5.6M", 4.7, C.writing],
  ["grammar-check-academic", "Academic Grammar Check", "Community", "Grammar and style suggestions tuned for academic register, not casual prose.", "Writing & Editing", "1.9M", 4.3, C.writing],
  ["hedge-word-detector", "Hedge Word Detector", "Community", "Flags overused hedging ('may suggest', 'could potentially') for tightening.", "Writing & Editing", "95K", 4.1, C.writing],
  ["passive-voice-linter", "Passive Voice Linter", "Community", "Highlights passive constructions with an active-voice suggestion.", "Writing & Editing", "410K", 3.9, C.writing],
  ["word-count-goals", "Word Count Goals", "Community", "Per-section word budgets with a live progress bar in the status bar.", "Writing & Editing", "260K", 4.4, C.writing],
  ["latex-table-generator", "Table Generator", "Community", "Paste a CSV, get a formatted LaTeX table with booktabs styling.", "Writing & Editing", "890K", 4.6, C.writing],
  ["equation-numbering", "Smart Equation Numbering", "Community", "Keeps \\eqref numbering consistent across multi-file projects.", "Writing & Editing", "310K", 4.2, C.writing],
  ["abstract-length-checker", "Abstract Length Checker", "Community", "Warns when an abstract exceeds a venue's stated word limit.", "Writing & Editing", "180K", 4.0, C.writing],
  ["latex-lorem", "Academic Lorem Ipsum", "Community", "Generates placeholder paragraphs shaped like real academic prose.", "Writing & Editing", "620K", 3.8, C.writing],
  ["multilingual-abstract", "Multilingual Abstract", "Community", "Side-by-side editing for translated abstracts (venue-required in some fields).", "Writing & Editing", "75K", 4.1, C.writing],
  ["latex-spell-domain", "Domain Spell Checker", "Community", "Spell-check that understands ML/bio/physics jargon instead of flagging it.", "Writing & Editing", "1.1M", 4.5, C.writing],
  ["readability-score", "Readability Score", "Community", "Flesch-Kincaid and academic readability scoring per section.", "Writing & Editing", "140K", 3.7, C.writing],
  ["latex-macro-linter", "Macro Consistency Linter", "Community", "Flags custom \\newcommand macros defined but never used.", "Writing & Editing", "230K", 4.0, C.writing],

  ["mermaid-live", "Mermaid Live Preview", "Community", "Side-by-side Mermaid source and rendered diagram, updates as you type.", "Diagrams & Visualization", "2.8M", 4.8, C.diagrams],
  ["tikz-preview", "TikZ Live Preview", "Community", "Renders tikzpicture environments without a full document compile.", "Diagrams & Visualization", "1.6M", 4.6, C.diagrams],
  ["plantuml-support", "PlantUML Support", "Community", "UML sequence, class, and architecture diagrams from plain text.", "Diagrams & Visualization", "980K", 4.4, C.diagrams],
  ["graphviz-dot", "Graphviz DOT Preview", "Community", "Live-renders .dot files for dependency and pipeline graphs.", "Diagrams & Visualization", "670K", 4.3, C.diagrams],
  ["chart-from-csv", "Chart from CSV", "Community", "Turns a results CSV into a publication-ready bar/line chart figure.", "Diagrams & Visualization", "450K", 4.2, C.diagrams],
  ["architecture-icons", "Architecture Icon Pack", "Community", "AWS/GCP/generic system icons for architecture diagrams.", "Diagrams & Visualization", "310K", 4.0, C.diagrams],
  ["excalidraw-embed", "Excalidraw Embed", "Excalidraw", "Hand-drawn style figures, embedded and editable inline.", "Diagrams & Visualization", "1.2M", 4.7, C.diagrams],
  ["flowchart-from-pseudocode", "Flowchart from Pseudocode", "Community", "Converts an algorithm block into a flowchart diagram automatically.", "Diagrams & Visualization", "190K", 3.9, C.diagrams],
  ["latex-pgfplots-helper", "pgfplots Helper", "Community", "Autocomplete and validation for pgfplots axis environments.", "Diagrams & Visualization", "280K", 4.1, C.diagrams],

  ["live-share-research", "Live Share", "Community", "Real-time collaborative editing with cursor presence, for co-authors.", "Collaboration", "3.4M", 4.5, C.collab],
  ["comment-threads", "Comment Threads", "Community", "Margin comments and reply threads, exported as a review-response letter.", "Collaboration", "540K", 4.3, C.collab],
  ["overleaf-bridge", "Overleaf Bridge", "Community", "Two-way sync between a local project and an Overleaf project.", "Collaboration", "1.8M", 4.2, C.collab],
  ["coauthor-presence", "Co-author Presence", "Community", "Shows which section each collaborator is currently viewing.", "Collaboration", "220K", 4.0, C.collab],
  ["track-changes-latex", "Track Changes for LaTeX", "Community", "\\added/\\deleted markup rendered as inline diff highlighting.", "Collaboration", "670K", 4.4, C.collab],
  ["review-response-builder", "Review Response Builder", "Community", "Turns reviewer comments + your replies into a formatted response letter.", "Collaboration", "160K", 4.1, C.collab],
  ["shared-todo", "Shared Paper To-Dos", "Community", "A task list scoped to the project, visible to every collaborator.", "Collaboration", "290K", 3.9, C.collab],

  ["one-dark-academic", "One Dark Academic", "Community", "A warmer One Dark variant tuned for long reading sessions.", "Themes", "1.1M", 4.6, C.themes],
  ["paper-white", "Paper White", "Community", "A high-contrast light theme that mimics printed paper.", "Themes", "780K", 4.3, C.themes],
  ["dyslexia-friendly", "Dyslexia-Friendly Theme", "Community", "OpenDyslexic font pairing with increased letter spacing.", "Themes", "95K", 4.7, C.themes],
  ["solarized-research", "Solarized Research", "Community", "The classic Solarized palette, remapped to Aurelius's severity colours.", "Themes", "420K", 4.4, C.themes],
  ["high-contrast-plus", "High Contrast+", "Community", "WCAG AAA contrast throughout, including diagnostic squiggles.", "Themes", "160K", 4.5, C.themes],
  ["nord-academic", "Nord Academic", "Community", "The Nord palette adapted for LaTeX syntax highlighting.", "Themes", "610K", 4.5, C.themes],
  ["sepia-night", "Sepia Night", "Community", "A warm sepia dark theme, easier on the eyes late at night.", "Themes", "230K", 4.1, C.themes],
  ["icon-pack-material", "Material Icon Pack", "Community", "File and folder icons matching common research project layouts.", "Themes", "1.3M", 4.6, C.themes],

  ["stats-check-r", "Statistical Method Checker (R)", "Community", "Flags common misuse of statistical tests in embedded R code blocks.", "Data & Statistics", "340K", 4.3, C.data],
  ["p-hacking-audit", "p-Hacking Audit", "Community", "Scans for signs of undisclosed multiple comparisons or optional stopping.", "Data & Statistics", "180K", 4.0, C.data],
  ["effect-size-reporter", "Effect Size Reporter", "Community", "Reminds you to report effect sizes alongside p-values.", "Data & Statistics", "150K", 3.8, C.data],
  ["preregistration-linker", "Preregistration Linker", "Community", "Links a paper's claims back to its OSF preregistration.", "Data & Statistics", "90K", 4.2, C.data],
  ["data-availability-checker", "Data Availability Checker", "Community", "Verifies a Data Availability statement matches an actual repository link.", "Data & Statistics", "110K", 4.1, C.data],
  ["reproducibility-badge", "Reproducibility Badge", "Community", "Generates a badge once code + data + environment are all linked.", "Data & Statistics", "70K", 3.9, C.data],
  ["jupyter-figure-sync", "Jupyter Figure Sync", "Community", "Re-exports a notebook figure into the paper on every notebook save.", "Data & Statistics", "260K", 4.4, C.data],

  ["git-latex-diff", "LaTeX-Aware Git Diff", "Community", "Word-level diffs for .tex files instead of line-level noise.", "Version Control", "890K", 4.6, C.git],
  ["commit-from-section", "Commit per Section", "Community", "Suggests commit boundaries aligned to section edits.", "Version Control", "60K", 3.6, C.git],
  ["latex-merge-driver", "LaTeX Merge Driver", "Community", "A git merge driver that understands LaTeX environments, not just lines.", "Version Control", "310K", 4.3, C.git],
  ["overleaf-git-sync", "Overleaf Git Sync", "Community", "Pulls Overleaf's git bridge into a local branch on a schedule.", "Version Control", "420K", 4.0, C.git],
  ["gitignore-latex", "LaTeX .gitignore Presets", "Community", "One-click .gitignore for aux/log/synctex build artefacts.", "Version Control", "1.4M", 4.5, C.git],

  ["pomodoro-writer", "Pomodoro for Writers", "Community", "Timed writing sprints with a status-bar countdown.", "Productivity", "780K", 4.2, C.productivity],
  ["deadline-tracker", "Submission Deadline Tracker", "Community", "Countdown to your target venue's deadline, timezone-aware.", "Productivity", "540K", 4.4, C.productivity],
  ["focus-mode", "Focus Mode", "Community", "Dims everything but the current paragraph.", "Productivity", "1.2M", 4.6, C.productivity],
  ["section-outline-map", "Section Outline Map", "Community", "A minimap of section/subsection structure, click to jump.", "Productivity", "630K", 4.3, C.productivity],
  ["snippet-library-academic", "Academic Snippet Library", "Community", "Common phrasing snippets ('as shown in Table', 'we hypothesize that').", "Productivity", "410K", 3.9, C.productivity],
  ["backup-on-save", "Timestamped Backups", "Community", "Keeps a rolling history of .tex snapshots outside git.", "Productivity", "290K", 4.0, C.productivity],
  ["venue-formatter", "Venue Format Switcher", "Community", "Swaps document class and margins between common venue templates.", "Productivity", "680K", 4.5, C.productivity],
  ["reading-list-manager", "Reading List Manager", "Community", "A queue of papers to read, promoted to citations once read.", "Productivity", "220K", 4.1, C.productivity],
  ["latex-build-badge", "Build Status Badge", "Community", "A status-bar badge showing last successful compile time.", "Productivity", "150K", 3.8, C.productivity],
  ["distraction-block", "Distraction Blocker", "Community", "Blocks configured websites while a writing sprint is active.", "Productivity", "340K", 3.7, C.productivity],

  ["multilingual-latex", "Multilingual LaTeX", "Community", "babel/polyglossia setup wizard for non-English papers.", "Language Support", "560K", 4.3, C.lang],
  ["cjk-latex-support", "CJK Support", "Community", "Correct spacing and font fallback for Chinese/Japanese/Korean text.", "Language Support", "410K", 4.4, C.lang],
  ["rtl-latex-support", "RTL Language Support", "Community", "Right-to-left text handling for Arabic and Hebrew papers.", "Language Support", "180K", 4.2, C.lang],
  ["r-syntax-embed", "R Syntax in LaTeX", "Community", "Syntax highlighting for R code blocks inside knitr documents.", "Language Support", "290K", 4.0, C.lang],
  ["julia-syntax-embed", "Julia Syntax in LaTeX", "Community", "Syntax highlighting for embedded Julia code listings.", "Language Support", "85K", 3.9, C.lang],
  ["python-syntax-embed", "Python Syntax in LaTeX", "Community", "Syntax highlighting for embedded Python listings, PEP 8 aware.", "Language Support", "670K", 4.3, C.lang],
  ["matlab-syntax-embed", "MATLAB Syntax in LaTeX", "Community", "Syntax highlighting for embedded MATLAB/Octave listings.", "Language Support", "230K", 3.8, C.lang],

  ["ai-abstract-drafter", "Abstract Drafter", "Community", "Drafts an abstract from your conclusion section as a starting point.", "AI & Automation", "1.5M", 4.0, C.ai],
  ["ai-related-work-finder", "Related Work Finder", "Community", "Suggests papers your related-work section may be missing.", "AI & Automation", "980K", 3.9, C.ai],
  ["ai-clarity-pass", "Clarity Pass", "Community", "Rewrites dense sentences for clarity, preserving every citation and number.", "AI & Automation", "1.1M", 4.1, C.ai],
  ["ai-reviewer-simulator", "Reviewer Simulator", "Community", "Drafts likely reviewer questions based on your claims and evidence.", "AI & Automation", "620K", 3.8, C.ai],
  ["ai-figure-caption", "Figure Caption Assistant", "Community", "Suggests a caption from a figure's filename and surrounding text.", "AI & Automation", "340K", 3.7, C.ai],
  ["ai-consistency-check", "Terminology Consistency Check", "Community", "Flags a term used inconsistently across sections.", "AI & Automation", "410K", 4.0, C.ai],
  ["ai-plain-summary", "Plain-Language Summary", "Community", "Generates a lay summary for broader-impact statements.", "AI & Automation", "290K", 3.9, C.ai],

  ["scholar-metrics-import", "Google Scholar Metrics Import", "Community", "Pulls citation counts and h-index snapshots into a project's stats sidebar.", "Citations & References", "480K", 4.1, C.citations],
  ["abbreviation-checker", "Abbreviation Consistency Checker", "Community", "Flags an acronym used before its first definition, or defined twice differently.", "Writing & Editing", "260K", 4.2, C.writing],
  ["drawio-embed", "Draw.io Embed", "diagrams.net", "Edit draw.io diagrams inline and export straight to a LaTeX figure.", "Diagrams & Visualization", "540K", 4.5, C.diagrams],
  ["advisor-review-mode", "Advisor Review Mode", "Community", "A read-annotate-only mode for sharing a draft with an advisor without edit risk.", "Collaboration", "190K", 4.3, C.collab],
  ["colorblind-safe-theme", "Colourblind-Safe Diagnostics", "Community", "Remaps error/warning/hint colours to a colourblind-safe palette.", "Themes", "140K", 4.6, C.themes],
  ["sample-size-justifier", "Sample Size Justifier", "Community", "Checks that a stated sample size matches the power analysis described.", "Data & Statistics", "85K", 3.9, C.data],
  ["branch-per-revision", "Branch per Revision", "Community", "Auto-creates a git branch per revision round, named by reviewer round.", "Version Control", "120K", 3.8, C.git],
  ["citation-budget-tracker", "Citation Budget Tracker", "Community", "Warns when a section leans on a single source too heavily relative to the rest.", "Productivity", "160K", 3.9, C.productivity],
  ["latex-accessibility-tagger", "LaTeX Accessibility Tagger", "Community", "Adds tagged-PDF accessibility structure for screen readers on compile.", "Language Support", "70K", 4.0, C.lang],
  ["model-card-generator", "Model Card Generator", "Community", "Drafts a model card section from your Methods, for ML papers.", "AI & Automation", "310K", 4.0, C.ai],
];

function fillerBatch(): ExtensionEntry[] {
  const categories: ExtensionCategory[] = [
    "Citations & References", "Writing & Editing", "Diagrams & Visualization", "Collaboration",
    "Themes", "Data & Statistics", "Version Control", "Productivity", "Language Support", "AI & Automation",
  ];
  const nouns = [
    "Toolkit", "Helper", "Companion", "Assistant", "Kit", "Suite", "Pack", "Bridge", "Sync", "Lens",
  ];
  const adjectives = [
    "Rapid", "Clean", "Smart", "Quiet", "Sharp", "Steady", "Clear", "Precise", "Focused", "Tidy",
  ];
  const out: ExtensionEntry[] = [];
  let i = 0;
  for (const category of categories) {
    for (let j = 0; j < 3; j++) {
      const adjective = adjectives[(i * 3 + j) % adjectives.length];
      const noun = nouns[(i + j) % nouns.length];
      const name = `${adjective} ${category.split(" ")[0]} ${noun}`;
      out.push(
        entry(
          `filler-${category.replace(/\W+/g, "").toLowerCase()}-${j}`,
          name,
          "Community",
          `A lightweight ${category.toLowerCase()} add-on for everyday paper writing.`,
          category,
          `${10 + ((i * 7 + j * 13) % 90)}K`,
          Number((3.4 + ((i + j) % 6) * 0.2).toFixed(1)),
          Object.values(C)[(i + j) % Object.values(C).length]
        )
      );
    }
    i++;
  }
  return out;
}

export const MARKETPLACE_EXTENSIONS: ExtensionEntry[] = [
  ...CATALOGUE_SOURCE.map(([id, name, publisher, description, category, installs, rating, colour]) =>
    entry(id, name, publisher, description, category, installs, rating, colour)
  ),
  ...fillerBatch(),
];

export const ALL_EXTENSIONS = [...BUILTIN_EXTENSIONS, ...MARKETPLACE_EXTENSIONS];

export const CATEGORIES: ExtensionCategory[] = [
  "Citations & References", "Writing & Editing", "Diagrams & Visualization", "Collaboration",
  "Themes", "Data & Statistics", "Version Control", "Productivity", "Language Support", "AI & Automation",
];
