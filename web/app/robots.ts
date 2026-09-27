import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/datasets", "/settings", "/sign-in", "/sign-up"] },
    sitemap: "https://atlasmatch.co.uk/sitemap.xml",
  };
}
