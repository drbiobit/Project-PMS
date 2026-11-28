import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import Layout from '@theme/Layout';
import styles from './index.module.css';

const features = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" /><path d="M11 8v6M8 11h6" /></svg>
    ),
    title: 'Multimodal search',
    desc: 'Images, videos, and audio in one index — search them all with plain words.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>
    ),
    title: 'Gallery + lightbox',
    desc: 'A responsive photo gallery with a full-page viewer: zoom, pan, swipe, download.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><path d="M12 3l1.9 4.8L18.7 9.7l-4.8 1.9L12 16.4l-1.9-4.8L5.3 9.7l4.8-1.9z" /><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></svg>
    ),
    title: 'Local AI model',
    desc: 'EmbeddingGemma-2 runs on your machine via llama.cpp — 768-d vectors, no cloud.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><path d="M22 12h-4l-3 8L9 4l-3 8H2" /></svg>
    ),
    title: 'Incremental index',
    desc: 'Re-runs only embed new files — a 10,000-photo library stays fast.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><path d="M23 4v6h-6" /><path d="M1 20v-6h6" /><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15" /></svg>
    ),
    title: 'Pluggable endpoint',
    desc: 'Point the app at any local OpenAI-compatible server — Ollama, vLLM, llama-server.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" width="22" height="22"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
    ),
    title: '100% local',
    desc: 'Model, database, and server all on your hardware — no API keys, no data leaves home.',
  },
];

const docs = [
  { to: 'installer', title: 'Installer', desc: 'One command: checks Docker, writes the compose file, opens the gallery.' },
  { to: 'deployment', title: 'Deployment', desc: 'Docker images, GPU variants, compose, endpoints and env vars.' },
  { to: 'architecture', title: 'Architecture', desc: 'The embedding engine, the database, and the search math.' },
  { to: 'usage', title: 'Usage', desc: 'The gallery, searching, the TUI, the CLI, and configuration.' },
  { to: 'files', title: 'Files', desc: 'Every file in the repository and what it does.' },
  { to: 'reference', title: 'Embedding Reference', desc: 'EmbeddingGemma-2 via llama.cpp — verified flags, formats, limits.' },
];

export default function Home() {
  const heroShot = useBaseUrl('/img/pms-gallery.svg');
  return (
    <Layout
      title="PMS — local-first multimodal media search"
      description="PMS is a local-first multimodal media search: embed your photos, videos and audio with EmbeddingGemma-2 and find them with plain words. No cloud, no API keys.">
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.heroScrim} />
          <div className={styles.heroInner}>
            <div className={styles.heroCopy}>
              <div className={styles.badge}>Local-first · 100% offline</div>
              <h1 className={styles.heroTitle}>
                Search your photos, videos &amp; audio <span className={styles.accent}>with plain words.</span>
              </h1>
              <p className={styles.heroSub}>
                PMS runs the <strong>EmbeddingGemma-2</strong> multimodal AI model locally (via
                llama.cpp), turns every image, video, and audio file in your folder into a
                semantic vector, and lets you search your whole collection with natural
                language.
              </p>
              <div className={styles.ctaRow}>
                <Link className="button button--lg" style={{ background: '#3ddc84', color: '#07140c', fontWeight: 800, border: 'none' }} to="introduction">
                  Start the documentation
                </Link>
                <Link
                  className="button button--lg"
                  style={{ background: 'transparent', color: '#e8ecf1', border: '1px solid #2f3a45' }}
                  href="https://github.com/drbiobit/Project-PMS">
                  View on GitHub
                </Link>
              </div>
              <div className={styles.pills}>
                <span className={styles.pill}>Python 3.10+</span>
                <span className={styles.pill}>Docker</span>
                <span className={styles.pill}>No API keys</span>
                <span className={styles.pill}>Apache-2.0</span>
              </div>
            </div>
            <div className={styles.heroShot}>
              <div className={styles.frame}>
                <div className={styles.shine} />
                <div className={styles.frameBar}>
                  <span className={`${styles.dot} ${styles.r}`} />
                  <span className={`${styles.dot} ${styles.y}`} />
                  <span className={`${styles.dot} ${styles.g}`} />
                  <span className={styles.urlBar}><b>localhost</b>:9090/</span>
                </div>
                <img className={styles.frameShot} src={heroShot} alt="PMS gallery — search your media with plain words" />
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionInner}>
            <div className={styles.eyebrow}>What it does</div>
            <h2 className={styles.sectionTitle}>Your whole media library, searchable</h2>
            <p className={styles.sectionDesc}>
              No cloud, no API keys, no third-party accounts. It runs on your own box — your
              media never leaves your network.
            </p>
            <div className={styles.features}>
              {features.map((f) => (
                <div key={f.title} className={styles.feature}>
                  <div className={styles.featIcon}>{f.icon}</div>
                  <h3 className={styles.featTitle}>{f.title}</h3>
                  <p className={styles.featDesc}>{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.sectionAlt}>
          <div className={styles.sectionInner}>
            <div className={styles.eyebrow}>Quick start</div>
            <div className={styles.quickRow}>
              <div className={styles.quickCopy}>
                <h2 className={styles.sectionTitle}>Up in 30 seconds</h2>
                <p className={styles.sectionDesc}>
                  One command checks Docker, asks where your media is, lets you pick the
                  image, asks for a username/password, and opens the gallery.
                </p>
              </div>
              <div className={styles.codeBlock}>
                <div className={styles.codeBar}>
                  <span className={`${styles.dot} ${styles.r}`} />
                  <span className={`${styles.dot} ${styles.y}`} />
                  <span className={`${styles.dot} ${styles.g}`} />
                </div>
                <pre className={styles.codeBody}><code><span className={styles.dim}># one-shot installer…</span>\ncurl -fsSL <span className={styles.green}>https://raw.githubusercontent.com/drbiobit/Project-PMS/main/install.sh</span> | bash\n\n<span className={styles.dim}># …or plain Docker</span>\ndocker run -d -p 9090:9090 -v /path/to/media:/media:ro \\\n  -v pms-data:/data <span className={styles.green}>ghcr.io/drbiobit/project-pms:cpu</span></code></pre>
              </div>
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionInner}>
            <div className={styles.eyebrow}>Documentation</div>
            <h2 className={styles.sectionTitle}>Guides &amp; references</h2>
            <p className={styles.sectionDesc}>
              Everything you need — from first deploy to reading the source.
            </p>
            <div className={styles.docsGrid}>
              {docs.map((d) => (
                <Link key={d.to} to={d.to} className={styles.docsCard}>
                  <div className={styles.docsCardTitle}>{d.title}</div>
                  <div className={styles.docsCardDesc}>{d.desc}</div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
