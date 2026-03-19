/**
 * Crypto polyfill for renderer process
 * 
 * Electron 渲染进程中的 crypto 替代实现
 */

export const getRandomValues = (array: Uint8Array): Uint8Array => {
  // 使用浏览器的 crypto API
  if (typeof window !== 'undefined' && window.crypto && window.crypto.getRandomValues) {
    return window.crypto.getRandomValues(array)
  }
  
  // 降级方案：使用 Math.random()
  for (let i = 0; i < array.length; i++) {
    array[i] = Math.floor(Math.random() * 256)
  }
  return array
}

export default {
  getRandomValues
}
