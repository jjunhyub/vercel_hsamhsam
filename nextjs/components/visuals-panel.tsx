// @ts-nocheck
'use client';

import { useMemo, useEffect, useState } from 'react';
import { getInspectorPills, nodeAssets } from '../lib/review-logic';

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

function AspectFrame({ width, height, children, dark = true }) {
  const w = Math.max(1, Number(width || 1));
  const h = Math.max(1, Number(height || 1));
  return (
    <div className={`aspectFrame ${dark ? 'isDark' : ''}`} style={{ aspectRatio: `${w} / ${h}` }}>
      {children}
    </div>
  );
}

function DirectImageFigure({ imageId, path, title, fullSize }) {
  if (!path) return null;
  const url = buildAssetUrl(imageId, path);
  return (
    <FigureCard title={title}>
      <AspectFrame width={fullSize?.[0]} height={fullSize?.[1]}>
        <img className="frameImage" src={url} alt={title} loading="lazy" />
      </AspectFrame>
    </FigureCard>
  );
}

function GeneratedImageFigure({ title, src, fullSize }) {
  if (!src) return null;

  return (
    <FigureCard title={title}>
      <AspectFrame width={fullSize?.[0]} height={fullSize?.[1]}>
        <img className="frameImage" src={src} alt={title} loading="lazy" />
      </AspectFrame>
    </FigureCard>
  );
}

function DerivedMaskViews({ imageId, rootPath, coloredPath, fullSize, leaf }) {
  const [derived, setDerived] = useState({
    overlay: '',
    maskOriginalFull: '',
    mask: '',
  });

  useEffect(() => {
    let cancelled = false;

    if (!imageId || !rootPath || !coloredPath) {
      setDerived({
        overlay: '',
        maskOriginalFull: '',
        mask: '',
      });
      return;
    }

    const rootUrl = buildAssetUrl(imageId, rootPath);
    const coloredUrl = buildAssetUrl(imageId, coloredPath);

    async function loadAndBuild() {
      const loadImage = (src) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.crossOrigin = 'anonymous';
          img.onload = () => resolve(img);
          img.onerror = reject;
          img.src = src;
        });

      try {
        const [rootImg, coloredImg] = await Promise.all([
          loadImage(rootUrl),
          loadImage(coloredUrl),
        ]);

        const width = rootImg.naturalWidth || rootImg.width;
        const height = rootImg.naturalHeight || rootImg.height;

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

        if (
          !rootCtx ||
          !coloredCtx ||
          !overlayCtx ||
          !maskOriginalCtx ||
          !maskCtx
        ) {
          return;
        }

        rootCtx.drawImage(rootImg, 0, 0, width, height);
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
            // 1) overlay: 원본 위에 붉은색 반투명
            overlayData[i] = Math.round(rr * 0.65 + 255 * 0.35);
            overlayData[i + 1] = Math.round(rg * 0.65);
            overlayData[i + 2] = Math.round(rb * 0.65);
            overlayData[i + 3] = ra;

            // 2) mask original full: 마스크 영역만 원본, 나머지는 검정
            maskOriginalData[i] = rr;
            maskOriginalData[i + 1] = rg;
            maskOriginalData[i + 2] = rb;
            maskOriginalData[i + 3] = ra;

            // 3) binary mask: foreground는 흰색
            maskData[i] = 255;
            maskData[i + 1] = 255;
            maskData[i + 2] = 255;
            maskData[i + 3] = 255;
          } else {
            // overlay는 원본 그대로
            overlayData[i] = rr;
            overlayData[i + 1] = rg;
            overlayData[i + 2] = rb;
            overlayData[i + 3] = ra;

            // mask original full 배경은 검정
            maskOriginalData[i] = 0;
            maskOriginalData[i + 1] = 0;
            maskOriginalData[i + 2] = 0;
            maskOriginalData[i + 3] = 255;

            // binary mask 배경은 검정
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
          setDerived({
            overlay: '',
            maskOriginalFull: '',
            mask: '',
          });
        }
      }
    }

    loadAndBuild();

    return () => {
      cancelled = true;
    };
  }, [imageId, rootPath, coloredPath]);

  return (
    <>
      <GeneratedImageFigure
        title={`오버레이 <${leaf}>`}
        src={derived.overlay}
        fullSize={fullSize}
      />
      <GeneratedImageFigure
        title={`원본 <${leaf}>`}
        src={derived.maskOriginalFull}
        fullSize={fullSize}
      />
      <GeneratedImageFigure
        title={`마스크 <${leaf}>`}
        src={derived.mask}
        fullSize={fullSize}
      />
    </>
  );
}


