async function go(page, name) {
  if (page.viewportSize().width > 650) {
    await page.locator(`[data-page="${name}"]`).click();
    return;
  }
  const tab = page.locator(`#mobile-nav [data-mobile-page="${name}"]`);
  if (await tab.count()) {
    await tab.click();
    return;
  }
  await page.locator('#mobile-menu-open').click();
  await page.locator(`#mobile-menu [data-mobile-page="${name}"]`).click();
}
module.exports = { go };
