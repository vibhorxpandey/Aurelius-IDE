/** A small self-contained icon set. No codicon font or SVG sprite dependency for a prototype. */
import type { JSX } from "react";

type IconProps = { size?: number; className?: string };

function base(paths: JSX.Element, { size = 16, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className={className}>
      {paths}
    </svg>
  );
}

export const ExplorerIcon = (p: IconProps) =>
  base(
    <path
      d="M2 3.5A1.5 1.5 0 0 1 3.5 2h2.6l1.2 1.5H12.5A1.5 1.5 0 0 1 14 5v6.5A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.5v-8Z"
      stroke="currentColor"
      strokeWidth="1.3"
    />,
    p
  );

export const BookIcon = (p: IconProps) =>
  base(
    <path
      d="M3 2.5h7A1.5 1.5 0 0 1 11.5 4v9.5H4.5A1.5 1.5 0 0 1 3 12V2.5Zm0 0v11M3 12h8.5"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
    />,
    p
  );

export const GateIcon = (p: IconProps) =>
  base(
    <>
      <path d="M2.5 13.5v-9L8 2l5.5 2.5v9" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
      <path d="M6 8.5l1.5 1.5L10 7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </>,
    p
  );

export const FolderIcon = (p: IconProps) =>
  base(
    <path
      d="M2 4.2A1.2 1.2 0 0 1 3.2 3h2.4l1 1.2H12.8A1.2 1.2 0 0 1 14 5.4v6.4A1.2 1.2 0 0 1 12.8 13H3.2A1.2 1.2 0 0 1 2 11.8V4.2Z"
      fill="#dcb67a"
      stroke="none"
    />,
    p
  );

export const FileTexIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M4 2h5l3 3v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"
        fill="#519aba"
        stroke="none"
        opacity="0.85"
      />
      <path d="M9 2v3h3" fill="#1e1e1e" stroke="none" />
    </>,
    p
  );

export const FileBibIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M4 2h5l3 3v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"
        fill="#cc7832"
        stroke="none"
        opacity="0.85"
      />
      <path d="M9 2v3h3" fill="#1e1e1e" stroke="none" />
    </>,
    p
  );

export const FileMermaidIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M4 2h5l3 3v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"
        fill="#e57373"
        stroke="none"
        opacity="0.85"
      />
      <path d="M9 2v3h3" fill="#1e1e1e" stroke="none" />
    </>,
    p
  );

export const TerminalIcon = (p: IconProps) =>
  base(
    <>
      <path d="M2.5 3h11a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4.5 6l2.5 2-2.5 2M8.5 10h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
    </>,
    p
  );

export const ActivityIcon = (p: IconProps) =>
  base(
    <path d="M2 8.5h2.5l1.5-4 3 8 1.5-4H14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />,
    p
  );

export const DiagramIcon = (p: IconProps) =>
  base(
    <>
      <rect x="2" y="2.5" width="5" height="3.5" rx="0.6" stroke="currentColor" strokeWidth="1.2" />
      <rect x="9" y="10" width="5" height="3.5" rx="0.6" stroke="currentColor" strokeWidth="1.2" />
      <rect x="2" y="10" width="5" height="3.5" rx="0.6" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4.5 6v4M11.5 6v4M4.5 8h7" stroke="currentColor" strokeWidth="1.1" />
    </>,
    p
  );

export const ExtensionsIcon = (p: IconProps) =>
  base(
    <path
      d="M6 2.5h4v2.3a1.2 1.2 0 0 0 1.9.95A1.5 1.5 0 1 1 13.5 8.4 1.2 1.2 0 0 0 12.5 10H14v4h-4v-1.4a1.2 1.2 0 0 0-2.3-.5A1.5 1.5 0 1 1 5.4 9.6 1.2 1.2 0 0 0 6.5 8H2V4h1.4a1.2 1.2 0 0 0 .5-2.3A1.5 1.5 0 1 1 6.4 3.4 1.2 1.2 0 0 0 6 2.5Z"
      stroke="currentColor"
      strokeWidth="1.1"
      strokeLinejoin="round"
    />,
    p
  );

