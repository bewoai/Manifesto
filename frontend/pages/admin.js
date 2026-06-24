import { api, toast, renderHeader } from '/app.js';

export async function render(container) {
  renderHeader('Yönetim', 'Kullanıcılar, audit, yedekler ve güncellemeler');
  container.innerHTML = `
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">manage_accounts</span> Kullanıcılar</div><button class="btn-primary" onclick="window.__showNewUser()">Yeni Kullanıcı</button></div>
        <div id="admin-users"></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">backup</span> Excel Yedekleri</div></div>
        <div id="admin-backups" class="max-h-80 overflow-auto"></div>
      </div>
      <div class="card xl:col-span-2">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">history</span> İşlem Geçmişi</div></div>
        <div id="admin-audit" class="overflow-auto"></div>
      </div>
      <div class="card xl:col-span-2">
        <div class="card-header"><div class="card-title"><span class="material-symbols-outlined">system_update</span> Güncelleme</div><button class="btn-secondary" onclick="window.__checkUpdate()">Kontrol Et</button></div>
        <div id="admin-update"></div>
      </div>
    </div>
    <dialog id="new-user-dialog" class="modal bg-transparent">
      <div class="glass-panel rounded-2xl p-6 w-[420px] max-w-[90vw]">
        <h3 class="font-headline text-xl mb-4">Yeni Kullanıcı</h3>
        <div class="form-group"><label class="form-label">Kullanıcı adı</label><input id="nu-user" class="form-input" /></div>
        <div class="form-group"><label class="form-label">Ad soyad</label><input id="nu-name" class="form-input" /></div>
        <div class="form-group"><label class="form-label">Parola</label><input id="nu-pass" type="password" class="form-input" /></div>
        <div class="form-group"><label class="form-label">Rol</label><select id="nu-role" class="form-select"><option value="operator">Operatör</option><option value="admin">Yönetici</option></select></div>
        <div class="flex justify-end gap-3 mt-5"><button class="btn-secondary" onclick="document.getElementById('new-user-dialog').close()">İptal</button><button class="btn-primary" onclick="window.__createUser()">Oluştur</button></div>
      </div>
    </dialog>`;
  await Promise.all([loadUsers(), loadBackups(), loadAudit(), loadUpdate()]);
}

async function loadUsers() {
  const data = await api.get('/api/admin/users');
  document.getElementById('admin-users').innerHTML = (data.users || []).map(user => `
    <div class="flex items-center justify-between border-b border-white/5 py-3">
      <div><strong class="text-on-surface">${esc(user.display_name)}</strong><div class="text-xs text-on-surface-variant">${esc(user.username)}</div></div>
      <span class="badge ${user.role === 'admin' ? 'badge-amber' : 'badge-blue'}">${user.role === 'admin' ? 'Yönetici' : 'Operatör'}</span>
    </div>`).join('');
}

async function loadBackups() {
  const data = await api.get('/api/admin/backups');
  document.getElementById('admin-backups').innerHTML = (data.backups || []).slice(0, 50).map(item => `
    <div class="flex items-center justify-between gap-3 border-b border-white/5 py-3">
      <div class="min-w-0"><strong class="block truncate text-sm">${esc(item.name)}</strong><span class="text-xs text-on-surface-variant">${new Date(item.created_at).toLocaleString('tr-TR')}</span></div>
      <button class="btn-ghost px-3" onclick="window.__restoreBackup('${escAttr(item.name)}')">Geri Yükle</button>
    </div>`).join('') || '<div class="empty-desc">Henüz yedek yok.</div>';
}

async function loadAudit() {
  const data = await api.get('/api/admin/audit?limit=200');
  document.getElementById('admin-audit').innerHTML = `
    <table class="w-full text-sm"><thead><tr><th class="p-2 text-left">Zaman</th><th class="p-2 text-left">Kullanıcı</th><th class="p-2 text-left">İşlem</th><th class="p-2 text-left">Gün</th></tr></thead>
    <tbody>${(data.entries || []).map(row => `<tr class="border-t border-white/5"><td class="p-2">${new Date(`${row.ts}Z`).toLocaleString('tr-TR')}</td><td class="p-2">${esc(row.actor)}</td><td class="p-2">${esc(row.action)}</td><td class="p-2">${esc(row.sheet || '—')}</td></tr>`).join('')}</tbody></table>`;
}

async function loadUpdate() {
  const data = await api.get('/api/update/status');
  const root = document.getElementById('admin-update');
  if (!data.configured) {
    root.innerHTML = '<div class="text-on-surface-variant">Güncelleme deposu Ayarlar bölümünde henüz yapılandırılmamış.</div>';
  } else if (data.available) {
    root.innerHTML = `<div class="flex items-center justify-between"><div><strong>Yeni sürüm ${esc(data.latest_version)}</strong><p class="text-sm text-on-surface-variant">${esc(data.release_notes || '')}</p></div><button class="btn-primary" onclick="window.__downloadUpdate()">İndir ve Doğrula</button></div>`;
  } else {
    root.innerHTML = `<div class="text-success">İrtifa güncel. Sürüm ${esc(data.current_version)}</div>`;
  }
}

window.__showNewUser = () => document.getElementById('new-user-dialog').showModal();
window.__createUser = async function() {
  try {
    await api.post('/api/admin/users', {
      username: document.getElementById('nu-user').value.trim(),
      display_name: document.getElementById('nu-name').value.trim(),
      password: document.getElementById('nu-pass').value,
      role: document.getElementById('nu-role').value,
    });
    document.getElementById('new-user-dialog').close();
    toast.success('Kullanıcı oluşturuldu');
    loadUsers();
  } catch (err) { toast.error('Kullanıcı oluşturulamadı', err.message); }
};

window.__restoreBackup = async function(name) {
  if (!confirm(`${name} geri yüklensin mi? Mevcut dosyanın ayrıca güvenlik yedeği alınır.`)) return;
  try {
    await api.post('/api/admin/backups/restore', { name });
    toast.success('Yedek geri yüklendi');
    loadBackups();
  } catch (err) { toast.error('Geri yükleme başarısız', err.message); }
};
window.__checkUpdate = loadUpdate;
window.__downloadUpdate = async function() {
  try {
    const data = await api.post('/api/update/download', {});
    if (confirm(`${data.version} indirildi ve doğrulandı. İrtifa yeniden başlatılarak kurulsun mu?`)) {
      await api.post('/api/update/install', {});
    }
  } catch (err) { toast.error('Güncelleme başarısız', err.message); }
};

function esc(value) { return String(value || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escAttr(value) { return esc(value).replace(/'/g, '&#39;').replace(/"/g, '&quot;'); }
