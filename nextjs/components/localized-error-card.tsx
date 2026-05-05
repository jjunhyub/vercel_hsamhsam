// @ts-nocheck
'use client';

import LanguageToggle, { useLanguagePreference } from './language-toggle';
import { uiText } from '../lib/i18n';

export default function LocalizedErrorCard({ titleKey, message }) {
  const [language, setLanguage] = useLanguagePreference();

  return (
    <div className="errorPageCard">
      <div className="errorCardHeader">
        <h1>{uiText(language, titleKey)}</h1>
        <LanguageToggle language={language} onLanguageChange={setLanguage} />
      </div>
      <p>{message}</p>
    </div>
  );
}
