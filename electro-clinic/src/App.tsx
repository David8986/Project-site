import {
  ArrowRight,
  CheckCircle2,
  MapPinned,
  Navigation as NavigationIcon,
  Phone,
  Sparkles,
} from "lucide-react";
import { ContactDetails } from "./components/ContactDetails";
import { ContactForm } from "./components/ContactForm";
import { CtaButton } from "./components/CtaButton";
import { Footer } from "./components/Footer";
import { Navigation } from "./components/Navigation";
import { SectionHeading } from "./components/SectionHeading";
import { ServiceCard } from "./components/ServiceCard";
import { reasons, services, siteConfig, steps } from "./data/site";
import { handleSectionLink } from "./utils/scroll";

function Hero() {
  return (
    <section
      id="acasa"
      className="relative scroll-mt-24 overflow-hidden border-b border-white/10 bg-clinic-bg px-4 pb-8 pt-8 sm:px-6 lg:px-8 lg:pb-10 lg:pt-10"
    >
      <div className="pointer-events-none absolute inset-0 bg-circuit-grid bg-[size:54px_54px] opacity-70" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-clinic-bg to-transparent" />
      <div className="pointer-events-none absolute inset-x-4 top-28 h-52 overflow-hidden rounded-lg border border-cyan-300/10 opacity-20 lg:hidden">
        <img
          src="/assets/repair-workbench.png"
          alt=""
          className="h-full w-full object-cover"
          aria-hidden="true"
        />
      </div>

      <div className="relative mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.06fr_0.94fr]">
        <div className="max-w-3xl">
          <h1 className="font-display text-[2.45rem] font-bold leading-[1.05] tracking-normal text-white sm:text-5xl lg:text-5xl">
            Reparații telefoane, laptopuri și electronice în Câmpulung Moldovenesc
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-clinic-muted sm:text-lg sm:leading-8">
            Electro Clinic oferă servicii de diagnoză, reparații și mentenanță pentru telefoane,
            tablete, laptopuri, PC-uri, console și alte dispozitive electronice.
          </p>

          <div className="mt-6 flex flex-wrap gap-3">
            <CtaButton href={siteConfig.phoneHref} icon={<Phone size={18} aria-hidden="true" />}>
              Sună acum
            </CtaButton>
            <CtaButton
              href="#contact"
              onClick={(event) => handleSectionLink(event, "contact")}
              variant="secondary"
              icon={<MapPinned size={18} aria-hidden="true" />}
            >
              Găsește-ne
            </CtaButton>
          </div>

          <div className="mt-7 hidden gap-3 text-sm text-clinic-muted sm:grid sm:grid-cols-3">
            {["Diagnoză", "Reparații", "Mentenanță"].map((item) => (
              <div key={item} className="flex items-center gap-2">
                <CheckCircle2 className="text-clinic-green" size={18} aria-hidden="true" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="relative hidden lg:block">
          <div className="absolute -inset-3 rounded-lg border border-cyan-300/10 bg-cyan-300/5 blur-xl" />
          <figure className="relative overflow-hidden rounded-lg border border-cyan-300/25 bg-slate-950 shadow-card">
            <img
              src="/assets/repair-workbench.png"
              alt="Telefon, laptop și unelte pe un banc de lucru pentru reparații electronice"
              className="aspect-[16/10] h-full w-full object-cover"
              width="1536"
              height="960"
            />
            <figcaption className="sr-only">
              Imagine tehnică pentru service de telefoane, laptopuri și dispozitive electronice.
            </figcaption>
          </figure>
        </div>
      </div>
    </section>
  );
}

function Services() {
  return (
    <section id="servicii" className="scroll-mt-24 bg-clinic-bg px-4 pb-16 pt-8 sm:px-6 sm:pb-24 sm:pt-12 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          title="Ce reparăm"
          text="Poți veni cu mai multe tipuri de dispozitive pentru diagnosticare și evaluare. Intervențiile depind de problemă, model și starea echipamentului."
        />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {services.map((service) => (
            <ServiceCard key={service.title} service={service} />
          ))}
        </div>
      </div>
    </section>
  );
}

function WhyChooseUs() {
  return (
    <section className="border-y border-white/10 bg-slate-950/70 px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[0.78fr_1fr] lg:items-start">
        <SectionHeading
          title="De ce Electro Clinic"
          text="Un service local, practic și ușor de contactat, pentru dispozitivele folosite în fiecare zi."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          {reasons.map(({ title, text, Icon }) => (
            <article key={title} className="rounded-lg border border-white/10 bg-clinic-panel/80 p-5">
              <Icon className="text-cyan-200" size={23} strokeWidth={1.9} aria-hidden="true" />
              <h3 className="mt-4 font-bold text-white">{title}</h3>
              <p className="mt-2 text-sm leading-6 text-clinic-muted">{text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Process() {
  return (
    <section className="bg-clinic-bg px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <SectionHeading title="Cum funcționează" align="center" />
        <ol className="mt-10 grid gap-4 md:grid-cols-4">
          {steps.map((step, index) => (
            <li key={step} className="rounded-lg border border-white/10 bg-slate-900/70 p-5">
              <span className="grid h-10 w-10 place-items-center rounded-lg bg-cyan-300 text-sm font-extrabold text-slate-950">
                {index + 1}
              </span>
              <p className="mt-5 text-base font-semibold leading-7 text-white">{step}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function About() {
  return (
    <section id="despre" className="scroll-mt-24 border-y border-white/10 bg-clinic-panel px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1fr_0.8fr] lg:items-center">
        <div>
          <SectionHeading title="Despre Electro Clinic" />
          <p className="mt-5 text-lg leading-8 text-clinic-muted">
            Electro Clinic este un service local din Câmpulung Moldovenesc, dedicat reparațiilor
            și mentenanței pentru dispozitive electronice. Oferim ajutor pentru telefoane,
            laptopuri, calculatoare, tablete, console și alte echipamente care au nevoie de
            verificare, curățare sau reparații.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <CtaButton
              href="#contact"
              onClick={(event) => handleSectionLink(event, "contact")}
              variant="secondary"
              icon={<ArrowRight size={18} aria-hidden="true" />}
            >
              Solicită reparație
            </CtaButton>
            <CtaButton href={siteConfig.phoneHref} variant="ghost" icon={<Phone size={18} aria-hidden="true" />}>
              {siteConfig.phoneDisplay}
            </CtaButton>
          </div>
        </div>

        <div className="rounded-lg border border-cyan-300/20 bg-slate-950/55 p-6 shadow-card">
          <div className="flex items-center gap-3 text-cyan-100">
            <Sparkles size={22} aria-hidden="true" />
            <h3 className="font-display text-2xl font-bold text-white">Practic. Local. Tehnic.</h3>
          </div>
          <p className="mt-4 text-sm leading-6 text-clinic-muted">
            Accentul este pe evaluarea problemei și pe comunicarea clară înainte de intervenție.
            Pentru fiecare dispozitiv, verificarea decide ce opțiuni sunt potrivite.
          </p>
        </div>
      </div>
    </section>
  );
}

function Contact() {
  return (
    <section id="contact" className="scroll-mt-24 bg-clinic-bg px-4 py-16 sm:px-6 sm:py-24 lg:px-8">
      <div className="mx-auto max-w-6xl">
        <SectionHeading
          title="Contact și locație"
          text="Sună direct sau vino la stand pentru verificarea dispozitivului. Locația este lângă Magazinul de Vânătoare."
        />

        <div className="mt-10 grid gap-6 lg:grid-cols-[0.86fr_1fr]">
          <ContactDetails />
          <ContactForm />
        </div>

        <div className="mt-6 overflow-hidden rounded-lg border border-white/10 bg-slate-900 shadow-card">
          <iframe
            title="Hartă Google Maps pentru Electro Clinic"
            src={siteConfig.mapEmbedUrl}
            className="h-80 w-full border-0"
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />
        </div>

        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <CtaButton
            href={siteConfig.mapsUrl}
            target="_blank"
            rel="noreferrer"
            variant="secondary"
            icon={<NavigationIcon size={18} aria-hidden="true" />}
          >
            Deschide în Google Maps
          </CtaButton>
          <CtaButton href={siteConfig.phoneHref} icon={<Phone size={18} aria-hidden="true" />}>
            Sună acum
          </CtaButton>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  return (
    <>
      <Navigation />
      <main>
        <Hero />
        <Services />
        <WhyChooseUs />
        <Process />
        <About />
        <Contact />
      </main>
      <Footer />
      <a
        href={siteConfig.phoneHref}
        className="fixed bottom-4 right-4 z-50 grid h-14 w-14 place-items-center rounded-full bg-cyan-300 text-slate-950 shadow-glow md:hidden"
        aria-label="Sună acum la Electro Clinic"
      >
        <Phone size={22} aria-hidden="true" />
      </a>
    </>
  );
}
