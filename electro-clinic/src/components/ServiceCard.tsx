import type { Service } from "../data/site";

export function ServiceCard({ service }: { service: Service }) {
  const { Icon } = service;

  return (
    <article className="group h-full rounded-lg border border-white/10 bg-slate-900/70 p-5 shadow-card transition duration-200 hover:-translate-y-1 hover:border-cyan-300/40">
      <div className="mb-5 grid h-11 w-11 place-items-center rounded-lg border border-cyan-300/25 bg-cyan-300/10 text-cyan-200 transition group-hover:bg-cyan-300/15">
        <Icon size={22} strokeWidth={1.9} aria-hidden="true" />
      </div>
      <h3 className="text-lg font-bold text-white">{service.title}</h3>
      <p className="mt-3 text-sm leading-6 text-clinic-muted">{service.description}</p>
    </article>
  );
}
