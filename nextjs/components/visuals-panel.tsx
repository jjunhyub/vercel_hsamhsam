// @ts-nocheck
'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { getInspectorPills, nodeAssets, translatedLabel, translatedPathLabels } from '../lib/review-logic';
import { uiText } from '../lib/i18n';

const EMPTY_DERIVED = {
  overlay: '',
  maskOriginalFull: '',
  mask: '',
};

function splitPillText(pill) {
  const text = String(pill || '');
  const separatorIndex = text.indexOf(':');
  if (separatorIndex < 0) {
    return { label: '', value: text };
  }

  return {
    label: text.slice(0, separatorIndex).trim(),
    value: text.slice(separatorIndex + 1).trim(),
  };
}

function buildAssetUrl(imageId, path) {
  if (!path) return '';
  const params = new URLSearchParams({ imageId: String(imageId), path: String(path) });
  return `/api/assets?${params.toString()}`;
}

function FigureCard({ title, children }) {
  return (
    <div className="figureCard">
      <div className="figureTitle">{title}</div>
      {children}
    </div>
  );
}

function AspectFrame({ width, height, children, dark = true, className = '' }) {
  const w = Math.max(1, Number(width || 1));
  const h = Math.max(1, Number(height || 1));
  return (
    <div
      className={`aspectFrame ${dark ? 'isDark' : ''} ${className}`.trim()}
      style={{ aspectRatio: `${w} / ${h}` }}
    >
      {children}
    </div>
  );
}

function FigureImageButton({ figure, onOpen, language }) {
  if (!figure.src) {
    return (
      <AspectFrame width={figure.fullSize?.[0]} height={figure.fullSize?.[1]}>
        <div className="framePlaceholder">
          <span className="framePlaceholderText">{uiText(language, 'visual.loading')}</span>
        </div>
      </AspectFrame>
    );
  }

  return (
    <button
      type="button"
      className="figureImageButton"
      onClick={onOpen}
      aria-label={uiText(language, 'modal.zoomAria', { title: figure.title })}
    >
      <AspectFrame width={figure.fullSize?.[0]} height={figure.fullSize?.[1]} className="isInteractive">
        <img className="frameImage" src={figure.src} alt={figure.title} loading="lazy" />
      </AspectFrame>
    </button>
  );
}

