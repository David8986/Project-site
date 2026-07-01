import type { MouseEvent } from "react";

export function handleSectionLink(event: MouseEvent<HTMLAnchorElement>, sectionId: string) {
  event.preventDefault();

  const target = document.getElementById(sectionId);
  if (!target) {
    return;
  }

  target.scrollIntoView({ behavior: "smooth", block: "start" });
  window.history.pushState(null, "", `#${sectionId}`);
}
