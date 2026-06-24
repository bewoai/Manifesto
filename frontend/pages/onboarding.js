import { api, toast, renderHeader } from '/app.js';

export async function render(container) {
  document.getElementById('sidebar').style.display = 'none';
  document.getElementById('page-header').style.display = 'none';
  
  container.innerHTML = `
    <div class="min-h-[85vh] flex items-center justify-center py-10">
      <div class="glass-panel rounded-3xl p-10 w-full max-w-3xl">
        
        <div class="flex items-center justify-between mb-8">
          <div class="flex items-center gap-4">
            <img src="/irtifa-logo.png" class="w-16 h-16 rounded-2xl" alt="İrtifa" />
            <div>
              <h1 class="font-headline text-3xl text-on-surface">İrtifa'ya Hoş Geldiniz</h1>
              <p class="text-on-surface-variant">Sistemi kullanmaya başlamadan önce temel operasyon ayarlarını yapalım.</p>
            </div>
          </div>
        </div>

        <div id="onboarding-step-1" class="space-y-6">
          <h2 class="font-headline text-xl text-primary">Adım 1: Firma ve Operasyon Tanımları</h2>
          
          <div class="form-group">
            <label class="form-label">Firmanızın Adı</label>
            <input type="text" id="ob-company" class="form-input" placeholder="Örn: Kapadokya Balloons" />
          </div>
          
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="form-group">
              <label class="form-label">Acenteleriniz</label>
              <textarea id="ob-agencies" class="form-input h-24" placeholder="Acente 1, Acente 2..."></textarea>
              <div class="form-help">Virgülle ayırın.</div>
            </div>
            <div class="form-group">
              <label class="form-label">Şoförleriniz</label>
              <textarea id="ob-drivers" class="form-input h-24" placeholder="Ahmet, Mehmet..."></textarea>
              <div class="form-help">Virgülle ayırın.</div>
            </div>
          </div>
          
          <div class="flex justify-end gap-3 mt-8">
            <button class="btn-ghost" onclick="window.__onboardingSkip(2)">Bu Adımı Atla</button>
            <button class="btn-primary" onclick="window.__onboardingNext(2)">İleri</button>
          </div>
        </div>

        <div id="onboarding-step-2" class="space-y-6 hidden">
          <h2 class="font-headline text-xl text-primary">Adım 2: Balon Kodları ve Kapasite</h2>
          
          <div class="form-group">
            <label class="form-label">Balon Kodlarınız</label>
            <input type="text" id="ob-balloons" class="form-input" placeholder="BYF, BTK, BYJ..." />
            <div class="form-help">Operasyonda uçan balonlarınızın kodlarını virgülle ayırarak girin.</div>
          </div>

          <div class="form-group">
            <label class="form-label">Standart Balon Kapasitesi</label>
            <input type="number" id="ob-capacity" class="form-input" value="28" />
          </div>
          
          <div class="flex justify-between mt-8">
            <button class="btn-ghost" onclick="window.__onboardingNext(1)">Geri</button>
            <div class="flex gap-3">
              <button class="btn-ghost" onclick="window.__onboardingSkip(3)">Bu Adımı Atla</button>
              <button class="btn-primary" onclick="window.__onboardingNext(3)">İleri</button>
            </div>
          </div>
        </div>

        <div id="onboarding-step-3" class="space-y-6 hidden">
          <h2 class="font-headline text-xl text-primary">Adım 3: Uçuş Planı Excel'inin Kurulumu</h2>
          <p class="text-on-surface-variant">Rezervasyonların yazılacağı ana master dosyayı oluşturun. Bu dosya masaüstünüzde (veya dilediğiniz yerde) duracak ve İrtifa rezervasyonları oraya kaydedecektir.</p>
          
          <div class="py-12 flex flex-col items-center gap-4">
            <button class="btn-primary shadow-lg scale-125" onclick="window.__createFirstPlan()">
              <span class="material-symbols-outlined text-2xl">post_add</span> İlk Uçuş Planı Excel'ini Oluştur
            </button>
            <div class="text-on-surface-variant my-2">veya</div>
            <button class="btn-ghost shadow" onclick="window.__importExistingPlan()">
              <span class="material-symbols-outlined text-xl">upload_file</span> Mevcut Excel Dosyasını Bağla
            </button>
          </div>
          
          <div class="flex justify-between mt-8">
            <button class="btn-ghost" onclick="window.__onboardingNext(2)">Geri</button>
            <div class="flex gap-3">
              <button id="btn-finish-ob" class="btn-primary hidden" onclick="window.__finishOnboarding()">Kurulumu Tamamla</button>
            </div>
          </div>
        </div>

      </div>
    </div>
  `;

  try {
    const s = await api.get('/api/settings');
    if (s.company_name) document.getElementById('ob-company').value = s.company_name;
    if (s.operation_options?.agency) document.getElementById('ob-agencies').value = s.operation_options.agency.join(', ');
    if (s.operation_options?.driver) document.getElementById('ob-drivers').value = s.operation_options.driver.join(', ');
    if (s.balloon_codes) document.getElementById('ob-balloons').value = s.balloon_codes.join(', ');
    if (s.balloon_capacity) document.getElementById('ob-capacity').value = s.balloon_capacity;
  } catch (e) {}
}

