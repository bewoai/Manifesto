/** @type {import('tailwindcss').Config} */

// ─── İrtifa renk sistemi ───────────────────────────────────────────────
// Değerler style.css'teki CSS değişkenlerinden gelir (RGB kanalları), böylece iki tema
// aynı sınıflarla çalışır: "Kısık Tüf" (varsayılan, :root) ve "Yumuşak Grafit"
// ([data-theme="graphite"]). Token adları eski sayfalarla uyum için korunur.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: [
    './index.html',
    './*.js',
    './pages/*.js',
  ],
  darkMode: ['class', '[data-theme="graphite"]'],
  theme: {
    extend: {
      colors: {
        // Zemin ve yüzeyler (tüf taşı katmanları)
        'background': v('ground'),
        'surface': v('ground'),
        'surface-dim': v('ground'),
        'surface-bright': v('raised'),
        'surface-container-lowest': v('rail'),
        'surface-container-low': v('well'),
        'surface-container': v('panel'),
        'surface-container-high': v('raised'),
        'surface-container-highest': v('rail'),
        'surface-variant': v('well'),
        'surface-light': v('raised'),
        'surface-tint': v('primary'),
        'rail': v('rail'),
        'panel': v('panel'),
        'raised': v('raised'),
        'well': v('well'),
        'line': v('line'),

        // Metin
        'on-surface': v('ink'),
        'on-background': v('ink'),
        'on-surface-variant': v('ink-2'),
        'ink': v('ink'),
        'ink-2': v('ink-2'),
        'inverse-surface': v('ink'),
        'inverse-on-surface': v('panel'),
        'outline': v('outline'),
        'outline-variant': v('line'),

        // Tek arayüz vurgusu: soluk lapis (Göreme kaya kiliseleri)
        'primary': v('primary'),
        'primary-fixed': v('primary-soft'),
        'primary-fixed-dim': v('primary-hover'),
        'on-primary': v('on-primary'),
        'primary-container': v('primary-soft'),
        'on-primary-container': v('primary-deep'),
        'on-primary-fixed': v('primary-deep'),
        'on-primary-fixed-variant': v('primary'),
        'inverse-primary': v('primary-soft'),

        // İkincil = bilgi mavisi-gri
        'secondary': v('info'),
        'secondary-fixed': v('primary-soft'),
        'secondary-fixed-dim': v('info'),
        'on-secondary': v('on-primary'),
        'secondary-container': v('primary-soft'),
        'on-secondary-container': v('primary-deep'),

        // Tertiary = mürekkep; /5–/15 opaklıkla ince çizgi ve dolgu olarak kullanılır
        'tertiary': v('ink'),
        'on-tertiary': v('panel'),

        // Durum renkleri (anlamlı: yeşil doğrulandı, sarı kontrol, kırmızı hata)
        'success': v('success'),
        'on-success': v('on-flag'),
        'warning': v('warning'),
        'on-warning': v('on-flag'),
        'danger': v('danger'),
        'on-danger': v('on-flag'),
        'error': v('danger'),
        'on-error': v('on-flag'),
        'error-container': v('danger-soft'),
        'on-error-container': v('danger-deep'),
        'info': v('info'),
        'on-info': v('on-flag'),

        // Sabah uçuş bayrağı (düz bez blokları)
        'flag-go': v('flag-go'),
        'flag-hold': v('flag-hold'),
        'flag-stop': v('flag-stop'),
        'on-flag': v('on-flag'),

        // Balon zarf mürekkepleri — yalnız balon kodu, zarf şeridi ve koltuk çubuğu
        'env-1': v('env-1'),
        'env-2': v('env-2'),
        'env-3': v('env-3'),
        'env-4': v('env-4'),
        'env-5': v('env-5'),
        'env-6': v('env-6'),
        'env-7': v('env-7'),
        'env-8': v('env-8'),
      },
      borderRadius: {
        DEFAULT: '0.25rem',
        md: '0.375rem',
        lg: '0.5rem',
        xl: '0.625rem',
        '2xl': '0.75rem',
        '3xl': '0.875rem',
        '4xl': '1rem',
        '5xl': '1.25rem',
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
        'headline': ['"Source Serif 4"', 'Georgia', 'serif'],
        'body': ['"Source Sans 3"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        'sans': ['"Source Sans 3"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        'mono': ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      fontSize: {
        'headline-sm': ['22px', { lineHeight: '28px', fontWeight: '600' }],
        'body-md': ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'headline-lg': ['38px', { lineHeight: '44px', fontWeight: '600', letterSpacing: '-0.01em' }],
        'body-lg': ['18px', { lineHeight: '28px', fontWeight: '400' }],
        'headline-md': ['28px', { lineHeight: '34px', fontWeight: '600', letterSpacing: '-0.005em' }],
        'label-md': ['12px', { lineHeight: '16px', letterSpacing: '0.08em', fontWeight: '600' }],
        'display-lg': ['56px', { lineHeight: '60px', letterSpacing: '-0.02em', fontWeight: '600' }],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
