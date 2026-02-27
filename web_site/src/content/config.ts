// web_site/src/content/config.ts
import { z, defineCollection } from 'astro:content';

// 캐릭터 데이터의 구조(Schema)를 정의합니다.
const charactersCollection = defineCollection({
  type: 'data', // 마크다운이 아닌 JSON 파일 형식이므로 'data'로 설정합니다.
  schema: z.object({
    id: z.string(),
    name: z.string(),
    affiliation: z.string(),
    weapon: z.string(),
    image_url: z.string(),
  }),
});

// 외부에서 이 컬렉션을 사용할 수 있도록 내보냅니다.
export const collections = {
  'characters': charactersCollection,
};