function ImageModal({ figures, activeIndex, onClose, onPrev, onNext, contextLabel, language }) {
  const activeFigure = figures[activeIndex];
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const frameRef = useRef(null);
  const dragRef = useRef(null);

  const clampPan = (nextPan, nextZoom = zoom) => {
    const frameEl = frameRef.current;
    if (!frameEl || nextZoom <= 1) return { x: 0, y: 0 };

    const maxX = (frameEl.clientWidth * 0.8 * (nextZoom - 1)) / 2;
    const maxY = (frameEl.clientHeight * 0.8 * (nextZoom - 1)) / 2;

    return {
      x: Math.min(maxX, Math.max(-maxX, nextPan.x)),
      y: Math.min(maxY, Math.max(-maxY, nextPan.y)),
    };
  };

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    dragRef.current = null;
    setIsDragging(false);
  }, [activeIndex, activeFigure?.src]);

  useEffect(() => {
    if (!activeFigure) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        onPrev();
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        onNext();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeFigure, onClose, onNext, onPrev]);

  if (!activeFigure) return null;

  const handleWheel = (event) => {
    event.preventDefault();
    const factor = Math.exp(-event.deltaY * 0.0028);
    setZoom((prev) => {
      const nextZoom = Math.min(4, Math.max(1, Number((prev * factor).toFixed(2))));
      setPan((currentPan) => clampPan(currentPan, nextZoom));
      return nextZoom;
    });
  };

  const handleDoubleClick = () => {
    setZoom((prev) => {
      const nextZoom = prev > 1 ? 1 : 2;
      setPan({ x: 0, y: 0 });
      return nextZoom;
    });
  };

  const handlePointerDown = (event) => {
    if (zoom <= 1) return;
    event.preventDefault();
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setIsDragging(true);
  };

  const handlePointerMove = (event) => {
    if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - dragRef.current.startX;
    const deltaY = event.clientY - dragRef.current.startY;
    setPan(
      clampPan({
        x: dragRef.current.originX + deltaX,
        y: dragRef.current.originY + deltaY,
      }),
    );
  };

  const endDrag = (event) => {
    if (dragRef.current && event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragRef.current = null;
    setIsDragging(false);
  };

  return (
    <div
      className="imageModalOverlay"
      role="dialog"
      aria-modal="true"
      aria-label={uiText(language, 'modal.zoomAria', { title: activeFigure.title })}
      onClick={onClose}
    >
      <div className="imageModalContent" onClick={(event) => event.stopPropagation()}>
        <button
          type="button"
          className="imageModalClose"
          onClick={onClose}
          aria-label={uiText(language, 'modal.closeAria')}
        >
          <span className="imageModalIcon">×</span>
        </button>

        {figures.length > 1 ? (
          <>
            <button
              type="button"
              className="imageModalNav imageModalNavLeft"
              onClick={onPrev}
              aria-label={uiText(language, 'modal.prevAria')}
            >
              <span className="imageModalIcon">‹</span>
            </button>
            <button
              type="button"
              className="imageModalNav imageModalNavRight"
              onClick={onNext}
              aria-label={uiText(language, 'modal.nextAria')}
            >
              <span className="imageModalIcon">›</span>
            </button>
          </>
        ) : null}

        <div className="imageModalMeta">
          <div className="imageModalTitle">{activeFigure.title}</div>
          <div className="imageModalContext">{`${uiText(language, 'modal.current')}: ${contextLabel}`}</div>
          <div className="imageModalCount">
            {activeIndex + 1} / {figures.length}
          </div>
        </div>

        <div
          ref={frameRef}
          className={`imageModalFrame ${zoom > 1 ? 'isZoomed' : ''} ${isDragging ? 'isDragging' : ''}`.trim()}
          onWheel={handleWheel}
          onDoubleClick={handleDoubleClick}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <img
            className="imageModalImage"
            src={activeFigure.src}
            alt={activeFigure.title}
            style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
          />
        </div>
      </div>
    </div>
  );
}

