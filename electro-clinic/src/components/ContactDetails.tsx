import { Clock3, MapPinned, Navigation, Phone } from "lucide-react";
import { siteConfig, workingHours } from "../data/site";
import { CtaButton } from "./CtaButton";

export function ContactDetails() {
  return (
    <aside className="rounded-lg border border-white/10 bg-slate-900/70 p-6 shadow-card">
      <h3 className="font-display text-2xl font-bold text-white">Electro Clinic</h3>

      <div className="mt-6 space-y-5 text-sm leading-6 text-clinic-muted">
        <div className="flex gap-3">
          <MapPinned className="mt-1 shrink-0 text-cyan-200" size={20} aria-hidden="true" />
          <p>
            <strong className="block text-white">{siteConfig.addressLine}</strong>
            {siteConfig.cityLine}
            <span className="block">{siteConfig.landmark}</span>
          </p>
        </div>

        <div className="flex gap-3">
          <Phone className="mt-1 shrink-0 text-cyan-200" size={20} aria-hidden="true" />
          <p>
            Telefon:{" "}
            <a className="font-semibold text-white hover:text-cyan-200" href={siteConfig.phoneHref}>
              {siteConfig.phoneDisplay}
            </a>
          </p>
        </div>

        <div className="flex gap-3">
          <Clock3 className="mt-1 shrink-0 text-cyan-200" size={20} aria-hidden="true" />
          <div>
            <strong className="block text-white">Program</strong>
            <dl className="mt-2 space-y-1">
              {workingHours.map((item) => (
                <div key={item.day} className="flex justify-between gap-5">
                  <dt>{item.day}</dt>
                  <dd className="font-semibold text-slate-100">{item.time}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>

      <div className="mt-7 flex flex-col gap-3 sm:flex-row lg:flex-col">
        <CtaButton href={siteConfig.phoneHref} icon={<Phone size={17} aria-hidden="true" />}>
          Sună acum
        </CtaButton>
        <CtaButton
          href={siteConfig.mapsUrl}
          target="_blank"
          rel="noreferrer"
          variant="secondary"
          icon={<Navigation size={17} aria-hidden="true" />}
        >
          Deschide în Google Maps
        </CtaButton>
      </div>
    </aside>
  );
}
