import { Facebook, Phone } from "lucide-react";
import { siteConfig, workingHours } from "../data/site";

export function Footer() {
  return (
    <footer className="border-t border-white/10 bg-slate-950/82 px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-6xl gap-8 text-sm text-clinic-muted md:grid-cols-[1.2fr_1fr_1fr]">
        <div>
          <p className="font-display text-xl font-bold text-white">Electro Clinic</p>
          <p className="mt-3 max-w-sm leading-6">
            {siteConfig.addressLine}, {siteConfig.cityLine}. {siteConfig.landmark}.
          </p>
        </div>

        <div>
          <p className="font-bold text-white">Contact</p>
          <a
            href={siteConfig.phoneHref}
            className="mt-3 inline-flex items-center gap-2 font-semibold text-slate-100 transition hover:text-cyan-200"
          >
            <Phone size={16} aria-hidden="true" />
            {siteConfig.phoneDisplay}
          </a>
          <a
            href={siteConfig.facebookUrl}
            className="mt-3 flex items-center gap-2 transition hover:text-cyan-200"
            aria-label="Facebook Electro Clinic - URL de înlocuit"
          >
            <Facebook size={16} aria-hidden="true" />
            Facebook
          </a>
        </div>

        <div>
          <p className="font-bold text-white">Program</p>
          <dl className="mt-3 space-y-1">
            {workingHours.map((item) => (
              <div key={item.day} className="flex justify-between gap-4">
                <dt>{item.day}</dt>
                <dd className="font-semibold text-slate-100">{item.time}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      <p className="mx-auto mt-8 max-w-6xl text-xs text-slate-500">
        © {new Date().getFullYear()} Electro Clinic. Toate drepturile rezervate.
      </p>
    </footer>
  );
}
