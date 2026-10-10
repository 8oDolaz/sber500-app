import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

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
  minHeight?: number;
};

export function Card({ align = "center", minHeight, className, style, ...rest }: CardProps) {
  return (
    <div
      className={cx("kn-card", align === "top" && "kn-card--top", className)}
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
