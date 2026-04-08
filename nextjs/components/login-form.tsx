// @ts-nocheck
'use client';

import { useState } from 'react';

export default function LoginForm() {
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
        setError(payload?.error || '로그인에 실패했습니다.');
        setStatus('idle');
        return;
      }

      setStatus('redirecting');
      window.location.replace('/');
    } catch (err) {
      setError('로그인 요청 중 오류가 발생했습니다.');
      setStatus('idle');
    }
  }

  return (
    <form className={`loginCard ${pending ? 'isPending' : ''}`} onSubmit={onSubmit}>
      {/* <div className="loginBadge">Reviewer Access</div> */}
      <h1 className="loginTitle">Reviewer Login</h1>

      <label className="fieldLabel" htmlFor="reviewer-id">Reviewer ID</label>
      <input
        id="reviewer-id"
        className="textField"
        value={reviewerId}
        onChange={(event) => setReviewerId(event.target.value)}
        placeholder="아이디를 입력하세요."
        autoComplete="username"
        disabled={pending}
      />

      <label className="fieldLabel" htmlFor="reviewer-password">Password</label>
      <input
        id="reviewer-password"
        className="textField"
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        placeholder="비밀번호를 입력하세요."
        autoComplete="current-password"
        disabled={pending}
      />

      {error ? <div className="errorBox">{error}</div> : null}

      <button className="primaryButton" type="submit" disabled={pending}>
        {status === 'redirecting' ? '이동 중...' : pending ? '로그인 중...' : '로그인'}
      </button>

      {pending ? (
        <div className="loginStatusText">
          {status === 'redirecting' ? '로그인 확인 완료. 페이지로 이동하고 있습니다.' : '아이디와 비밀번호를 확인하고 있습니다.'}
        </div>
      ) : null}
    </form>
  );
}
