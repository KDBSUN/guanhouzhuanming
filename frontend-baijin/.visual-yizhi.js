await page.emulateMedia({ reducedMotion: 'no-preference' });
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto('http://[::1]:3001/#/home', { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.topnav-group button[aria-haspopup]');
const out = {};

// 闭合状态下 ArrowDown：应打开菜单并把焦点移到第一项
await page.locator('.topnav-group button[aria-haspopup]').first().focus();
await page.keyboard.press('ArrowDown');
await page.waitForTimeout(120);
out.closedArrowDown = await page.evaluate(() => ({
  expanded: document.querySelector('.topnav-group button[aria-haspopup]')?.getAttribute('aria-expanded'),
  focusRole: document.activeElement?.getAttribute('role'),
  focusText: document.activeElement?.textContent?.trim().slice(0, 20),
}));
// 菜单内继续 ArrowDown：循环到下一条
await page.keyboard.press('ArrowDown');
out.secondArrow = await page.evaluate(() => document.activeElement?.textContent?.trim().slice(0, 20));
// ArrowUp 回到上一项
await page.keyboard.press('ArrowUp');
out.arrowUp = await page.evaluate(() => document.activeElement?.textContent?.trim().slice(0, 20));
// Escape 关闭并还焦到按钮
await page.keyboard.press('Escape');
out.escape = await page.evaluate(() => ({
  menuGone: !document.querySelector('[role="menu"]'),
  focusBackToOpener: !!document.activeElement?.hasAttribute('aria-haspopup'),
}));
return out;
