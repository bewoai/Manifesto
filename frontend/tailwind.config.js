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
        // ─── Şafak Öncesi Kapadokya teması (twilight sky + balon vurguları) ───
        // Token isimleri korunur (Material 3), değerler şafak paletine remap edilir.
        'background': '#181225',
        'surface': '#181225',
        'surface-dim': '#120d1d',
        'surface-bright': '#473869',
        'surface-container-lowest': '#1f1730',
        'surface-container-low': '#241b38',
        'surface-container': '#2a2040',
        'surface-container-high': '#332748',
        'surface-container-highest': '#3d2f54',
        'surface-variant': '#3a2e52',
        'surface-tint': '#ff9f5a',
        'on-surface': '#f4ecde',
        'on-background': '#f4ecde',
        'on-surface-variant': '#c2b2d6',
        'inverse-surface': '#ece6df',
        'inverse-on-surface': '#2a2040',
        'outline': '#8e7ca8',
        'outline-variant': '#4a3d63',

        // Primary — gün doğumu kehribar/mercan (balon parıltısı)
        'primary': '#ff9f5a',
        'primary-fixed': '#ffd9bd',
        'primary-fixed-dim': '#ffbd8e',
        'on-primary': '#43210a',
        'primary-container': '#e8843a',
        'on-primary-container': '#3a1606',
        'on-primary-fixed': '#331403',
        'on-primary-fixed-variant': '#7a3a14',
        'inverse-primary': '#9a4600',

        // Secondary — balon turkuazı / gökyüzü
        'secondary': '#6fe0d0',
        'secondary-fixed': '#9ff0e4',
        'secondary-fixed-dim': '#5cd6c4',
        'on-secondary': '#063830',
        'secondary-container': '#2e8e84',
        'on-secondary-container': '#c9f6ef',
        'on-secondary-fixed': '#022b24',
        'on-secondary-fixed-variant': '#0c5b50',

        // Tertiary — gök mavisi
        'tertiary': '#9dc0ff',
        'tertiary-fixed': '#d6e4ff',
        'tertiary-fixed-dim': '#b3cdff',
        'on-tertiary': '#0c2a52',
        'tertiary-container': '#3e5c8a',
        'on-tertiary-container': '#d6e4ff',
        'on-tertiary-fixed': '#04173a',
        'on-tertiary-fixed-variant': '#274a78',

        // Error — kırmızı korunur
        'error': '#ffb4ab',
        'on-error': '#5a0f0c',
        'error-container': '#8c2f2a',
        'on-error-container': '#ffdad6',

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
