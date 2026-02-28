// web_site/src/content/config.ts
import { z, defineCollection } from 'astro:content';

const charactersCollection = defineCollection({
  type: 'data',
  schema: z.object({
    id: z.string(),
    characterName: z.string(),
    identityName: z.string(),
    isDefault: z.boolean(),
    grade: z.number(), 
    releaseDate: z.string(),
    
    // 🚀 새로 추가된 이미지 포커스 위치
    imagePosition: z.string().default('center'),

    keywords: z.array(z.string()),
    skills: z.object({
      skill1: z.object({ type: z.string(), attribute: z.string() }),
      skill2: z.object({ type: z.string(), attribute: z.string() }),
      skill3: z.object({ type: z.string(), attribute: z.string() }),
      special1: z.object({ type: z.string(), attribute: z.string() }).optional(),
      special2: z.object({ type: z.string(), attribute: z.string() }).optional(),
      special3: z.object({ type: z.string(), attribute: z.string() }).optional(),
    }),
    defense: z.object({ type: z.string(), attribute: z.string() }),
    affiliation: z.array(z.string()), 
    image_url: z.string(),
  }),
});

export const collections = { 'characters': charactersCollection };