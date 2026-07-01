import { Phone, Wrench } from "lucide-react";
import { navItems, phoneHref } from "../data/site";
import { handleSectionLink } from "../utils/scroll";
import { CtaButton } from "./CtaButton";

export function Navigation() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-clinic-bg/88 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <a
          href="#acasa"
          onClick={(event) => handleSectionLink(event, "acasa")}
          className="flex items-center gap-3"
          aria-label="Electro Clinic acasă"
        >
          <span className="grid h-10 w-10 place-items-center rounded-lg border border-cyan-300/35 bg-cyan-300/10 text-cyan-200 shadow-glow">
            <Wrench size={21} aria-hidden="true" />
          </span>
          <span className="font-display text-xl font-bold tracking-normal text-white">
            Electro Clinic
          </span>
        </a>

        <nav aria-label="Navigare principală" className="order-3 w-full sm:order-none sm:w-auto">
          <ul className="flex items-center gap-2 overflow-x-auto text-sm font-semibold text-slate-300 sm:gap-6">
            {navItems.map((item) => (
              <li key={item.href}>
                <a
                  href={item.href}
                  onClick={(event) => handleSectionLink(event, item.href.slice(1))}
                  className="block rounded-md px-1.5 py-2 transition hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200"
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <CtaButton href={phoneHref} icon={<Phone size={17} aria-hidden="true" />} className="min-h-10 px-4 py-2">
          Sună acum
        </CtaButton>
      </div>
    </header>
  );
}
