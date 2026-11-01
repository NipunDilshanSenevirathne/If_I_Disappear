/** Free photos used on the site and in the sample home, from Unsplash, under the Unsplash License. */
export const PHOTOS: { use: string; photographer: string; id: string; page?: string }[] = [
  { use: 'Hero: a lamp in a dark room (also the sample home\'s bill scene)', photographer: 'Arun Anoop', id: 'photo-1524694344997-f872df30b642' },
  { use: 'Running water (sample photo: not the pump)', photographer: 'Gowtham AGM', id: 'photo-1696371269814-ae41fc67cf03' },
  { use: 'A warm room (landing page)', photographer: 'PhilCreates', id: 'photo-1638035661684-f5d69e44d34f' },
  { use: 'Lamp by the wall (power cut)', photographer: 'Khanh Do', id: 'photo-1704536345279-4b7dfa0c166d' },
  { use: 'Train through the hills', photographer: 'Anton Lecock', id: 'photo-1578517929167-db9ed31cd5c6' },
  { use: 'Nine Arches Bridge, Ella', photographer: 'Hendrik Cornelissen', id: 'photo-1566296314736-6eaac1ca0cb9' },
  { use: 'Phone with a QR code', photographer: 'Markus Winkler', id: 'photo-1595079676339-1534801ad6cf' },
  { use: 'Cargo ship at sea', photographer: 'Kinsey Wang', id: 'photo-1722413890417-67b8ce3f4005', page: 'https://unsplash.com/photos/a-large-cargo-ship-in-the-middle-of-the-ocean-bOGNLYidRXY' },
];

/** The sample home's own photos, made with Meta's Muse Image (prompts in backend/fixtures/base/photos.json). */
export const GENERATED: { en: string; si: string }[] = [
  { en: 'the main switch box', si: 'ප්‍රධාන ස්විච් පෙට්ටිය' },
  { en: 'a different switch box', si: 'වෙනත් ස්විච් පෙට්ටියක්' },
  { en: 'the water pump and tank', si: 'වතුර පොම්පය සහ ටැංකිය' },
  { en: 'the kitchen with the gas cylinder', si: 'ගෑස් සිලින්ඩරය තියෙන කුස්සිය' },
  { en: 'the bedroom cupboard with the white files', si: 'සුදු ෆයිල් තියෙන නිදන කාමරේ අල්මාරිය' },
];

export const FONTS = [
  { name: 'Outfit', by: 'Rodrigo Fuenzalida', license: 'SIL Open Font License 1.1' },
  { name: 'Yaldevi', by: 'Mooniak', license: 'SIL Open Font License 1.1' },
];

export const LIBRARIES = [
  { name: '@meta-sam/react, @meta-sam/parser', by: 'Meta', license: 'SAM License' },
  { name: 'Omnilingual ASR', by: 'Meta', license: 'Apache 2.0' },
  { name: 'React', by: 'Meta', license: 'MIT' },
  { name: 'Lucide icons', by: 'Lucide contributors', license: 'ISC' },
  { name: 'qrcode', by: 'Ryan Day', license: 'MIT' },
  { name: 'FastAPI, Pydantic, Pillow, FFmpeg', by: 'their authors', license: 'MIT, BSD, HPND, LGPL' },
];
