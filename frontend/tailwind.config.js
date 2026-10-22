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
        // ─── İrtifa "Aetheria" — Kapadokya şafağı paleti ───
        // Zemin: şafak öncesi gök (koyu indigo/lacivert yüzeyler). Metin ve ince kenarlıklar:
        // peribacası tüfünün sıcak nötrleri (kum/bej). Birincil vurgu: gün doğumu amber/terakota;
        // gök mavisi yalnız ikincil (bilgi/link). Token adları sabit — sayfa sınıfları değişmez.
        'background': '#0b1020',
        'surface': '#10162b',
        'surface-dim': '#0b1020',
        'surface-bright': '#222a45',
        'surface-container-lowest': '#0b1020',
        'surface-container-low': '#0e1428',
        'surface-container': '#141a33',
        'surface-container-high': '#1c2340',
        'surface-container-highest': '#283050',
        'surface-variant': '#1c2340',
        'surface-tint': '#f2a65a',
        'on-surface': '#ece2d0',          // tüf beji — saf beyaz yerine göz yormayan sıcak metin
        'on-background': '#ece2d0',
        'on-surface-variant': '#b3a893',  // ikincil metin (kil/kum)
        'inverse-surface': '#ece2d0',
        'inverse-on-surface': '#10162b',
        'outline': '#7a705f',
        'outline-variant': '#3b3a3f',

        // Primary — gün doğumu amberi / terakota (düğme, aktif öğe, odak halkası)
        'primary': '#f2a65a',
        'primary-fixed': '#fcdcb6',
        'primary-fixed-dim': '#f6c08a',
        'on-primary': '#2a1606',
        'primary-container': '#ad5428',
        'on-primary-container': '#fff7ee',
        'on-primary-fixed': '#2a1606',
        'on-primary-fixed-variant': '#a5521f',
        'inverse-primary': '#a5521f',

        // Secondary — gök mavisi (bilgi, link; ikincil vurgu)
        'secondary': '#38bdf8',
        'secondary-fixed': '#bae6fd',
        'secondary-fixed-dim': '#7dd3fc',
        'on-secondary': '#082f49',
        'secondary-container': '#0369a1',
        'on-secondary-container': '#e0f2fe',
        'on-secondary-fixed': '#0c4a6e',
        'on-secondary-fixed-variant': '#0284c7',

        // Tertiary — tüf taşı sıcak nötrleri (kart dolgusu/kenarlık: /8–/12 opaklıkta)
        'tertiary': '#e9dcc7',
        'tertiary-fixed': '#f5ede0',
        'tertiary-fixed-dim': '#ddcdb3',
        'on-tertiary': '#3b3226',
        'tertiary-container': '#6b5d48',
        'on-tertiary-container': '#f8f1e6',
        'on-tertiary-fixed': '#241d14',
        'on-tertiary-fixed-variant': '#4a3f30',

        // Error — kırmızı korunur
        'error': '#f87171',
        'on-error': '#450a0a',
        'error-container': '#991b1b',
        'on-error-container': '#fef2f2',

        // ─── Durum renkleri (kontrol kartları yeşil/sarı, rozetler, uyarılar) ───
        // Semantik kalır; warning şafak amberiyle karışmasın diye sarıya (#facc15) çekildi.
        'success': '#4ade80',
        'on-success': '#052e16',
        'warning': '#facc15',
        'on-warning': '#422006',
        'danger': '#f87171',
        'on-danger': '#450a0a',
        'info': '#38bdf8',
        'on-info': '#082f49',
        'surface-light': '#1c2340', // kart içi açık yüzey

        // ─── Balon vurgu paleti — yalnız balon rozetleri ve grafikler (az, dengeli) ───
        'balloon-red': '#ff6b6b',
        'balloon-orange': '#ff9f5a',
        'balloon-amber': '#ffc24b',
        'balloon-teal': '#36d6c3',
        'balloon-sky': '#5ba8ff',
        'balloon-magenta': '#f074c0',
        'balloon-purple': '#b493ff',
        'balloon-green': '#7bd88f',
        'sunrise': '#f2a65a',
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
