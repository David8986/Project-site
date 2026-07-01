import { FormEvent, useState } from "react";
import { Send } from "lucide-react";
import { submitRepairRequest } from "../utils/contact";

const deviceOptions = [
  "Telefon",
  "Tabletă",
  "Laptop",
  "Calculator / PC",
  "Consolă",
  "GPS / navigație",
  "Alt dispozitiv",
];

export function ContactForm() {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("loading");

    const form = event.currentTarget;
    const formData = new FormData(form);

    try {
      await submitRepairRequest({
        name: String(formData.get("name") ?? ""),
        phone: String(formData.get("phone") ?? ""),
        deviceType: String(formData.get("deviceType") ?? ""),
        message: String(formData.get("message") ?? ""),
      });
      form.reset();
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-white/10 bg-clinic-panel/80 p-6 shadow-card"
    >
      <h3 className="font-display text-2xl font-bold text-white">Solicită o verificare</h3>
      <p className="mt-2 text-sm leading-6 text-clinic-muted">
        Lasă câteva detalii, iar formularul poate fi conectat ulterior la un serviciu de trimitere.
      </p>

      <div className="mt-6 grid gap-4">
        <label htmlFor="repair-name" className="grid gap-2 text-sm font-semibold text-slate-200">
          Nume
          <input
            id="repair-name"
            name="name"
            required
            autoComplete="name"
            className="min-h-12 rounded-lg border border-white/10 bg-slate-950/55 px-4 text-base text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/25"
            placeholder="Numele tău"
          />
        </label>

        <label htmlFor="repair-phone" className="grid gap-2 text-sm font-semibold text-slate-200">
          Telefon
          <input
            id="repair-phone"
            name="phone"
            required
            type="tel"
            autoComplete="tel"
            className="min-h-12 rounded-lg border border-white/10 bg-slate-950/55 px-4 text-base text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/25"
            placeholder="0734 369 763"
          />
        </label>

        <label htmlFor="repair-device-type" className="grid gap-2 text-sm font-semibold text-slate-200">
          Tip dispozitiv
          <select
            id="repair-device-type"
            name="deviceType"
            required
            className="min-h-12 rounded-lg border border-white/10 bg-slate-950/55 px-4 text-base text-white outline-none transition focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/25"
            defaultValue=""
          >
            <option value="" disabled>
              Alege dispozitivul
            </option>
            {deviceOptions.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </select>
        </label>

        <label htmlFor="repair-message" className="grid gap-2 text-sm font-semibold text-slate-200">
          Descriere scurtă a problemei
          <textarea
            id="repair-message"
            name="message"
            required
            rows={4}
            className="resize-y rounded-lg border border-white/10 bg-slate-950/55 px-4 py-3 text-base text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-300 focus:ring-2 focus:ring-cyan-300/25"
            placeholder="Spune pe scurt ce se întâmplă cu dispozitivul."
          />
        </label>
      </div>

      <button
        type="submit"
        disabled={status === "loading"}
        className="mt-6 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 shadow-glow transition hover:bg-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-200 focus-visible:ring-offset-2 focus-visible:ring-offset-clinic-bg disabled:cursor-wait disabled:opacity-70"
      >
        <Send size={17} aria-hidden="true" />
        {status === "loading" ? "Se trimite..." : "Trimite solicitarea"}
      </button>

      {status === "success" ? (
        <p className="mt-4 rounded-lg border border-emerald-300/30 bg-emerald-300/10 p-3 text-sm text-emerald-100">
          Solicitarea a fost înregistrată ca simulare. Pentru urgențe, sună direct la{" "}
          <a className="font-bold underline" href="tel:0734369763">
            0734 369 763
          </a>
          .
        </p>
      ) : null}

      {status === "error" ? (
        <p className="mt-4 rounded-lg border border-red-300/30 bg-red-300/10 p-3 text-sm text-red-100">
          Formularul nu a putut fi trimis. Te rugăm să suni direct la 0734 369 763.
        </p>
      ) : null}
    </form>
  );
}
