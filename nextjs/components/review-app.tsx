// @ts-nocheck
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import HierarchyTree from './hierarchy-tree';
import ImageList from './image-list';
import QuestionPanel from './question-panel';
import VisualsPanel, { TreeVisualsPanel } from './visuals-panel';
import LanguageToggle, { useLanguagePreference } from './language-toggle';
import {
  applyAnswerChange,
  firstReviewableNodeId,
  missingReport,
  translatedLabel,
} from '../lib/review-logic';
import { normalizeTranslationJson } from '../lib/translation';
import { dateLocaleFor, uiText } from '../lib/i18n';

export default function ReviewApp({ reviewerId, records, initialAnnotations, initialSelection }) {
  const [language, setLanguage] = useLanguagePreference();
  const [annotations, setAnnotations] = useState(initialAnnotations || {});
  const [selectedImageId, setSelectedImageId] = useState(initialSelection?.imageId || Object.keys(records || {})[0] || null);
  const [selectedMode, setSelectedMode] = useState(initialSelection?.mode || 'node');
  const [selectedNodeId, setSelectedNodeId] = useState(initialSelection?.nodeId || null);
  const [translationMap, setTranslationMap] = useState({});
  const [saveStatus, setSaveStatus] = useState({ status: 'idle', savedAt: null, message: '' });

  const annotationsRef = useRef(annotations);
  const dirtyRef = useRef(false);
  const savingRef = useRef(false);

  useEffect(() => {
    annotationsRef.current = annotations;
  }, [annotations]);

  useEffect(() => {
    let cancelled = false;

    fetch(`/translation/full_translation.json?v=${Date.now()}`, {
      cache: 'no-store',
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((payload) => {
        if (!cancelled && payload) {
          const parsed = normalizeTranslationJson(payload);
          setTranslationMap(parsed);
        }
      })
      .catch((error) => {
        console.error('translation load failed:', error);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const imageIds = Object.keys(records || {});
  const selectedRecord = selectedImageId ? records[selectedImageId] : null;

  useEffect(() => {
    if (!imageIds.length) return;
    if (!selectedImageId || !records[selectedImageId]) {
      const nextImageId = imageIds[0];
      setSelectedImageId(nextImageId);
      setSelectedMode('node');
      setSelectedNodeId(firstReviewableNodeId(records[nextImageId]));
    }
  }, [imageIds, records, selectedImageId]);

  useEffect(() => {
    if (!selectedRecord) return;
    if (selectedMode === 'tree') {
      setSelectedNodeId(null);
      return;
    }

    if (!selectedNodeId || !selectedRecord.nodes?.[selectedNodeId]) {
      setSelectedNodeId(firstReviewableNodeId(selectedRecord));
    }
  }, [selectedImageId, selectedMode, selectedNodeId, selectedRecord]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (selectedImageId) params.set('image', selectedImageId);
    if (selectedMode) params.set('mode', selectedMode);
    if (selectedMode === 'node' && selectedNodeId) params.set('node', selectedNodeId);
    else params.delete('node');
    window.history.replaceState(null, '', `/?${params.toString()}`);
  }, [selectedImageId, selectedMode, selectedNodeId]);

  const saveNow = useCallback(async (force = false) => {
    if (savingRef.current) return false;
    if (!force && !dirtyRef.current) return true;

    savingRef.current = true;
    if (!force) {
      setSaveStatus((prev) => ({ ...prev, status: 'saving', message: '' }));
    }

    try {
      const response = await fetch('/api/review/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ annotations: annotationsRef.current }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error || uiText(language, 'app.saveFailed'));
      }

      dirtyRef.current = false;
      setSaveStatus({
        status: 'saved',
        savedAt: payload?.savedAt || new Date().toISOString(),
        message: '',
      });
      return true;
    } catch (error) {
      setSaveStatus({
        status: 'error',
        savedAt: null,
        message: error instanceof Error ? error.message : uiText(language, 'app.saveFailed'),
      });
      return false;
    } finally {
      savingRef.current = false;
    }
  }, [language]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (dirtyRef.current) {
        void saveNow(false);
      }
    }, 15000);

    return () => window.clearInterval(interval);
  }, [saveNow]);

  useEffect(() => {
    const onBeforeUnload = () => {
      if (!dirtyRef.current) return;
      const blob = new Blob([JSON.stringify({ annotations: annotationsRef.current })], {
        type: 'application/json',
      });
      navigator.sendBeacon('/api/review/save', blob);
    };

    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, []);

  const handleAnswerChange = useCallback((mode, questionId, value, nodeId = null) => {
    if (!selectedImageId) return;
    setAnnotations((prev) => {
      const next = applyAnswerChange(prev, selectedImageId, mode, questionId, value, nodeId);
      annotationsRef.current = next;
      return next;
    });
    dirtyRef.current = true;
    setSaveStatus({ status: 'dirty', savedAt: null, message: '' });
  }, [selectedImageId]);

  const handleSelectImage = useCallback((imageId) => {
    const record = records[imageId];
    setSelectedImageId(imageId);
    setSelectedMode('node');
    setSelectedNodeId(firstReviewableNodeId(record));
  }, [records]);

  const handleSelectNode = useCallback((nodeId) => {
    setSelectedMode('node');
    setSelectedNodeId(nodeId);
  }, []);

  const handleSelectTreeSummary = useCallback(() => {
    setSelectedMode('tree');
    setSelectedNodeId(null);
  }, []);

  const handleLogout = useCallback(async () => {
    await saveNow(true);
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => null);
    window.location.href = '/login';
  }, [saveNow]);

  const selectedMissingReport = useMemo(() => {
    if (!selectedRecord || !selectedImageId) return null;
    return missingReport(annotations, selectedImageId, selectedRecord);
  }, [annotations, selectedImageId, selectedRecord]);

  const saveStatusMessage = saveStatus.status === 'error' && saveStatus.message
    ? saveStatus.message
    : uiText(language, `saveStatus.${saveStatus.status || 'idle'}`);

  if (!imageIds.length) {
    return (
      <main className="appShell">
        <header className="topBar">
          <div>
            <div className="topBarTitle">{process.env.NEXT_PUBLIC_APP_TITLE || 'H-SAM Review Tool'}</div>
            <div className="topBarMeta">{uiText(language, 'app.reviewerId')}: {reviewerId}</div>
          </div>
          <div className="topBarActions">
            <LanguageToggle language={language} onLanguageChange={setLanguage} />
            <button className="secondaryButton" onClick={handleLogout}>{uiText(language, 'app.logout')}</button>
          </div>
        </header>

        <div className="emptyStateCard">
          <h1>{uiText(language, 'app.noAssignedTitle')}</h1>
          <p>{uiText(language, 'app.noAssignedBody', { reviewerId })}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <div className="topBarTitle">{process.env.NEXT_PUBLIC_APP_TITLE || 'H-SAM Review Tool'}</div>
          <div className="topBarMeta">{uiText(language, 'app.reviewerId')}: {reviewerId}</div>
        </div>

        <div className="topBarActions">
          <LanguageToggle language={language} onLanguageChange={setLanguage} />
          <div className={`saveBadge is-${saveStatus.status}`}>
            {saveStatusMessage}
            {saveStatus.savedAt ? ` · ${new Date(saveStatus.savedAt).toLocaleString(dateLocaleFor(language))}` : ''}
          </div>
          <button className="secondaryButton" onClick={() => saveNow(true)}>{uiText(language, 'app.saveToCloud')}</button>
          <button className="secondaryButton" onClick={handleLogout}>{uiText(language, 'app.logout')}</button>
        </div>
      </header>

      <div className="mainGrid">
        <ImageList
          records={records}
          annotations={annotations}
          selectedImageId={selectedImageId}
          onSelectImage={handleSelectImage}
          language={language}
        />

        <section className="contentColumn">
          {selectedRecord ? (
            <>

              <HierarchyTree
                record={selectedRecord}
                annotations={annotations}
                selectedMode={selectedMode}
                selectedNodeId={selectedNodeId}
                onSelectNode={handleSelectNode}
                onSelectTreeSummary={handleSelectTreeSummary}
                translationMap={translationMap}
                language={language}
              />

              {selectedMode === 'node' && selectedNodeId ? (
                <>
                  <VisualsPanel
                    key={`${selectedImageId}:${selectedNodeId}`}
                    record={selectedRecord}
                    nodeId={selectedNodeId}
                    translationMap={translationMap}
                    language={language}
                  />
                  <QuestionPanel
                    record={selectedRecord}
                    annotations={annotations}
                    imageId={selectedImageId}
                    mode="node"
                    nodeId={selectedNodeId}
                    onAnswerChange={handleAnswerChange}
                    translationMap={translationMap}
                    language={language}
                  />
                </>
              ) : (
                <>
                  <TreeVisualsPanel
                    key={`${selectedImageId}:tree`}
                    record={selectedRecord}
                    language={language}
                  />
                  <QuestionPanel
                    record={selectedRecord}
                    annotations={annotations}
                    imageId={selectedImageId}
                    mode="tree"
                    nodeId={null}
                    onAnswerChange={handleAnswerChange}
                    translationMap={translationMap}
                    language={language}
                  />
                </>
              )}

              {selectedMissingReport &&
              (selectedMissingReport.missing_nodes.length || selectedMissingReport.tree_missing.length) ? (
                <section className="sectionCard">
                  <h2 className="sectionTitle">{uiText(language, 'app.missingItems')}</h2>
                  <div className="pillCloud">
                    {selectedMissingReport.missing_nodes.map((item) => (
                      <span className="finalizePill" key={item.node_id}>
                        {translatedLabel(selectedImageId, item.node_id, translationMap, language)}
                      </span>
                    ))}
                    {selectedMissingReport.tree_missing.length ? (
                      <span className="finalizePill">{uiText(language, 'app.fullTree')}</span>
                    ) : null}
                  </div>
                </section>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}
