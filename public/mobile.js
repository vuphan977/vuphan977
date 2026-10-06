(() => {
  const paths = {
    home: '<path d="m3 10 9-7 9 7v10H3z"/><path d="M9 20v-7h6v7"/>',
    rooms: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h2m4 0h2M8 11h2m4 0h2M10 21v-6h4v6"/>',
    invoice: '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6m-6 4h6"/>',
    repair: '<path d="M14 5a5 5 0 0 0-6 6L3 16l5 5 5-5a5 5 0 0 0 6-6l-4 3-4-4z"/>',
    bell: '<path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4"/>',
    account: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
  };
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths[name]}</svg>`;
  const menu = document.querySelector('#mobile-menu');
  function openMenu() { menu.showModal(); }
  document.querySelector('#mobile-menu-open').onclick = openMenu;
  document.querySelector('#mobile-menu-close').onclick = () => menu.close();
  document.querySelector('#mobile-logout').onclick = () => { menu.close(); document.querySelector('#logout').click(); };
  document.addEventListener('click', event => {
    if (event.target.closest('[data-mobile-more]')) openMenu();
  });
  window.addEventListener('roomly:render', event => {
    const { role, selected, unread } = event.detail;
    const items = role === 'tenant'
      ? [['Hóa đơn của tôi', 'Hóa đơn', 'invoice'], ['Thông báo', 'Thông báo', 'bell'], ['Báo hỏng', 'Báo hỏng', 'repair'], ['Tài khoản', 'Tài khoản', 'account']]
      : [['Dashboard', 'Tổng quan', 'home'], ['Phòng', 'Phòng', 'rooms'], ['Hóa đơn', 'Hóa đơn', 'invoice'], ['Báo hỏng', 'Báo hỏng', 'repair']];
    document.querySelector('#mobile-nav').innerHTML = items.map(([target, label, glyph]) => `<button data-mobile-page="${esc(target)}" class="${selected === target ? 'active' : ''}" ${selected === target ? 'aria-current="page"' : ''}>${icon(glyph)}<span>${label}</span>${target === 'Thông báo' && unread ? `<b class="unread-dot" aria-label="${unread} thông báo chưa đọc"></b>` : ''}</button>`).join('') + (role === 'owner' ? `<button data-mobile-more>${icon('more')}<span>Thêm</span></button>` : '');
    const pages = role === 'tenant' ? ['Hóa đơn của tôi', 'Thông báo', 'Báo hỏng', 'Tài khoản'] : names;
    document.querySelector('#mobile-menu-pages').innerHTML = pages.map(target => `<button data-mobile-page="${esc(target)}" class="${selected === target ? 'active' : ''}">${esc(target === 'Dashboard' ? 'Tổng quan' : target)}</button>`).join('');
    document.querySelector('#mobile-nav').hidden = false;
  });
  window.addEventListener('roomly:logout', () => {
    document.querySelector('#mobile-nav').hidden = true;
    document.querySelector('#mobile-nav').innerHTML = '';
    document.querySelector('#mobile-menu-pages').innerHTML = '';
    menu.close();
  });
  if (currentUser && state) mobileNavigation();
})();
