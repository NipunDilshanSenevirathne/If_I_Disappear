import '@fontsource-variable/outfit';
import '@fontsource-variable/yaldevi';
import './styles/tokens.css';
import './styles/base.css';
import './styles/app.css';
import './styles/landing.css';
import './styles/print.css';
import './styles/tour.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { applyTheme } from './components/Shell';
import { I18nProvider } from './i18n';
import { registerServiceWorker } from './lib/offline';

applyTheme();
registerServiceWorker();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>,
);
