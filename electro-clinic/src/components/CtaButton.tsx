import type { AnchorHTMLAttributes, ReactNode } from "react";

type CtaButtonProps = AnchorHTMLAttributes<HTMLAnchorElement> & {
  variant?: "primary" | "secondary" | "ghost";
  icon?: ReactNode;
};

export function CtaButton({
  variant = "primary",
  icon,
  children,
  className = "",
  ...props
}: CtaButtonProps) {
  const styles = {
    primary:
      "bg-cyan-300 text-slate-950 shadow-glow hover:bg-cyan-200 focus-visible:ring-cyan-200",
    secondary:
      "border border-cyan-300/45 bg-slate-950/40 text-cyan-100 hover:border-cyan-200 hover:bg-cyan-300/10 focus-visible:ring-cyan-200",
    ghost:
      "border border-slate-700/80 bg-slate-900/45 text-slate-100 hover:border-slate-500 hover:bg-slate-800/80 focus-visible:ring-slate-300",
  };

  return (
    <a
      className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-lg px-5 py-3 text-sm font-bold transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-clinic-bg ${styles[variant]} ${className}`}
      {...props}
    >
      {icon}
      <span>{children}</span>
    </a>
  );
}
