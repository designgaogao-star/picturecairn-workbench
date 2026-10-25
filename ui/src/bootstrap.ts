import './styles.css';

const desktop = (window as unknown as {
  galleryApp?: { sessionId?: string; loadPreferences?: () => Promise<Record<string, string> | null> };
}).galleryApp;

try {
  if (desktop?.sessionId && sessionStorage.getItem('gt.desktopSession') !== desktop.sessionId) {
    const saved = await desktop.loadPreferences?.();
    if (saved) {
      for (const key of Object.keys(localStorage)) if (key.startsWith('gt.')) localStorage.removeItem(key);
      for (const [key, value] of Object.entries(saved)) localStorage.setItem(key, value);
    }
    sessionStorage.setItem('gt.desktopSession', desktop.sessionId);
  }
  const theme = localStorage.getItem('gt.theme');
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
} catch (error) { console.warn('Unable to restore UI preferences:', error); }

// State modules read preferences on import, before the first app render.
await import('./main');
export {};
