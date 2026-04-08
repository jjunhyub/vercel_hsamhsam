// lib/translation.ts
export type NodeTranslation = {
  en: string;
  ko: string;
};

export type TranslationMap = Record<string, Record<string, NodeTranslation>>;

export function normalizeTranslationJson(raw: any): TranslationMap {
  const out: TranslationMap = {};

  const images = Array.isArray(raw?.images) ? raw.images : [];
  for (const image of images) {
    const imageId = String(image?.image_id || '').trim();
    if (!imageId) continue;
    out[imageId] = image?.nodes || {};
  }

  return out;
}