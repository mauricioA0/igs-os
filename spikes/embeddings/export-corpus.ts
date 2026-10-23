import { writeFileSync } from "node:fs";
import { experiences, knowledge, opponents } from "../../src/db/seed-data";

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

const docs = [
  ...knowledge.map((k) => ({ id: `kb:${slug(k.title)}`, type: "knowledge", text: `${k.title}. ${k.content}` })),
  ...opponents.map((o) => ({
    id: `opp:${slug(o.name)}`,
    type: "opponent",
    text: `${o.name} (${o.city}, ${o.country}). ${o.sport.replace("_", " ")}, ${o.gender}, age groups ${o.ageGroups.join("/")}, level ${o.levelScore}/10. ${o.description}`,
  })),
  ...experiences.map((e) => ({
    id: `exp:${slug(e.title)}`,
    type: "experience",
    text: `${e.title} (${e.city}, ${e.country}). ${e.durationHours}h, $${e.priceUsd} per person. ${e.description}`,
  })),
];
writeFileSync("spikes/embeddings/corpus.json", JSON.stringify(docs, null, 2));
console.log(docs.length, "docs");