function useDerivedFigures(imageId, rootPath, coloredPath, fullSize, leaf, language) {
  const [rootImgEl, setRootImgEl] = useState(null);
  const [derived, setDerived] = useState(EMPTY_DERIVED);

  useEffect(() => {
    setRootImgEl(null);
    setDerived(EMPTY_DERIVED);
  }, [imageId, rootPath, coloredPath]);

  useEffect(() => {
    let cancelled = false;

    if (!imageId || !rootPath) {
      setRootImgEl(null);
      return undefined;
    }

    const rootUrl = buildAssetUrl(imageId, rootPath);
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      if (!cancelled) setRootImgEl(img);
    };
    img.onerror = () => {
      if (!cancelled) setRootImgEl(null);
    };
    img.src = rootUrl;

    return () => {
      cancelled = true;
    };
  }, [imageId, rootPath]);

  useEffect(() => {
    let cancelled = false;

    if (!imageId || !coloredPath || !rootImgEl) {
      setDerived(EMPTY_DERIVED);
      return undefined;
    }

    const coloredUrl = buildAssetUrl(imageId, coloredPath);

    async function buildDerived() {
      const loadImage = (src) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.crossOrigin = 'anonymous';
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = src;
        });

      try {
        const coloredImg = await loadImage(coloredUrl);

        const width = rootImgEl.naturalWidth || rootImgEl.width;
        const height = rootImgEl.naturalHeight || rootImgEl.height;

        const rootCanvas = document.createElement('canvas');
        rootCanvas.width = width;
        rootCanvas.height = height;
        const rootCtx = rootCanvas.getContext('2d');

        const coloredCanvas = document.createElement('canvas');
        coloredCanvas.width = width;
        coloredCanvas.height = height;
        const coloredCtx = coloredCanvas.getContext('2d');

        const overlayCanvas = document.createElement('canvas');
        overlayCanvas.width = width;
        overlayCanvas.height = height;
        const overlayCtx = overlayCanvas.getContext('2d');

        const maskOriginalCanvas = document.createElement('canvas');
        maskOriginalCanvas.width = width;
        maskOriginalCanvas.height = height;
        const maskOriginalCtx = maskOriginalCanvas.getContext('2d');

        const maskCanvas = document.createElement('canvas');
        maskCanvas.width = width;
        maskCanvas.height = height;
        const maskCtx = maskCanvas.getContext('2d');

        if (!rootCtx || !coloredCtx || !overlayCtx || !maskOriginalCtx || !maskCtx) return;

        rootCtx.drawImage(rootImgEl, 0, 0, width, height);
        coloredCtx.drawImage(coloredImg, 0, 0, width, height);

        const rootImageData = rootCtx.getImageData(0, 0, width, height);
        const coloredImageData = coloredCtx.getImageData(0, 0, width, height);

        const rootData = rootImageData.data;
        const coloredData = coloredImageData.data;

        const overlayImageData = overlayCtx.createImageData(width, height);
        const maskOriginalImageData = maskOriginalCtx.createImageData(width, height);
        const maskImageData = maskCtx.createImageData(width, height);

        const overlayData = overlayImageData.data;
        const maskOriginalData = maskOriginalImageData.data;
        const maskData = maskImageData.data;

        for (let i = 0; i < rootData.length; i += 4) {
          const r = coloredData[i];
          const g = coloredData[i + 1];
          const b = coloredData[i + 2];
          const a = coloredData[i + 3];

          const isFg = a > 0 && (r !== 0 || g !== 0 || b !== 0);

          const rr = rootData[i];
          const rg = rootData[i + 1];
          const rb = rootData[i + 2];
          const ra = rootData[i + 3];

          if (isFg) {
            overlayData[i] = Math.round(rr * 0.65 + 255 * 0.35);
            overlayData[i + 1] = Math.round(rg * 0.65);
            overlayData[i + 2] = Math.round(rb * 0.65);
            overlayData[i + 3] = ra;

            maskOriginalData[i] = rr;
            maskOriginalData[i + 1] = rg;
            maskOriginalData[i + 2] = rb;
            maskOriginalData[i + 3] = ra;

            maskData[i] = 255;
            maskData[i + 1] = 255;
            maskData[i + 2] = 255;
            maskData[i + 3] = 255;
          } else {
            overlayData[i] = rr;
            overlayData[i + 1] = rg;
            overlayData[i + 2] = rb;
            overlayData[i + 3] = ra;

            maskOriginalData[i] = 0;
            maskOriginalData[i + 1] = 0;
            maskOriginalData[i + 2] = 0;
            maskOriginalData[i + 3] = 255;

            maskData[i] = 0;
            maskData[i + 1] = 0;
            maskData[i + 2] = 0;
            maskData[i + 3] = 255;
          }
        }

        overlayCtx.putImageData(overlayImageData, 0, 0);
        maskOriginalCtx.putImageData(maskOriginalImageData, 0, 0);
        maskCtx.putImageData(maskImageData, 0, 0);

        if (!cancelled) {
          setDerived({
            overlay: overlayCanvas.toDataURL('image/png'),
            maskOriginalFull: maskOriginalCanvas.toDataURL('image/png'),
            mask: maskCanvas.toDataURL('image/png'),
          });
        }
      } catch (error) {
        console.error('Failed to build derived views:', error);
        if (!cancelled) {
          setDerived(EMPTY_DERIVED);
        }
      }
    }

    buildDerived();

    return () => {
      cancelled = true;
    };
  }, [imageId, coloredPath, rootImgEl]);

  return useMemo(
    () => [
      {
        key: `derived-overlay-${imageId}-${leaf}`,
        title: uiText(language, 'visual.overlay'),
        src: derived.overlay,
        fullSize,
      },
      {
        key: `derived-original-${imageId}-${leaf}`,
        title: uiText(language, 'visual.maskedOriginal'),
        src: derived.maskOriginalFull,
        fullSize,
      },
      {
        key: `derived-mask-${imageId}-${leaf}`,
        title: uiText(language, 'visual.mask'),
        src: derived.mask,
        fullSize,
      },
    ],
    [derived.mask, derived.maskOriginalFull, derived.overlay, fullSize, imageId, leaf, language]
  );
}

