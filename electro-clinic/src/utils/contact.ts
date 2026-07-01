import { siteConfig } from "../data/site";

export type RepairRequest = {
  name: string;
  phone: string;
  deviceType: string;
  message: string;
};

export async function submitRepairRequest(payload: RepairRequest) {
  if (!siteConfig.formEndpoint) {
    await new Promise((resolve) => window.setTimeout(resolve, 450));
    return { mode: "mock" as const, payload };
  }

  const response = await fetch(siteConfig.formEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error("Formularul nu a putut fi trimis.");
  }

  return { mode: "live" as const, payload };
}
