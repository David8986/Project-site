# Electro Clinic

Site one-page pentru Electro Clinic, service local GSM și IT din Câmpulung Moldovenesc.

## Rulare locală

```bash
pnpm install
pnpm dev
```

## Build pentru producție

```bash
pnpm build
pnpm preview
```

Conținutul optimizat pentru deploy este generat în `dist/` și poate fi publicat pe Netlify, Vercel, Cloudflare Pages sau orice hosting static.

## Valori de înlocuit

Valorile marcate în `src/data/site.ts` trebuie actualizate când sunt disponibile:

- URL Facebook real
- endpoint formular contact
- email de contact
- eventuală cheie sau variantă dedicată pentru map embed

Formularul afișează momentan o stare de succes simulată când nu există endpoint configurat.