export const UserIcon = (p: IconProps) =>
  base(
    <>
      <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M2.5 13.5c1-2.8 3.2-4 5.5-4s4.5 1.2 5.5 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </>,
    p
  );

export const FileGenericIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M4 2h5l3 3v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.2"
        opacity="0.6"
      />
      <path d="M9 2v3h3" stroke="currentColor" strokeWidth="1.2" opacity="0.6" />
    </>,
    p
  );

export const ChevronIcon = (p: IconProps) =>
  base(<path d="M6 3.5l5 4.5-5 4.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />, p);

export const CloseIcon = (p: IconProps) =>
  base(
    <path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />,
    p
  );

export const RefreshIcon = (p: IconProps) =>
  base(
    <path
      d="M13 8A5 5 0 1 1 11.6 4.4M13 2v3.5h-3.5"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    />,
    p
  );

export const PlayIcon = (p: IconProps) =>
  base(<path d="M4.5 3l8 5-8 5V3Z" fill="currentColor" stroke="none" />, p);

export const DownloadIcon = (p: IconProps) =>
  base(
    <path
      d="M8 2.5v7.2M4.8 6.9 8 10.1l3.2-3.2M3 12.5h10"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    />,
    p
  );

export const NewFileIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M4 2h5l3 3v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <path d="M9 2v3h3" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 7.5v4M6 9.5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </>,
    p
  );

export const NewFolderIcon = (p: IconProps) =>
  base(
    <>
      <path
        d="M2 4.2A1.2 1.2 0 0 1 3.2 3h2.4l1 1.2H12.8A1.2 1.2 0 0 1 14 5.4v6.4A1.2 1.2 0 0 1 12.8 13H3.2A1.2 1.2 0 0 1 2 11.8V4.2Z"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <path d="M8 6.8v4M6 8.8h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </>,
    p
  );

export const ErrorIcon = (p: IconProps) =>
  base(
    <>
      <circle cx="8" cy="8" r="6.3" fill="var(--sev-error)" stroke="none" />
      <path d="M8 4.8v3.8M8 11.1v.1" stroke="#1e1e1e" strokeWidth="1.4" strokeLinecap="round" />
    </>,
    p
  );

export const WarningIcon = (p: IconProps) =>
  base(
    <>
      <path d="M8 2.3 14.3 13H1.7L8 2.3Z" fill="var(--sev-warning)" stroke="none" />
      <path d="M8 6.5v3M8 11.6v.1" stroke="#1e1e1e" strokeWidth="1.4" strokeLinecap="round" />
    </>,
    p
  );

export const InfoIcon = (p: IconProps) =>
  base(
    <>
      <circle cx="8" cy="8" r="6.3" fill="var(--sev-info)" stroke="none" />
      <path d="M8 7.2v3.6M8 4.9v.1" stroke="#1e1e1e" strokeWidth="1.4" strokeLinecap="round" />
    </>,
    p
  );

export const HintIcon = (p: IconProps) =>
  base(<circle cx="8" cy="8" r="3.4" fill="var(--sev-hint)" stroke="none" />, p);

export const CheckCircleIcon = (p: IconProps) =>
  base(
    <>
      <circle cx="8" cy="8" r="6.3" stroke="#73c991" strokeWidth="1.3" />
      <path d="M5.2 8.2l1.8 1.8 3.8-4" stroke="#73c991" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </>,
    p
  );

export const SkipCircleIcon = (p: IconProps) =>
  base(<path d="M3 3l10 10M13 3L3 13" stroke="var(--fg-muted)" strokeWidth="1.3" strokeLinecap="round" />, p);

export const LogoMark = (p: IconProps) =>
  base(
    <>
      <rect x="2" y="4" width="12" height="2" rx="1" fill="currentColor" opacity="0.85" />
      <path
        d="M2 11.5c1.6-2.2 3-2.2 4.6 0s3 2.2 4.6 0"
        stroke="var(--sev-error)"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </>,
    p
  );
