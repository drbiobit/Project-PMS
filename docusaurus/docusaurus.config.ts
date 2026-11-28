import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';

// PMS documentation site (Docusaurus).
// Built by .github/workflows/pages.yml and published to
// https://drbiobit.github.io/Project-PMS/
const config: Config = {
  title: 'PMS Docs',
  tagline:
    'Local-first multimodal media search — find your photos, videos & audio with plain words. No cloud, no API keys.',
  favicon: 'img/favicon.svg',

  // The URL of your Docusaurus site without trailing slash.
  url: 'https://drbiobit.github.io',
  // Used as __dirname equivalent
  baseUrl: '/Project-PMS/',

  // Set the production url of your site here
  organizationName: 'drbiobit',
  projectName: 'Project-PMS',

  onBrokenLinks: 'throw',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  // Even if you don't use internalization, you can use this field for i18n:
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          // Remove this if your site has no docs.
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      },
    ],
  ],

  themeConfig: {
    image: 'img/pms-social.png',
    navbar: {
      title: 'PMS',
      logo: {
        alt: 'PMS logo',
        src: 'img/logo.svg',
      },
      items: [
        {to: '/', label: 'Docs', position: 'left'},
        {
          href: 'https://github.com/drbiobit/Project-PMS',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://github.com/drbiobit/Project-PMS/releases',
          label: 'Releases',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      copyright: `Copyright © ${new Date().getFullYear()} PMS. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.github,
    },
    // Local (offline) search - no external service, works on the static site.
    // Provided by the @easyops-cn/docusaurus-search-local plugin (see below).
    // @ts-expect-error - shape is defined by the plugin, not the core types
    search: {
      type: 'local',
    },
  } as any,

  // Offline, client-side search. No external API - the index is built into
  // the static site at build time.
  themes: ['@easyops-cn/docusaurus-search-local'],

};

export default config;
