import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  return [{ url: "https://atlasmatch.co.uk/", changeFrequency: "monthly", priority: 1 }];
}
