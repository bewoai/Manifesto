/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './*.js',
    './pages/*.js',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ─── İrtifa Lacivert & Gök Mavisi Teması ───
        'background': '#020617', // Slate 950 (Koyu Lacivert)
        'surface': '#0f172a',    // Slate 900 (Lacivert)
        'surface-dim': '#020617',
        'surface-bright': '#1e293b',
        'surface-container-lowest': '#020617',
        'surface-container-low': '#0b1120',
        'surface-container': '#0f172a',
        'surface-container-high': '#1e293b',
        'surface-container-highest': '#334155',
        'surface-variant': '#1e293b',
        'surface-tint': '#38bdf8',
        'on-surface': '#ffffff', // Beyaz
        'on-background': '#ffffff', // Beyaz
        'on-surface-variant': '#94a3b8',
        'inverse-surface': '#f8fafc',
        'inverse-on-surface': '#0f172a',
        'outline': '#475569',
        'outline-variant': '#334155',

        // Primary — Gök Mavisi (Sky Blue)
        'primary': '#38bdf8',
        'primary-fixed': '#bae6fd',
        'primary-fixed-dim': '#7dd3fc',
        'on-primary': '#0369a1',
        'primary-container': '#0284c7',
        'on-primary-container': '#f0f9ff',
        'on-primary-fixed': '#0c4a6e',
        'on-primary-fixed-variant': '#0284c7',
        'inverse-primary': '#0284c7',

        // Secondary — Lacivert / Mavi
        'secondary': '#818cf8',
        'secondary-fixed': '#c7d2fe',
        'secondary-fixed-dim': '#a5b4fc',
        'on-secondary': '#3730a3',
        'secondary-container': '#4f46e5',
        'on-secondary-container': '#e0e7ff',
        'on-secondary-fixed': '#312e81',
        'on-secondary-fixed-variant': '#4338ca',

        // Tertiary — Açık Beyaz/Gri Mavi
        'tertiary': '#cbd5e1',
        'tertiary-fixed': '#f1f5f9',
        'tertiary-fixed-dim': '#e2e8f0',
        'on-tertiary': '#334155',
        'tertiary-container': '#475569',
        'on-tertiary-container': '#f8fafc',
        'on-tertiary-fixed': '#0f172a',
        'on-tertiary-fixed-variant': '#1e293b',

        // Error — kırmızı korunur
        'error': '#f87171',
        'on-error': '#450a0a',
        'error-container': '#991b1b',
        'on-error-container': '#fef2f2',

        // ─── Balon vurgu paleti (illüstrasyon + 3D ikon + grafik) ───
        'balloon-red': '#ff6b6b',
        'balloon-orange': '#ff9f5a',
        'balloon-amber': '#ffc24b',
        'balloon-teal': '#36d6c3',
        'balloon-sky': '#5ba8ff',
        'balloon-magenta': '#f074c0',
        'balloon-purple': '#b493ff',
        'balloon-green': '#7bd88f',
        'sunrise': '#ffb066',
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        lg: '0.5rem',
        xl: '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
        '4xl': '2rem',
        '5xl': '2.5rem',
        full: '9999px',
      },
      spacing: {
        gutter: '32px',
        'section-gap': '120px',
        'container-padding-desktop': '64px',
        'container-padding-mobile': '24px',
        unit: '8px',
      },
      fontFamily: {
        'headline': ['"Bricolage Grotesque"', 'Plus Jakarta Sans', 'sans-serif'],
        'body': ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
      fontSize: {
        'headline-sm': ['24px', { lineHeight: '32px', fontWeight: '600' }],
        'body-md': ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'headline-lg': ['40px', { lineHeight: '48px', fontWeight: '600' }],
        'body-lg': ['18px', { lineHeight: '28px', fontWeight: '400' }],
        'headline-md': ['32px', { lineHeight: '40px', fontWeight: '600' }],
        'label-md': ['14px', { lineHeight: '20px', letterSpacing: '0.05em', fontWeight: '500' }],
        'display-lg': ['64px', { lineHeight: '72px', letterSpacing: '-0.02em', fontWeight: '700' }],
      },
      animation: {
        'morph': 'morph 20s ease-in-out infinite',
        'dash': 'dash 20s linear infinite',
      },
      keyframes: {
        morph: {
          '0%': { borderRadius: '42% 58% 70% 30% / 45% 45% 55% 55%' },
          '50%': { borderRadius: '70% 30% 46% 54% / 30% 29% 71% 70%' },
          '100%': { borderRadius: '42% 58% 70% 30% / 45% 45% 55% 55%' },
        },
        dash: {
          to: { strokeDashoffset: '-100' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
