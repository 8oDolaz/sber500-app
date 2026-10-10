import { useEffect, useRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode, type RefObject } from "react";

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
  returnFocusRef,
  children,
}: {
  title: string;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = returnFocusRef?.current ?? document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLElement>("button, a[href], [tabindex='0']")?.focus();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, [returnFocusRef]);
  return (
    <div className="kn-sheet-backdrop" onClick={onClose}>
      <div
        ref={dialog}
        className="kn-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); onClose(); }
          if (e.key === "Tab") {
            const targets = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex='0']");
            if (!targets?.length) return;
            const first = targets[0], last = targets[targets.length - 1];
            if (!first || !last) return;
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
          }
        }}
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
