// @ts-nocheck
'use client';

import { useState } from 'react';
import LanguageToggle, { useLanguagePreference } from './language-toggle';
import { uiText } from '../lib/i18n';

export default function LoginForm() {
  const [language, setLanguage] = useLanguagePreference();
  const [reviewerId, setReviewerId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('idle');

  const pending = status !== 'idle';

  async function onSubmit(event) {
    event.preventDefault();
    if (pending) return;

    setStatus('submitting');
    setError('');

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewerId, password }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(payload?.code ? uiText(language, `login.error.${payload.code}`) : payload?.error || uiText(language, 'login.failed'));
        setStatus('idle');
        return;
      }

      setStatus('redirecting');
      window.location.replace('/');
    } catch (err) {
      setError(uiText(language, 'login.requestFailed'));
      setStatus('idle');
    }
  }

  return (
    <form className={`loginCard ${pending ? 'isPending' : ''}`} onSubmit={onSubmit}>
      <div className="loginCardHeader">
        <h1 className="loginTitle">{uiText(language, 'login.title')}</h1>
        <LanguageToggle language={language} onLanguageChange={setLanguage} />
      </div>

      <label className="fieldLabel" htmlFor="reviewer-id">{uiText(language, 'login.reviewerId')}</label>
      <input
        id="reviewer-id"
        className="textField"
        value={reviewerId}
        onChange={(event) => setReviewerId(event.target.value)}
        placeholder={uiText(language, 'login.reviewerPlaceholder')}
        autoComplete="username"
        disabled={pending}
      />

      <label className="fieldLabel" htmlFor="reviewer-password">{uiText(language, 'login.password')}</label>
      <input
        id="reviewer-password"
        className="textField"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        placeholder={uiText(language, 'login.passwordPlaceholder')}
        autoComplete="current-password"
        disabled={pending}
      />

      {error ? <div className="errorBox">{error}</div> : null}

      <button className="primaryButton" type="submit" disabled={pending}>
        {status === 'redirecting'
          ? uiText(language, 'login.redirecting')
          : pending
            ? uiText(language, 'login.submitting')
            : uiText(language, 'login.submit')}
      </button>

      {pending ? (
        <div className="loginStatusText">
          {status === 'redirecting' ? uiText(language, 'login.redirectMessage') : uiText(language, 'login.checking')}
        </div>
      ) : null}
    </form>
  );
}
