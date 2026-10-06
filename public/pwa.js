(() => {
  let installPrompt, registration, updating = false;
  const isStandalone = () => matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIOS = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const buttons = () => document.querySelectorAll('[data-install-app]');
  function refreshInstallButtons() {
    buttons().forEach(button => { button.hidden = isStandalone(); });
  }
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    refreshInstallButtons();
  });
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    buttons().forEach(button => { button.hidden = true; });
    toast('Roomly đã được cài lên điện thoại');
  });
  document.addEventListener('click', async event => {
    if (!event.target.closest('[data-install-app]')) return;
    if (installPrompt) {
      const prompt = installPrompt;
      installPrompt = null;
      await prompt.prompt();
      await prompt.userChoice;
      return;
    }
    const text = document.querySelector('#install-instructions');
    text.textContent = isIOS()
      ? 'Mở Roomly bằng Safari. Chạm Chia sẻ, chọn Thêm vào Màn hình chính, rồi chọn Thêm. Nếu đang mở trong Zalo hoặc Facebook, hãy chuyển sang Safari trước.'
      : 'Mở Roomly bằng Chrome trên Android. Trong menu ⋮, chọn Cài đặt ứng dụng hoặc Thêm vào màn hình chính. Ứng dụng cần chạy trên địa chỉ HTTPS. Trên máy tính, dùng nút cài đặt trong thanh địa chỉ nếu có.';
    document.querySelector('#install-dialog').showModal();
  });
  document.querySelector('#install-close').onclick = () => document.querySelector('#install-dialog').close();
  document.querySelector('#app-update').onclick = () => {
    if (registration?.waiting) {
      updating = true;
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
  };
  function updateAvailable() { document.querySelector('#update-banner').hidden = false; }
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('/sw.js').then(result => {
      registration = result;
      if (result.waiting) updateAvailable();
      result.addEventListener('updatefound', () => {
        const worker = result.installing;
        worker?.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) updateAvailable();
        });
      });
    }).catch(() => { /* The online app remains usable if installation is unavailable. */ });
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (updating) location.reload();
    });
  }
  function connectionChanged() { document.querySelector('#connection-status').hidden = navigator.onLine; }
  window.addEventListener('online', connectionChanged);
  window.addEventListener('offline', connectionChanged);
  document.addEventListener('submit', event => {
    if (!navigator.onLine) {
      event.preventDefault();
      event.stopImmediatePropagation();
      toast('Đang mất mạng. Kết nối lại rồi lưu thông tin.');
    }
  }, true);
  refreshInstallButtons();
  matchMedia('(display-mode: standalone)').addEventListener('change', refreshInstallButtons);
  connectionChanged();
})();
