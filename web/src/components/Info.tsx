import { ReactNode, useId, useState } from "react";

/** A small "i" that explains a metric: opens on hover, keyboard focus or tap, closes on Escape. */
export default function Info({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className={`info ${open ? "open" : ""}`}>
      <button
        type="button"
        className="info-btn"
        aria-label={`What is ${label}?`}
        aria-describedby={id}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); }}
      >
        i
      </button>
      <span role="tooltip" id={id} className="info-pop">{children}</span>
    </span>
  );
}