export function TreeVisualsPanel({ record, language }) {
  const [activeFigureIndex, setActiveFigureIndex] = useState(null);

  const figures = useMemo(() => {
    const imageId = record?.image_id;
    const fullSize = record?.full_size || null;
    const nextFigures = [];

    if (record?.root_image_path) {
      nextFigures.push({
        key: `tree-root-original-${imageId}`,
        title: uiText(language, 'visual.originalImage'),
        src: buildAssetUrl(imageId, record.root_image_path),
        fullSize,
      });
    }

    if (record?.others_others_path) {
      nextFigures.push({
        key: `tree-others-others-${imageId}`,
        title: uiText(language, 'visual.remainingArea'),
        src: buildAssetUrl(imageId, record.others_others_path),
        fullSize,
      });
    }

    if (record?.all_instances_overlay_path) {
      nextFigures.push({
        key: `tree-all-instances-overlay-${imageId}`,
        title: uiText(language, 'visual.fullOverlay'),
        src: buildAssetUrl(imageId, record.all_instances_overlay_path),
        fullSize,
      });
    }

    return nextFigures;
  }, [record, language]);

  const modalFigures = useMemo(
    () => figures.filter((figure) => Boolean(figure.src)),
    [figures]
  );

  useEffect(() => {
    if (activeFigureIndex === null) return;
    if (!modalFigures.length) {
      setActiveFigureIndex(null);
      return;
    }
    if (activeFigureIndex >= modalFigures.length) {
      setActiveFigureIndex(modalFigures.length - 1);
    }
  }, [activeFigureIndex, modalFigures]);

  const handleOpenFigure = (figure) => {
    const nextIndex = modalFigures.findIndex((item) => item.key === figure.key);
    if (nextIndex >= 0) {
      setActiveFigureIndex(nextIndex);
    }
  };

  const handleCloseModal = () => setActiveFigureIndex(null);

  const handlePrevFigure = () => {
    setActiveFigureIndex((prev) => {
      if (prev === null || !modalFigures.length) return prev;
      return (prev - 1 + modalFigures.length) % modalFigures.length;
    });
  };

  const handleNextFigure = () => {
    setActiveFigureIndex((prev) => {
      if (prev === null || !modalFigures.length) return prev;
      return (prev + 1) % modalFigures.length;
    });
  };

  return (
    <>
      <section className="sectionCard">
        <div className="sectionHeaderWithMeta">
          <div>
            <h2 className="sectionTitle">{uiText(language, 'visual.treeReview')}</h2>
          </div>
        </div>

        {figures.length ? (
          <div className="visualsGrid treeVisualsGrid">
            {figures.map((figure) => (
              <FigureCard key={figure.key} title={figure.title}>
                <FigureImageButton figure={figure} onOpen={() => handleOpenFigure(figure)} language={language} />
              </FigureCard>
            ))}
          </div>
        ) : (
          <div className="emptyBox">{uiText(language, 'visual.noTreeImages')}</div>
        )}
      </section>

      <ImageModal
        figures={modalFigures}
        activeIndex={activeFigureIndex}
        onClose={handleCloseModal}
        onPrev={handlePrevFigure}
        onNext={handleNextFigure}
        contextLabel={uiText(language, 'app.fullTree')}
        language={language}
      />
    </>
  );
}

