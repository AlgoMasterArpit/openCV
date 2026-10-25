const ua = navigator.userAgent;

/** WhatsApp and other Android in-app browsers run in a WebView where the camera often fails. */
export function inAppBrowser() {
  return /WhatsApp/i.test(ua) || (/Android/i.test(ua) && /; wv\)/.test(ua));
}

export function chromeIntentUrl() {
  const target = `${location.host}${location.pathname}`;
  const fallback = encodeURIComponent(location.href);
  return `intent://${target}#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=${fallback};end`;
}