export default function VisualsPanel({ record, nodeId, translationMap }) {
  const assets = useMemo(() => nodeAssets(record, nodeId), [record, nodeId]);
  console.log('assets', assets);

  const leaf = String(nodeId || '').split('__').at(-1) || nodeId;

  console.log('imageId:', record?.image_id);
  console.log('nodeId:', nodeId);
  console.log('translation entry:', translationMap?.[record?.image_id]?.[nodeId]);

  const pills = useMemo(
    () => getInspectorPills(record, nodeId, translationMap),
    [record, nodeId, translationMap]
  );


  const reviewFigures = [
    assets.root_original ? (
      <DirectImageFigure
        key="root-original"
        imageId={record.image_id}
        path={assets.root_original}
        title="원본 이미지"
        fullSize={assets.full_size}
      />
    ) : null,

    assets.root_original && assets.instances_colored ? (
      <DerivedMaskViews
        key="derived-views"
        imageId={record.image_id}
        rootPath={assets.root_original}
        coloredPath={assets.instances_colored}
        fullSize={assets.full_size}
        leaf={leaf}
      />
    ) : null,

    assets.instances_colored ? (
      <DirectImageFigure
        key="instances-colored"
        imageId={record.image_id}
        path={assets.instances_colored}
        title={`인스턴스 <${leaf}>`}
        fullSize={assets.full_size}
      />
    ) : null,
  ].filter(Boolean);
  // const reviewFigures = [
  //   assets.root_original ? (
  //     <DirectImageFigure
  //       key="root-original"
  //       imageId={record.image_id}
  //       path={assets.root_original}
  //       title="원본 이미지"
  //       fullSize={assets.full_size}
  //     />
  //   ) : null,

  //   assets.overlay ? (
  //     <DirectImageFigure
  //       key="overlay"
  //       imageId={record.image_id}
  //       path={assets.overlay}
  //       title={`오버레이 <${leaf}>`}
  //       fullSize={assets.full_size}
  //     />
  //   ) : null,

  //   assets.mask_original_full ? (
  //     <DirectImageFigure
  //       key="mask-original-full"
  //       imageId={record.image_id}
  //       path={assets.mask_original_full}
  //       title={`원본 <${leaf}>`}
  //       fullSize={assets.full_size}
  //     />
  //   ) : null,

  //   assets.mask ? (
  //     <DirectImageFigure
  //       key="mask"
  //       imageId={record.image_id}
  //       path={assets.mask}
  //       title={`마스크 <${leaf}>`}
  //       fullSize={assets.full_size}
  //     />
  //   ) : null,

  //   assets.instances_colored ? (
  //     <DirectImageFigure
  //       key="instances-colored"
  //       imageId={record.image_id}
  //       path={assets.instances_colored}
  //       title={`인스턴스 <${leaf}>`}
  //       fullSize={assets.full_size}
  //     />
  //   ) : null,
  // ].filter(Boolean);

  return (
    <section className="sectionCard">
      <div className="sectionHeaderWithMeta">
        <div>
          <h2 className="sectionTitle">Visuals</h2>
          <div className="statusPillsRow">
            {pills.map((pill) => (
              <span className="statusPill" key={pill}>
                {pill}
              </span>
            ))}
          </div>
        </div>
      </div>

      {reviewFigures.length ? (
        <div className="visualsGrid">{reviewFigures}</div>
      ) : (
        <div className="emptyBox">노드 검토용 이미지를 찾지 못했습니다.</div>
      )}
    </section>
  );
}