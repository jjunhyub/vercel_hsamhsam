// @ts-nocheck
'use client';

import { useCallback, useEffect, useState } from 'react';
import { LANGUAGE_STORAGE_KEY, normalizeLanguage, uiText } from '../lib/i18n';

export function useLanguagePreference() {
  const [language, setLanguageState] = useState('ko');

  useEffect(() => {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    const nextLanguage = normalizeLanguage(stored || 'ko');
    setLanguageState(nextLanguage);
    document.documentElement.lang = nextLanguage;
  }, []);

  const setLanguage = useCallback((nextValue) => {
    const nextLanguage = normalizeLanguage(nextValue);
    setLanguageState(nextLanguage);
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, nextLanguage);
    document.documentElement.lang = nextLanguage;
  }, []);

  return [language, setLanguage];
}

export default function LanguageToggle({ language, onLanguageChange, className = '' }) {
  const enabled = language === 'en';
  const nextLanguage = enabled ? 'ko' : 'en';

  return (
    <button
      type="button"
      className={`languageToggle ${enabled ? 'isOn' : ''} ${className}`.trim()}
      aria-pressed={enabled}
      aria-label={uiText(language, 'languageToggle.aria')}
      onClick={() => onLanguageChange(nextLanguage)}
    >
      <span className="languageToggleLabel">{uiText(language, 'languageToggle.label')}</span>
      <span className="languageToggleState">
        {uiText(language, enabled ? 'languageToggle.on' : 'languageToggle.off')}
      </span>
    </button>
  );
}
