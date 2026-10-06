import {assertNoHorizontalOverflow, expect, test} from './fixtures.js'

test('mantiene la navegación por teclado en motores alternativos', async ({cleanPage, identity}, testInfo) => {
  await cleanPage.goto('/cuaderno/precios')
  await expect(cleanPage.getByText('Formatos y precios', {exact: true}).first()).toBeVisible()
  await expect(cleanPage.locator('main')).toHaveCount(1)

  const format = cleanPage.getByLabel('Formato', {exact: true})
  await expect(format).toBeEnabled()
  await format.focus()
  await expect(format).toBeFocused()
  await cleanPage.keyboard.press('Tab')
  await expect(cleanPage.getByLabel('Contenido', {exact: true})).toBeFocused()

  await assertNoHorizontalOverflow(cleanPage, testInfo)
  expect(identity.browser).not.toBe('chromium')
})

test('aplica la hoja de impresión sin navegación ni desbordamiento', async ({cleanPage}, testInfo) => {
  await cleanPage.goto('/cuaderno/precios')
  await expect(cleanPage.getByText('Formatos y precios', {exact: true}).first()).toBeVisible()
  await cleanPage.emulateMedia({media: 'print'})

  await expect(cleanPage.locator('.v-navigation-drawer')).toBeHidden()
  await expect(cleanPage.locator('.v-bottom-navigation')).toBeHidden()
  await assertNoHorizontalOverflow(cleanPage, testInfo)
})
