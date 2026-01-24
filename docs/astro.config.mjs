import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import starlightThemeGalaxy from "starlight-theme-galaxy";

export default defineConfig({
  // site and base are set via CLI args in CI (from actions/configure-pages)
  integrations: [
    starlight({
      title: "vcpkg-harbor",
      description: "Binary cache server for vcpkg with plugin-based storage backends",
      plugins: [starlightThemeGalaxy()],
      customCss: ["./src/styles/custom.css"],
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/rennerdo30/vcpkg-harbor" },
      ],
      sidebar: [
        { label: "Home", slug: "index" },
        {
          label: "Getting Started",
          items: [
            { label: "Installation", slug: "getting-started/installation" },
            { label: "Quick Start", slug: "getting-started/quickstart" },
            { label: "Configuration", slug: "getting-started/configuration" },
          ],
        },
        {
          label: "User Guide",
          items: [
            { label: "Storage Backends", slug: "user-guide/storage-backends" },
            { label: "Authentication", slug: "user-guide/authentication" },
            { label: "Dashboard", slug: "user-guide/dashboard" },
            { label: "Metrics", slug: "user-guide/metrics" },
          ],
        },
        {
          label: "Deployment",
          items: [
            { label: "Docker", slug: "deployment/docker" },
            { label: "Kubernetes", slug: "deployment/kubernetes" },
          ],
        },
        {
          label: "Development",
          items: [
            { label: "Contributing", slug: "development/contributing" },
            { label: "Architecture", slug: "development/architecture" },
            { label: "Testing", slug: "development/testing" },
          ],
        },
        { label: "API Reference", slug: "api-reference" },
      ],
    }),
  ],
});