window.__onboardingNext = async function(step) {
  const { toast } = await import('/app.js');
  // Validation for step 1 to 2
  if (step === 2) {
    if (!document.getElementById('ob-company').value.trim() || 
        !document.getElementById('ob-agencies').value.trim() || 
        !document.getElementById('ob-drivers').value.trim()) {
      toast.error('Eksik Bilgi', 'Lütfen tüm alanları doldurun veya "Bu Adımı Atla" diyerek geçin.');
      return;
    }
  }
  // Validation for step 2 to 3
  if (step === 3) {
    if (!document.getElementById('ob-balloons').value.trim() || 
        !document.getElementById('ob-capacity').value.trim()) {
      toast.error('Eksik Bilgi', 'Lütfen balon bilgilerini doldurun veya "Bu Adımı Atla" diyerek geçin.');
      return;
    }
  }
  
  document.getElementById('onboarding-step-1').classList.add('hidden');
  document.getElementById('onboarding-step-2').classList.add('hidden');
  document.getElementById('onboarding-step-3').classList.add('hidden');
  document.getElementById('onboarding-step-' + step).classList.remove('hidden');
};

window.__onboardingSkip = function(step) {
  document.getElementById('onboarding-step-1').classList.add('hidden');
  document.getElementById('onboarding-step-2').classList.add('hidden');
  document.getElementById('onboarding-step-3').classList.add('hidden');
  document.getElementById('onboarding-step-' + step).classList.remove('hidden');
};

window.__createFirstPlan = async function() {
  const { modal } = await import('/app.js');
  const now = new Date();
  modal.open('İlk Uçuş Planını Oluştur', `
    <div class="space-y-4">
      <div class="form-group">
        <label class="form-label">Yıl</label>
        <select id="modal-plan-year" class="form-select">
          <option value="${now.getFullYear()}">${now.getFullYear()}</option>
          <option value="${now.getFullYear() + 1}">${now.getFullYear() + 1}</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Ay</label>
        <select id="modal-plan-month" class="form-select">
          ${[...Array(12)].map((_, i) => {
            const val = i + 1;
            const name = new Date(2000, i, 1).toLocaleString('tr-TR', { month: 'long' });
            return '<option value="' + val + '" ' + (now.getMonth() + 1 === val ? 'selected' : '') + '>' + name + '</option>';
          }).join('')}
        </select>
      </div>
    </div>
  `, `
    <button class="btn-ghost" onclick="window.__closeModal()">İptal</button>
    <button class="btn-primary" onclick="window.__doCreateFirstPlan()">Oluştur ve Kaydet</button>
  `);
};

window.__doCreateFirstPlan = async function() {
  const { toast } = await import('/app.js');
  const y = parseInt(document.getElementById('modal-plan-year').value);
  const m = parseInt(document.getElementById('modal-plan-month').value);
  window.__closeModal();
  try {
    const res = await api.post('/api/planning/generate-monthly', { year: y, month: m });
    if (res.success) {
      toast.success('Başarılı', res.message);
      document.querySelector('#onboarding-step-3 .btn-primary.shadow-lg').classList.add('bg-success');
      document.querySelector('#onboarding-step-3 .btn-primary.shadow-lg').innerHTML = '<span class="material-symbols-outlined text-2xl">check_circle</span> Dosya Ayarlandı';
      document.getElementById('btn-finish-ob').classList.remove('hidden');
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

window.__importExistingPlan = async function() {
  const { toast } = await import('/app.js');
  try {
    const res = await api.post('/api/planning/import-existing', {});
    if (res.success) {
      toast.success('Başarılı', res.message);
      document.querySelector('#onboarding-step-3 .btn-primary.shadow-lg').classList.add('bg-success');
      document.querySelector('#onboarding-step-3 .btn-primary.shadow-lg').innerHTML = '<span class="material-symbols-outlined text-2xl">check_circle</span> Dosya Ayarlandı';
      document.getElementById('btn-finish-ob').classList.remove('hidden');
    } else {
      if (res.message !== 'İptal edildi') toast.error('Hata', res.message);
    }
  } catch (err) {
    toast.error('Hata', err.message);
  }
};

async function saveSettingsAndFinish(isComplete) {
  const { toast } = await import('/app.js');
  const payload = { is_setup_complete: isComplete };
  
  if (isComplete) {
    payload.company_name = document.getElementById('ob-company').value.trim();
    payload.balloon_codes = document.getElementById('ob-balloons').value.split(',').map(s => s.trim()).filter(Boolean);
    payload.balloon_capacity = parseInt(document.getElementById('ob-capacity').value) || 28;
    payload.operation_options = {
      agency: document.getElementById('ob-agencies').value.split(',').map(s => s.trim()).filter(Boolean),
      driver: document.getElementById('ob-drivers').value.split(',').map(s => s.trim()).filter(Boolean)
    };
  }

  try {
    await api.put('/api/settings', payload);
    document.getElementById('sidebar').style.display = '';
    document.getElementById('page-header').style.display = '';
    window.location.hash = '#/dashboard';
  } catch (err) {
    toast.error('Ayarlar kaydedilemedi', err.message);
  }
}

window.__finishOnboarding = () => saveSettingsAndFinish(true);
window.__skipOnboarding = () => saveSettingsAndFinish(true);
