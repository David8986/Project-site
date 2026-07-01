import {
  BatteryCharging,
  Brush,
  Cpu,
  Gamepad2,
  Laptop,
  MapPinned,
  MonitorCog,
  ShieldCheck,
  Smartphone,
  TabletSmartphone,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";

export const phoneDisplay = "0734 369 763";
export const phoneHref = "tel:0734369763";
export const mapsUrl =
  "https://www.google.com/maps/search/?api=1&query=Strada%20Alexandru%20Bogza%20nr.%204%2C%20Stand%2015%2C%20C%C3%A2mpulung%20Moldovenesc%2C%20Suceava%2C%20Romania";
export const mapEmbedUrl =
  "https://www.google.com/maps?q=Strada%20Alexandru%20Bogza%20nr.%204%2C%20Stand%2015%2C%20C%C3%A2mpulung%20Moldovenesc%2C%20Suceava%2C%20Romania&output=embed";

export const siteConfig = {
  businessName: "Electro Clinic",
  addressLine: "Strada Alexandru Bogza nr. 4, Stand 15",
  cityLine: "Câmpulung Moldovenesc, Suceava",
  landmark: "Lângă Magazinul de Vânătoare",
  phoneDisplay,
  phoneHref,
  mapsUrl,
  mapEmbedUrl,
  // TODO: Replace with the real Facebook page URL.
  facebookUrl: "#facebook-url-de-inlocuit",
  // TODO: Replace with a real endpoint such as Formspree, EmailJS, a backend API, or WhatsApp bridge.
  formEndpoint: "",
  // TODO: Replace with the email address used by the shop if email routing is added.
  contactEmail: "contact-de-inlocuit@electro-clinic.ro",
};

export const navItems = [
  { label: "Acasă", href: "#acasa" },
  { label: "Servicii", href: "#servicii" },
  { label: "Despre noi", href: "#despre" },
  { label: "Contact", href: "#contact" },
];

export type Service = {
  title: string;
  description: string;
  Icon: LucideIcon;
};

export const services: Service[] = [
  {
    title: "Telefoane",
    Icon: Smartphone,
    description:
      "Diagnosticare și intervenții pentru probleme de încărcare, baterie, ecran, software și funcționare generală.",
  },
  {
    title: "Tablete",
    Icon: TabletSmartphone,
    description:
      "Verificare pentru tablete cu probleme de alimentare, afișaj, conectori, sistem sau performanță.",
  },
  {
    title: "Laptopuri",
    Icon: Laptop,
    description:
      "Evaluare pentru laptopuri care pornesc greu, se încălzesc, au probleme software sau componente care necesită verificare.",
  },
  {
    title: "Calculatoare și PC-uri",
    Icon: MonitorCog,
    description:
      "Suport pentru unități desktop, upgrade-uri, curățare, verificare componente și probleme de funcționare.",
  },
  {
    title: "Console de gaming",
    Icon: Gamepad2,
    description:
      "Diagnoză pentru console cu probleme de alimentare, temperatură, conectivitate, zgomot sau funcționare.",
  },
  {
    title: "GPS și navigație",
    Icon: MapPinned,
    description:
      "Verificare pentru sisteme de navigație și dispozitive GPS, în funcție de model și de problema constatată.",
  },
  {
    title: "Curățare și mentenanță",
    Icon: Brush,
    description:
      "Curățare, verificare preventivă și mentenanță pentru dispozitive folosite zilnic, în funcție de starea lor.",
  },
  {
    title: "Accesorii pentru telefoane",
    Icon: BatteryCharging,
    description:
      "Accesorii utile precum huse, folii, cabluri sau încărcătoare, disponibile în funcție de stoc.",
  },
];

export const reasons = [
  {
    title: "Service local în Câmpulung Moldovenesc",
    text: "Ai un punct de contact apropiat, cu adresă clară și program afișat.",
    Icon: MapPinned,
  },
  {
    title: "Mai multe tipuri de dispozitive",
    text: "Poți veni cu telefoane, tablete, laptopuri, PC-uri, console sau GPS-uri pentru evaluare.",
    Icon: Cpu,
  },
  {
    title: "Comunicare clară înainte de intervenție",
    text: "Discutăm problema și opțiunile înainte de a continua cu lucrarea.",
    Icon: ShieldCheck,
  },
  {
    title: "Diagnoză și evaluare",
    text: "Pornim de la verificarea dispozitivului, apoi stabilim ce poate fi făcut.",
    Icon: Wrench,
  },
  {
    title: "Soluții utile pentru dispozitivele tale",
    text: "Pe lângă reparații, poți găsi accesorii și recomandări practice.",
    Icon: Zap,
  },
];

export const steps = [
  "Adu dispozitivul sau sună-ne.",
  "Verificăm problema și discutăm opțiunile.",
  "Stabilim intervenția necesară.",
  "Ridici dispozitivul după finalizarea lucrării.",
];

export const workingHours = [
  { day: "Luni - Vineri", time: "09:00 - 18:00" },
  { day: "Sâmbătă", time: "10:00 - 14:00" },
  { day: "Duminică", time: "Închis" },
];
