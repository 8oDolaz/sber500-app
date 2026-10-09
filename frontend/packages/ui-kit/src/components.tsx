import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import dotUrl from "./assets/dot.svg";

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Screen({
  variant = "default",
  className,
  ...rest
}: HTMLAttributes<HTMLElement> & { variant?: "default" | "home" | "centered" }) {
  return (
    <main
      className={cx("kn-screen", variant === "home" && "kn-screen--home", variant === "centered" && "kn-screen--centered", className)}
      {...rest}
    />
  );
}

export function Logo({ size = "xl" }: { size?: "xl" | "m" }) {
  return <h1 className={cx("kn-logo", `kn-logo--${size}`)}>kainem</h1>;
}

export function WelcomeText({ children }: { children: ReactNode }) {
  return <p className="kn-welcome">{children}</p>;
}

type CardProps = HTMLAttributes<HTMLDivElement> & {
  align?: "center" | "top";
  variant?: "default" | "home";
  minHeight?: number;
};

export function Card({ align = "center", variant = "default", minHeight, className, style, ...rest }: CardProps) {
  return (
    <div
      className={cx("kn-card", align === "top" && "kn-card--top", variant === "home" && "kn-card--home", className)}
      style={{ minHeight, ...style }}
      {...rest}
    />
  );
}

export function CardButton({
  minHeight,
  className,
  style,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { minHeight?: number }) {
  return <button type="button" className={cx("kn-card", className)} style={{ minHeight, ...style }} {...rest} />;
}

export function Button({
  loading = false,
  disabled,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      type="button"
      className={cx("kn-button", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Chip(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...props} className={cx("kn-chip", props.className)} />;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="kn-section-title">{children}</h2>;
}

export function List({ children }: { children: ReactNode }) {
  return <ul className="kn-list">{children}</ul>;
}

type ListRowProps = {
  children?: ReactNode;
  meta?: ReactNode;
  done?: boolean;
  /** Tapping the dot; omitted for placeholder rows. */
  onToggle?: () => void;
  toggleLabel?: string;
};

export function ListRow({ children, meta, done, onToggle, toggleLabel }: ListRowProps) {
  const dot = <img src={dotUrl} width={21} height={21} alt="" />;
  return (
    <li className="kn-list-row">
      {onToggle ? (
        <button type="button" className="kn-list-row__dot" aria-pressed={done} aria-label={toggleLabel} onClick={onToggle}>
          {dot}
        </button>
      ) : (
        <span className="kn-list-row__dot" aria-hidden="true">
          {dot}
        </span>
      )}
      <div className={cx("kn-list-row__body", done && "kn-list-row__body--done")}>
        {children}
        {meta ? <span className="kn-list-row__meta">{meta}</span> : null}
      </div>
    </li>
  );
}

export function Sheet({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="kn-sheet-backdrop" onClick={onClose}>
      <div
        className="kn-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function BackButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button type="button" className="kn-back" onClick={onClick}>
      ‹ {children}
    </button>
  );
}