export default function VisualsPanel({ record, nodeId, translationMap, language }) {
  const assets = useMemo(() => nodeAssets(record, nodeId), [record, nodeId]);
  const [activeFigureIndex, setActiveFigureIndex] = useState(null);
  const [showInstances, setShowInstances] = useState(false);

  const leaf = String(nodeId || '').split('__').at(-1) || nodeId;
  const currentNodeLabel = translatedLabel(record.image_id, nodeId, translationMap, language);
  const instanceCount = assets.instance_paths?.length || 0;
  const breadcrumbSegments = useMemo(
    () => translatedPathLabels(record.image_id, nodeId, translationMap, language),
    [nodeId, record.image_id, translationMap, language]
  );

  const pills = useMemo(
    () =>
      getInspectorPills(record, nodeId, translationMap, language).filter(
        (pill) =>
          !pill.startsWith(`${uiText(language, 'inspector.current')}:`) &&
          !pill.startsWith(`${uiText(language, 'inspector.path')}:`)
      ),
    [record, nodeId, translationMap, language]
  );

  const derivedFigures = useDerivedFigures(
    record.image_id,
    assets.root_original,
    assets.instances_colored,
    assets.full_size,
    leaf,
    language
  );

  const derivedReady = useMemo(() => {
    if (!(assets.root_original && assets.instances_colored)) {
      return true;
    }
    return derivedFigures.every((figure) => Boolean(figure.src));
  }, [assets.instances_colored, assets.root_original, derivedFigures]);

  const figures = useMemo(() => {
    const nextFigures = [];

    if (assets.root_original) {
      nextFigures.push({
        key: `root-original-${record.image_id}`,
        title: uiText(language, 'visual.originalImage'),
        src: buildAssetUrl(record.image_id, assets.root_original),
        fullSize: assets.full_size,
      });
    }

    if (assets.root_original && assets.instances_colored) {
      nextFigures.push(...derivedFigures);
    }

    if (assets.instances_colored) {
      nextFigures.push({
        key: `instances-colored-${record.image_id}-${nodeId}`,
        title: uiText(language, 'visual.instances'),
        src: derivedReady ? buildAssetUrl(record.image_id, assets.instances_colored) : '',
        fullSize: assets.full_size,
      });
    }

    return nextFigures;
  }, [
    assets.full_size,
    assets.instances_colored,
    assets.root_original,
    derivedReady,
    derivedFigures,
    leaf,
    language,
    nodeId,
    record.image_id,
  ]);

  const instanceFigures = useMemo(
    () =>
      (assets.instance_paths || []).map((instancePath, index) => ({
        key: `instance-${record.image_id}-${nodeId}-${index}`,
        title: uiText(language, 'visual.instanceItem', { index: index + 1 }),
        src: buildAssetUrl(record.image_id, instancePath),
        fullSize: assets.full_size,
      })),
    [assets.full_size, assets.instance_paths, nodeId, record.image_id, language]
  );

  const modalFigures = useMemo(
    () => (showInstances ? [...figures, ...instanceFigures] : figures).filter((figure) => Boolean(figure.src)),
    [figures, instanceFigures, showInstances]
  );

  useEffect(() => {
    if (activeFigureIndex === null) return;
    if (!modalFigures.length) {
      setActiveFigureIndex(null);
      return;
    }
    if (activeFigureIndex >= modalFigures.length) {
      setActiveFigureIndex(modalFigures.length - 1);
    }
  }, [activeFigureIndex, modalFigures]);

  const handleOpenFigure = (figure) => {
    const nextIndex = modalFigures.findIndex((item) => item.key === figure.key);
    if (nextIndex >= 0) {
      setActiveFigureIndex(nextIndex);
    }
  };

  const handleCloseModal = () => setActiveFigureIndex(null);

  const handleToggleInstances = () => {
    setShowInstances((prev) => {
      const next = !prev;
      if (!next) {
        setActiveFigureIndex(null);
      }
      return next;
    });
  };

  const handlePrevFigure = () => {
    setActiveFigureIndex((prev) => {
      if (prev === null || !modalFigures.length) return prev;
      return (prev - 1 + modalFigures.length) % modalFigures.length;
    });
  };

  const handleNextFigure = () => {
    setActiveFigureIndex((prev) => {
      if (prev === null || !modalFigures.length) return prev;
      return (prev + 1) % modalFigures.length;
    });
  };

  return (
    <>
      <section className="sectionCard">
        <div className="sectionHeaderWithMeta">
          <div>
            <div className="visualsTitleRow">
              <h2 className="sectionTitle">{currentNodeLabel}</h2>
              {breadcrumbSegments.length ? (
                <div className="visualsBreadcrumb" aria-label={uiText(language, 'visual.nodePathAria')}>
                  {breadcrumbSegments.map((segment, index) => (
                    <React.Fragment key={`${segment}-${index}`}>
                      <span
                        className={`breadcrumbSegment ${index === breadcrumbSegments.length - 1 ? 'isCurrent' : ''}`.trim()}
                      >
                        {segment}
                      </span>
                      {index < breadcrumbSegments.length - 1 ? (
                        <span className="breadcrumbDivider" aria-hidden="true">
                          &rsaquo;
                        </span>
                      ) : null}
                    </React.Fragment>
                  ))}
                </div>
              ) : null}
            </div>
            <div className="statusPillsRow visualsStatusRow">
              {pills.map((pill) => {
                const { label, value } = splitPillText(pill);
                return (
                  <span className="statusPill" key={pill}>
                    {label ? <span className="statusPillLabel">{label}</span> : null}
                    <span className="statusPillValue">{value || pill}</span>
                  </span>
                );
              })}
            </div>
          </div>
          {instanceCount ? (
            <div className="visualsHeaderActions">
              <button
                type="button"
                className={`secondaryButton visualsToggleButton ${showInstances ? 'isActive' : ''}`.trim()}
                onClick={handleToggleInstances}
                aria-expanded={showInstances}
              >
                {showInstances
                  ? uiText(language, 'visual.hideInstances', { count: instanceCount })
                  : uiText(language, 'visual.showInstances', { count: instanceCount })}
              </button>
            </div>
          ) : null}
        </div>

        {figures.length ? (
          <div className="visualsGrid">
            {figures.map((figure) => (
              <FigureCard key={figure.key} title={figure.title}>
                <FigureImageButton figure={figure} onOpen={() => handleOpenFigure(figure)} language={language} />
              </FigureCard>
            ))}
          </div>
        ) : (
          <div className="emptyBox">{uiText(language, 'visual.noNodeImages')}</div>
        )}

        {showInstances ? (
          <div className="instancesPanel">
            <div className="instancesPanelHeader">
              <div className="instancesPanelTitle">{uiText(language, 'visual.instances')}</div>
              <div className="instancesPanelMeta">{uiText(language, 'visual.items', { count: instanceCount })}</div>
            </div>
            <div className="instancesGrid">
              {instanceFigures.map((figure) => (
                <FigureCard key={figure.key} title={figure.title}>
                  <FigureImageButton figure={figure} onOpen={() => handleOpenFigure(figure)} language={language} />
                </FigureCard>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <ImageModal
        figures={modalFigures}
        activeIndex={activeFigureIndex}
        onClose={handleCloseModal}
        onPrev={handlePrevFigure}
        onNext={handleNextFigure}
        contextLabel={currentNodeLabel}
        language={language}
      />
    </>
  );
}
