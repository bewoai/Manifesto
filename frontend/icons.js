/* ═══════════════════════════════════════════════════════════════════
   İrtifa — 3D İkon Seti (Kapadokya/balon paleti)
   icon3d(name, size) → parlak gradyan kabartma SVG (gloss + gölge + rim).
   Çevrimdışı/vektörel; Material Symbols'ın yerine vurgulu yerlerde kullanılır.
   ═══════════════════════════════════════════════════════════════════ */

let _c = 0;

// Her ikon: gradyan renk çifti + beyaz sembol (48×48 viewBox, ~24,24 merkez).
const SYMBOLS = {
  dashboard: { grad: ['#FFB066', '#FF6B6B'], svg:
    `<g fill="#fff"><rect x="14" y="14" width="8.5" height="8.5" rx="2.2"/><rect x="25.5" y="14" width="8.5" height="8.5" rx="2.2"/><rect x="14" y="25.5" width="8.5" height="8.5" rx="2.2"/><rect x="25.5" y="25.5" width="8.5" height="8.5" rx="2.2"/></g>` },

  weather: { grad: ['#7BC6FF', '#36D6C3'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><circle cx="29" cy="16.5" r="4.3" fill="#fff" stroke="none"/><line x1="29" y1="8" x2="29" y2="10"/><line x1="36.5" y1="16.5" x2="34.5" y2="16.5"/><line x1="34.5" y1="11" x2="33" y2="12.5"/></g><path fill="#fff" d="M16.5 33c-3 0-5.5-2.4-5.5-5.4 0-2.9 2.3-5.3 5.2-5.4.8-2.7 3.3-4.7 6.3-4.7 3.4 0 6.2 2.6 6.6 5.9 2.4.2 4.2 2.1 4.2 4.5 0 2.5-2 4.5-4.6 4.5H16.5z"/>` },

  planning: { grad: ['#FFC24B', '#FF8A3C'], svg:
    `<g fill="#fff"><rect x="18" y="12.5" width="2.4" height="5" rx="1.2"/><rect x="27.6" y="12.5" width="2.4" height="5" rx="1.2"/></g><g fill="none" stroke="#fff" stroke-width="2.3"><rect x="13.5" y="16.5" width="21" height="18" rx="3.5"/></g><g fill="#fff"><rect x="13.5" y="16.5" width="21" height="5.5" rx="2.5"/><circle cx="19" cy="27" r="1.5"/><circle cx="24" cy="27" r="1.5"/><circle cx="29" cy="27" r="1.5"/><circle cx="19" cy="31.5" r="1.5"/><circle cx="24" cy="31.5" r="1.5"/></g>` },

  passport: { grad: ['#36D6C3', '#2E8E84'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.2"><rect x="12.5" y="15.5" width="23" height="17" rx="3"/></g><g fill="#fff"><rect x="16" y="19" width="7" height="8" rx="1.6"/><rect x="26" y="20" width="6.5" height="2" rx="1"/><rect x="26" y="24" width="6.5" height="2" rx="1"/><rect x="16" y="29.4" width="16" height="1.8" rx="0.9"/></g>` },

  manifest: { grad: ['#F074C0', '#B493FF'], svg:
    `<path fill="#fff" d="M16 12.5h8.5l7.5 7.5v13.5c0 1.4-1.1 2.5-2.5 2.5H16c-1.4 0-2.5-1.1-2.5-2.5V15c0-1.4 1.1-2.5 2.5-2.5z"/><path fill="rgba(40,15,40,.22)" d="M24.5 12.5l7.5 7.5h-7.5z"/><g stroke="rgba(40,15,40,.32)" stroke-width="2" stroke-linecap="round"><line x1="18" y1="25" x2="30" y2="25"/><line x1="18" y1="29" x2="30" y2="29"/><line x1="18" y1="33" x2="26" y2="33"/></g>` },

  lists: { grad: ['#7BD88F', '#36D6C3'], svg:
    `<g fill="#fff"><circle cx="16" cy="18" r="2"/><circle cx="16" cy="24" r="2"/><circle cx="16" cy="30" r="2"/><rect x="21" y="16.8" width="14" height="2.4" rx="1.2"/><rect x="21" y="22.8" width="14" height="2.4" rx="1.2"/><rect x="21" y="28.8" width="14" height="2.4" rx="1.2"/></g>` },

  settings: { grad: ['#B493FF', '#7A6FB0'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><line x1="15" y1="18" x2="33" y2="18"/><line x1="15" y1="24" x2="33" y2="24"/><line x1="15" y1="30" x2="33" y2="30"/></g><g fill="#fff" stroke="#7A6FB0" stroke-width="1.2"><circle cx="21" cy="18" r="3"/><circle cx="29" cy="24" r="3"/><circle cx="19" cy="30" r="3"/></g>` },

  balloon: { grad: ['#FF6B6B', '#FF9F5A'], svg:
    `<path fill="#fff" d="M24 11c-6.1 0-10.5 4.6-10.5 10.4 0 5 3.6 9.2 7.7 11.1l.4 1.5h4.8l.4-1.5c4.1-1.9 7.7-6.1 7.7-11.1C34.5 15.6 30.1 11 24 11z"/><g stroke="rgba(120,40,20,.25)" stroke-width="1.5" fill="none"><path d="M24 11.5v21.5"/><path d="M19.3 12.6c-2.4 3.4-2.4 14.4 0 19.2"/><path d="M28.7 12.6c2.4 3.4 2.4 14.4 0 19.2"/></g><g stroke="#fff" stroke-width="1.1"><line x1="22.4" y1="33.2" x2="22.6" y2="35.4"/><line x1="25.6" y1="33.2" x2="25.4" y2="35.4"/></g><path fill="#fff" d="M22 35.3h4l-.6 3.1c-.1.4-.4.6-.8.6h-1.2c-.4 0-.7-.2-.8-.6z"/>` },

  wind: { grad: ['#8FD0FF', '#5BA8FF'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M13 20h12.5a3.1 3.1 0 1 0-3.1-3.1"/><path d="M13 26h16.5a3.3 3.3 0 1 1-3.3 3.3"/><path d="M13 32h8.5a2.7 2.7 0 1 1-2.7 2.7" opacity=".85"/></g>` },

  thermometer: { grad: ['#FF9F5A', '#FF6B6B'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.4"><path d="M27 14.5a3 3 0 0 0-6 0v11.4a5.2 5.2 0 1 0 6 0z"/></g><circle cx="24" cy="30.6" r="3.2" fill="#fff"/><rect x="23" y="18" width="2" height="9.4" rx="1" fill="#fff"/>` },

  visibility: { grad: ['#5BA8FF', '#7BD88F'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.4"><path d="M12 24c3.2-5.1 7.4-7.7 12-7.7S32.8 18.9 36 24c-3.2 5.1-7.4 7.7-12 7.7S15.2 29.1 12 24z"/></g><circle cx="24" cy="24" r="3.4" fill="#fff"/>` },

  cloud: { grad: ['#9FB6FF', '#5BA8FF'], svg:
    `<path fill="#fff" d="M17 30c-3.3 0-6-2.6-6-5.9 0-3.1 2.5-5.7 5.6-5.9.9-2.9 3.6-5 6.8-5 3.7 0 6.7 2.8 7.1 6.4 2.6.2 4.6 2.3 4.6 4.9 0 2.7-2.2 5-4.9 5H17z"/><g stroke="#fff" stroke-width="2.2" stroke-linecap="round"><line x1="19" y1="33" x2="18" y2="36"/><line x1="24" y1="33" x2="23" y2="36.5"/><line x1="29" y1="33" x2="28" y2="36"/></g>` },

  location: { grad: ['#F074C0', '#FF6B6B'], svg:
    `<path fill="#fff" d="M24 12c-4.4 0-8 3.5-8 7.9 0 5.6 8 16.1 8 16.1s8-10.5 8-16.1c0-4.4-3.6-7.9-8-7.9z"/><circle cx="24" cy="20" r="3" fill="rgba(120,30,60,.3)"/>` },

  refresh: { grad: ['#36D6C3', '#5BA8FF'], svg:
    `<g fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"><path d="M32.5 24a8.5 8.5 0 1 1-2.5-6"/></g><path fill="#fff" d="M33.6 13.6l.7 5.1-5.1-.9z"/>` },

  check: { grad: ['#7BD88F', '#36C39A'], svg:
    `<path fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" d="M15 24.5l6 6 12-12.5"/>` },

  alert: { grad: ['#FFC24B', '#FF6B6B'], svg:
    `<path fill="#fff" d="M24 13l11 19.5c.6 1-.1 2.3-1.3 2.3H14.3c-1.2 0-1.9-1.3-1.3-2.3L24 13z"/><g fill="rgba(120,50,10,.45)"><rect x="22.7" y="21" width="2.6" height="7" rx="1.3"/><circle cx="24" cy="31" r="1.5"/></g>` },
};

/** name → balon gradyan rengi (illüstrasyon/aksent için tek renk lazım olduğunda). */
export function iconColor(name) {
  return (SYMBOLS[name] || SYMBOLS.dashboard).grad[0];
}

/** 3D ikon SVG string'i döndürür. */
export function icon3d(name, size = 44) {
  const ic = SYMBOLS[name] || SYMBOLS.dashboard;
  const id = 'i3d' + (++_c);
  const [c1, c2] = ic.grad;
  return `<svg class="icon3d shadow" width="${size}" height="${size}" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs><linearGradient id="${id}" x1="10" y1="6" x2="40" y2="44" gradientUnits="userSpaceOnUse">
      <stop stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs>
    <rect x="5" y="5" width="38" height="38" rx="12" fill="url(#${id})"/>
    <path d="M5 17c0-6.6 5.4-12 12-12h14c6.6 0 12 5.4 12 12 0 1.6-1.4 1.7-4 2.6C46 21 36 23 24 23S2 21 5 17z" fill="#fff" opacity=".16"/>
    <rect x="5.7" y="5.7" width="36.6" height="36.6" rx="11.3" fill="none" stroke="#fff" stroke-opacity=".28" stroke-width="1.1"/>
    ${ic.svg}
  </svg>`;
}

export default icon3d;
