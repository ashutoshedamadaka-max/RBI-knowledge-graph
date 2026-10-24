import { ReactNode } from "react";
import { evidenceUrl } from "../quality";
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" />
      </>
    ),
    ask: (
      <>
        <path d="M20 11a8 8 0 0 1-8 8H5l-4 3 2-7a8 8 0 1 1 17-4Z" />
        <path d="M7 9h8M7 13h5" />
      </>
    ),
    how: (
      <>
        <rect x="3" y="3" width="6" height="6" rx="1" />
        <rect x="15" y="15" width="6" height="6" rx="1" />
        <path d="M9 6h9v9M6 9v9h9" />
      </>
    ),
    built: (
      <>
        <path d="m12 3 10 6-10 6L2 9Z" />
        <path d="m2 13 10 6 10-6M2 17l10 6 10-6" />
      </>
    ),
    evals: (
      <>
        <path d="M4 3v17h17M8 16v-5M13 16V7M18 16V4" />
      </>
    ),
    sources: (
      <>
        <path d="M5 2h10l4 4v16H5Z" />
        <path d="M14 2v5h5M8 11h8M8 15h8M8 19h5" />
      </>
    ),
    graph: (
      <>
        <circle cx="12" cy="5" r="3" />
        <circle cx="5" cy="18" r="3" />
        <circle cx="20" cy="16" r="3" />
        <path d="m10 8-4 7m8-7 4 5M8 18l9-1" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    external: <path d="M14 3h7v7m0-7L10 14M10 3H4v17h17v-6" />,
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2" />
      </>
    ),
    menu: <path d="M4 6h16M4 12h16M4 18h16" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    search: (
      <>
        <circle cx="10" cy="10" r="7" />
        <path d="m15 15 6 6" />
      </>
    ),
    play: <path d="m8 4 12 8-12 8Z" />,
    check: <path d="m4 12 5 5L20 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.arrow}
    </svg>
  );
}
export function PageIntro({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <header className="page-intro">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <div className="lead">{children}</div>
    </header>
  );
}
export function SourceNote({
  file,
  children,
}: {
  file: string;
  children?: ReactNode;
}) {
  return (
    <p className="source-note">
      {children && <>{children} · </>}
      <a href={evidenceUrl(file)} target="_blank" rel="noreferrer">
        Saved run <Icon name="external" size={12} />
        <span className="sr-only">: {file} (opens in a new tab)</span>
      </a>
    </p>
  );
}
export function NextPage({
  href,
  title,
  text,
}: {
  href: string;
  title: string;
  text: string;
}) {
  return (
    <a href={href} className="next-page">
      <span>
        <span className="eyebrow">Continue exploring</span>
        <strong>{title}</strong>
        <span className="muted">{text}</span>
      </span>
      <Icon name="arrow" size={28} />
    </a>
  );
}
export function EmptyState({
  title,
  children,
  retry,
}: {
  title: string;
  children: ReactNode;
  retry?: () => void;
}) {
  return (
    <div className="empty-state" role="status">
      <Icon name="search" size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
      {retry && (
        <button className="secondary" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
